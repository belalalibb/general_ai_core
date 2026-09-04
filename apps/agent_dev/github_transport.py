"""REST-only GitHub implementation of ``GitTransportPort`` (R172 C8).

Why REST and not ``git``: R172 §2 forbids subprocesses, shells and hooks in the
agent's write path. The GitHub Git Data API lets us build blobs → tree → commit
and move a branch ref with plain HTTPS calls, and the Pulls API opens the pull
request. There is therefore no local ``.git`` directory: ``commit()`` stages a
content-addressed snapshot of the jailed paths in memory (keyed by binding id),
``push()`` uploads that snapshot and points ``refs/heads/<branch>`` at the new
commit. ``status()``/``diff_summary()`` describe the staging area.

Credential posture (20 §5): the token arrives per call, rides ONLY the
``Authorization`` header of the requests made inside that call, and is never
stored on the instance, never echoed into results or exception text.

Error mapping (GitToolset relies on these types):
* HTTP 422 whose message names a pull-request/protected-branch rule →
  ``ProtectedBranchRejected`` (GitToolset turns it into
  ``remote_rejected_protected_branch`` + ``suggested_mode="pull_request"``).
* other 4xx on a mutating call → ``RemoteRejected``.
* transport/network failures, unknown remote shapes, missing refs →
  ``TransportError``.
* pushing with nothing staged, or committing zero readable files →
  ``NothingToCommit``.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from apps.agent_dev.git_tools import (
    NothingToCommit,
    ProtectedBranchRejected,
    RemoteRejected,
    TransportError,
)
from core.contracts.repo_binding import GitStatusResult, RepoBinding

GITHUB_API_BASE = "https://api.github.com"
_API_VERSION = "2022-11-28"
_REMOTE_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_PROTECTED_MARKERS = ("pull request", "protected branch", "protected")


def parse_github_remote(remote_url: str) -> tuple[str, str]:
    """``https://github.com/{owner}/{repo}[.git][/]`` → ``(owner, repo)``; else refuse."""
    match = _REMOTE_RE.match(remote_url)
    if match is None:
        raise TransportError("remote is not a github.com https repository URL")
    owner, repo = match.group(1), match.group(2)
    if owner in (".", "..") or repo in (".", ".."):
        raise TransportError("remote path segment rejected")
    return owner, repo


@dataclass(frozen=True)
class _StagedFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class _Staged:
    message: str
    files: tuple[_StagedFile, ...]
    sha: str


def _snapshot_sha(message: str, files: Sequence[_StagedFile]) -> str:
    digest = hashlib.sha1(usedforsecurity=False)  # git-shaped id (40 hex), local only
    digest.update(message.encode("utf-8"))
    for item in files:
        digest.update(b"\0")
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.content).digest())
    return digest.hexdigest()


def _jail(root: Path, raw: str) -> str:
    """Lexically resolve ``raw`` under ``root``; refuse escapes."""
    root_resolved = root.resolve()
    candidate = Path(raw)
    target = candidate if candidate.is_absolute() else root_resolved / candidate
    resolved = target.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise TransportError(f"path escapes binding root: {raw}")
    return resolved.relative_to(root_resolved).as_posix()


