"""Read-only GitHub project inspection for the App Factory slice (R191-B).

Two GET calls, nothing else:

1. ``GET /repos/{owner}/{repo}/git/ref/heads/{branch}`` → head commit sha
2. ``GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1`` → flat tree

The result is a bounded ``ProjectInventory`` (blob paths capped at
``max_paths``; language tally by extension; well-known manifests detected).
No clone, no subprocess, no write verb — the same posture as
``github_transport.py`` (R172 §2), and the same credential rule (20 §5): the
token arrives per call, rides ONLY the ``Authorization`` header of that call's
requests, and is never stored, never echoed into results or exception text.

``bind(token)`` returns a token-free ``ProjectInspectorPort`` adaptor for
``core.agent.app_factory.AppFactoryCapability`` so the core layer never sees
the credential; the composition layer decides when/how a token is supplied.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx

from apps.agent_dev.git_tools import (
    BindingLookupRefused,
    RemoteTrustPort,
    RepoBindingRegistry,
    TransportError,
)
from apps.agent_dev.github_transport import GITHUB_API_BASE, parse_github_remote
from core.agent.app_factory import ProjectInventory
from core.contracts.repo_binding import GitRefusalCode, RepoBinding
from core.secrets.errors import SecretNotFound

if TYPE_CHECKING:
    from uuid import UUID

    from core.secrets.ports import SecretManagerPort

_API_VERSION = "2022-11-28"
_DEFAULT_MAX_PATHS = 2000

_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".sh": "shell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}
_LANGUAGE_BY_FILENAME: dict[str, str] = {"Dockerfile": "dockerfile", "Makefile": "make"}
_MANIFESTS: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "Gemfile",
        "composer.json",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
)


def _language_of(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name in _LANGUAGE_BY_FILENAME:
        return _LANGUAGE_BY_FILENAME[name]
    dot = name.rfind(".")
    if dot <= 0:
        return None
    return _LANGUAGE_BY_EXTENSION.get(name[dot:].lower())


class GitHubProjectInspector:
    """Read-only inspector; ``transport`` is injected so tests never touch the network."""

    def __init__(
        self,
        *,
        base_url: str = GITHUB_API_BASE,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 30.0,
        max_paths: int = _DEFAULT_MAX_PATHS,
    ) -> None:
        if max_paths < 1:
            raise ValueError("max_paths must be >= 1")
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout_seconds
        self._max_paths = max_paths

    def __repr__(self) -> str:  # never includes credentials — none are stored
        return f"GitHubProjectInspector(base_url={self._base_url!r}, max_paths={self._max_paths})"

    # -- http plumbing (mirrors GitHubRestTransport) ---------------------------------

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
    async def _get(client: httpx.AsyncClient, path: str, **params: str) -> httpx.Response:
        try:
            return await client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise TransportError(f"github api unreachable ({type(exc).__name__})") from exc

    @staticmethod
    def _json(response: httpx.Response, what: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise TransportError(f"{what}: malformed github response") from exc
        if not isinstance(body, dict):
            raise TransportError(f"{what}: malformed github response")
        return body

    # -- port ----------------------------------------------------------------------------

    async def inspect(self, remote_url: str, branch: str, *, token: str) -> ProjectInventory:
        owner, repo = parse_github_remote(remote_url)  # refuses BEFORE any network call
        async with self._client(token) as client:
            ref = await self._get(client, f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
            if ref.status_code == 404:
                raise TransportError(f"branch {branch!r} not found on remote")
            if ref.status_code >= 400:
                raise TransportError(f"inspect: github api error (http {ref.status_code})")
            sha = self._json(ref, "inspect").get("object", {}).get("sha")
            if not isinstance(sha, str) or not sha:
                raise TransportError("inspect: malformed github response")
            tree = await self._get(client, f"/repos/{owner}/{repo}/git/trees/{sha}", recursive="1")
            if tree.status_code >= 400:
                raise TransportError(f"inspect: github api error (http {tree.status_code})")
            body = self._json(tree, "inspect")
        entries = body.get("tree")
        if not isinstance(entries, list):
            raise TransportError("inspect: malformed github response")
        return self._inventory(remote_url, branch, sha, entries, bool(body.get("truncated")))

    def _inventory(
        self, remote_url: str, branch: str, sha: str, entries: list[Any], truncated: bool
    ) -> ProjectInventory:
        blobs: list[str] = []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("type") == "blob":
                path = entry.get("path")
                if isinstance(path, str) and path:
                    blobs.append(path)
        blobs.sort()
        languages: Counter[str] = Counter()
        manifests: list[str] = []
        for path in blobs:
            lang = _language_of(path)
            if lang is not None:
                languages[lang] += 1
            if path.rsplit("/", 1)[-1] in _MANIFESTS:
                manifests.append(path)
        return ProjectInventory(
            remote_url=remote_url,
            branch=branch,
            head_sha=sha,
            file_count=len(blobs),
            paths=blobs[: self._max_paths],
            languages=dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))),
            manifests=sorted(manifests),
            truncated=truncated or len(blobs) > self._max_paths,
        )

    def bind(self, token_source: Callable[[], str]) -> _BoundInspector:
        """Token-free ``ProjectInspectorPort`` for the core layer; the token is pulled per call."""
        return _BoundInspector(self, token_source)


class _BoundInspector:
    """Adaptor: ``inspect(remote_url, branch)`` without a credential in the signature."""

    def __init__(self, inspector: GitHubProjectInspector, token_source: Callable[[], str]) -> None:
        self._inspector = inspector
        self._token_source = token_source

    def __repr__(self) -> str:
        return f"BoundInspector({self._inspector!r})"

    def inspect(self, remote_url: str, branch: str) -> ProjectInventory:
        return asyncio.run(self._inspector.inspect(remote_url, branch, token=self._token_source()))


class BoundProjectInspector:
    """R192 G1 — the GOVERNED inspection path, by ``RepoBinding`` id.

    Same chain, same authorities, same order as ``GitToolset`` (R169/R172):

    1. ``RepoBindingRegistry.get(binding_id, tenant_id=...)`` — tenant-scoped;
       a foreign tenant's binding is ``binding_tenant_mismatch``, never "unknown".
    2. ``RemoteTrustPort.is_trusted`` BEFORE any credential resolve; a registry
       fault is "not trusted" (fail closed). ``trust=None`` preserves the pre-R172
       behaviour exactly like ``GitToolset``.
    3. ``SecretManagerPort.resolve(tenant_id, binding.credential_ref)`` at the
       last moment; ``SecretNotFound`` → ``credential_unresolved``. The value is
       passed straight into ``GitHubProjectInspector.inspect`` and never stored.

    Implements ``core.agent.app_factory.BindingInspectorPort`` so Core only ever
    sees a binding id and an inventory — no URL+token pairs cross into Core.
    """

    def __init__(
        self,
        inspector: GitHubProjectInspector,
        *,
        tenant_id: UUID,
        bindings: RepoBindingRegistry,
        trust: RemoteTrustPort | None,
        secrets: SecretManagerPort,
    ) -> None:
        self._inspector = inspector
        self._tenant_id = tenant_id
        self._bindings = bindings
        self._trust = trust
        self._secrets = secrets

    def __repr__(self) -> str:  # never includes credentials — none are stored
        return f"BoundProjectInspector(tenant={self._tenant_id}, inspector={self._inspector!r})"

    # -- the ONE governed chain (mirrors GitToolset._binding/_require_trust/_token) ----

    def _require_trust(self, binding: RepoBinding) -> None:
        if self._trust is None:
            return
        try:
            trusted = self._trust.is_trusted(self._tenant_id, binding.remote_url) is True
        except Exception:  # defensive: registry faults must not become 500s
            trusted = False
        if not trusted:
            raise BindingLookupRefused(
                GitRefusalCode.REMOTE_NOT_TRUSTED,
                f"remote {binding.remote_url} is not trusted for tenant {self._tenant_id}",
            )

    def _token(self, binding: RepoBinding) -> str:
        try:
            return self._secrets.resolve(self._tenant_id, binding.credential_ref)
        except SecretNotFound as exc:
            raise BindingLookupRefused(
                GitRefusalCode.CREDENTIAL_UNRESOLVED,
                f"credential_ref could not be resolved for binding {binding.id}",
            ) from exc

    def inspect_binding(self, binding_id: UUID) -> ProjectInventory:
        binding = self._bindings.get(binding_id, tenant_id=self._tenant_id)
        self._require_trust(binding)  # BEFORE the credential is touched
        token = self._token(binding)
        return asyncio.run(self._inspector.inspect(binding.remote_url, binding.branch, token=token))