class GitHubRestTransport:
    """``GitTransportPort`` over the GitHub REST API (no subprocess, no shell)."""

    def __init__(
        self,
        *,
        base_url: str = GITHUB_API_BASE,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout_seconds
        self._staged: dict[UUID, _Staged] = {}

    def __repr__(self) -> str:  # never includes credentials — none are stored
        return f"GitHubRestTransport(base_url={self._base_url!r}, staged={len(self._staged)})"

    # -- http plumbing ------------------------------------------------------------

    def _client(self, token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            transport=self._transport,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
            },
        )

    @staticmethod
    async def _call(
        client: httpx.AsyncClient, method: str, path: str, *, json: Any | None = None
    ) -> httpx.Response:
        try:
            return await client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            # exc text may embed the URL but never the header; keep it short anyway
            raise TransportError(f"github api unreachable ({type(exc).__name__})") from exc

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        message = body.get("message") if isinstance(body, dict) else None
        return message if isinstance(message, str) else ""

    @classmethod
    def _raise_for_mutation(cls, response: httpx.Response, what: str) -> None:
        if response.status_code < 400:
            return
        message = cls._message(response)
        lowered = message.lower()
        if response.status_code == 422 and any(m in lowered for m in _PROTECTED_MARKERS):
            raise ProtectedBranchRejected(f"{what}: remote refused ({message or 'protected'})")
        if 400 <= response.status_code < 500:
            raise RemoteRejected(f"{what}: remote refused (http {response.status_code})")
        raise TransportError(f"{what}: github api error (http {response.status_code})")

    @staticmethod
    def _sha(response: httpx.Response, what: str) -> str:
        try:
            sha = response.json()["sha"]
        except (ValueError, KeyError, TypeError) as exc:
            raise TransportError(f"{what}: malformed github response") from exc
        if not isinstance(sha, str):
            raise TransportError(f"{what}: malformed github response")
        return sha

    # -- port: fetch / status / diff -------------------------------------------------

    async def fetch(self, binding: RepoBinding, *, token: str) -> str | None:
        owner, repo = parse_github_remote(binding.remote_url)
        async with self._client(token) as client:
            response = await self._call(
                client, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{binding.branch}"
            )
        if response.status_code == 404:
            raise TransportError(f"branch {binding.branch!r} not found on remote")
        if response.status_code >= 400:
            raise TransportError(f"fetch: github api error (http {response.status_code})")
        try:
            sha = response.json()["object"]["sha"]
        except (ValueError, KeyError, TypeError) as exc:
            raise TransportError("fetch: malformed github response") from exc
        return sha if isinstance(sha, str) else None

    async def status(self, binding: RepoBinding) -> GitStatusResult:
        staged = self._staged.get(binding.id)
        return GitStatusResult(
            binding_id=str(binding.id),
            branch=binding.branch,
            head=staged.sha if staged else None,
            clean=staged is None,
            entries=[f.path for f in staged.files] if staged else [],
        )

    async def diff_summary(self, binding: RepoBinding) -> str:
        staged = self._staged.get(binding.id)
        if staged is None:
            return "nothing staged"
        names = ", ".join(f.path for f in staged.files)
        return f"{len(staged.files)} file(s) staged for {binding.branch}: {names}"

    # -- port: commit (local snapshot, no network) ------------------------------------

    async def commit(self, binding: RepoBinding, *, message: str, paths: Sequence[str]) -> str:
        root = Path(binding.local_root)
        files: list[_StagedFile] = []
        seen: set[str] = set()
        for raw in paths:
            rel = _jail(root, raw)
            if rel in seen:
                continue
            seen.add(rel)
            target = root / rel
            if not target.is_file():
                continue
            files.append(_StagedFile(path=rel, content=target.read_bytes()))
        if not files:
            raise NothingToCommit("no readable files under the binding root to commit")
        files.sort(key=lambda f: f.path)
        sha = _snapshot_sha(message, files)
        self._staged[binding.id] = _Staged(message=message, files=tuple(files), sha=sha)
        return sha

    # -- port: push / pull request ----------------------------------------------------

    async def push(self, binding: RepoBinding, *, branch: str, token: str) -> None:
        staged = self._staged.get(binding.id)
        if staged is None:
            raise NothingToCommit("nothing staged — call git.commit first")
        owner, repo = parse_github_remote(binding.remote_url)
        prefix = f"/repos/{owner}/{repo}"
        async with self._client(token) as client:
            base = await self._call(client, "GET", f"{prefix}/git/ref/heads/{binding.branch}")
            if base.status_code >= 400:
                raise TransportError(
                    f"push: base branch {binding.branch!r} unavailable (http {base.status_code})"
                )
            try:
                base_sha = base.json()["object"]["sha"]
            except (ValueError, KeyError, TypeError) as exc:
                raise TransportError("push: malformed github response") from exc
            base_commit = await self._call(client, "GET", f"{prefix}/git/commits/{base_sha}")
            if base_commit.status_code >= 400:
                raise TransportError("push: base commit unavailable")
            try:
                base_tree = base_commit.json()["tree"]["sha"]
            except (ValueError, KeyError, TypeError) as exc:
                raise TransportError("push: malformed github response") from exc

            entries: list[dict[str, str]] = []
            for item in staged.files:
                blob = await self._call(
                    client, "POST", f"{prefix}/git/blobs", json=_blob_body(item.content)
                )
                self._raise_for_mutation(blob, "push(blob)")
                entries.append(
                    {
                        "path": item.path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": self._sha(blob, "push(blob)"),
                    }
                )
            tree = await self._call(
                client,
                "POST",
                f"{prefix}/git/trees",
                json={"base_tree": base_tree, "tree": entries},
            )
            self._raise_for_mutation(tree, "push(tree)")
            commit = await self._call(
                client,
                "POST",
                f"{prefix}/git/commits",
                json={
                    "message": staged.message,
                    "tree": self._sha(tree, "push(tree)"),
                    "parents": [base_sha],
                },
            )
            self._raise_for_mutation(commit, "push(commit)")
            commit_sha = self._sha(commit, "push(commit)")

            existing = await self._call(client, "GET", f"{prefix}/git/ref/heads/{branch}")
            if existing.status_code == 404:
                created = await self._call(
                    client,
                    "POST",
                    f"{prefix}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
                )
                self._raise_for_mutation(created, f"push({branch})")
            else:
                moved = await self._call(
                    client,
                    "PATCH",
                    f"{prefix}/git/refs/heads/{branch}",
                    json={"sha": commit_sha, "force": False},
                )
                self._raise_for_mutation(moved, f"push({branch})")
        # only after the remote accepted the ref does the staging area clear
        self._staged.pop(binding.id, None)

    async def open_pull_request(
        self, binding: RepoBinding, *, work_branch: str, title: str, token: str
    ) -> str:
        owner, repo = parse_github_remote(binding.remote_url)
        async with self._client(token) as client:
            response = await self._call(
                client,
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                json={
                    "title": title,
                    "head": work_branch,
                    "base": binding.branch,
                    "body": "Opened by the dev agent (publish mode: pull_request).",
                },
            )
        self._raise_for_mutation(response, "open_pull_request")
        try:
            url = response.json()["html_url"]
        except (ValueError, KeyError, TypeError) as exc:
            raise TransportError("open_pull_request: malformed github response") from exc
        if not isinstance(url, str):
            raise TransportError("open_pull_request: malformed github response")
        return url


def _blob_body(content: bytes) -> dict[str, str]:
    """UTF-8 text goes as-is; anything else is base64 (Git Data API encodings)."""
    if b"\0" not in content:
        try:
            return {"content": content.decode("utf-8"), "encoding": "utf-8"}
        except UnicodeDecodeError:
            pass
    return {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"}


__all__ = ["GITHUB_API_BASE", "GitHubRestTransport", "parse_github_remote"]
