"""R172 C8 — hermetic spec for the REST-only GitHub transport.

The R169 ``GitTransportPort`` had ONLY a test fake behind it (discovery: "live git
transport NOT EVALUATED"). This spec pins a real implementation that speaks the
GitHub Git Data / Pulls REST API over httpx — **no subprocess, no shell, no hooks**
(R172 §2). Every test here runs against ``httpx.MockTransport``; the live proof is
``tests_live/r172/test_live_transport.py`` (env-gated, outside the verifier).

Design facts pinned:
* ``commit()`` receives NO token (port shape) — it stages a local snapshot of the
  jailed paths under ``binding.local_root``; nothing leaves the process.
* ``push()`` uploads blobs → tree → commit and moves/creates the branch ref; a 422
  "Changes must be made through a pull request." / "protected" becomes
  ``ProtectedBranchRejected``; other 4xx → ``RemoteRejected``; network → ``TransportError``.
* The token rides ONLY the ``Authorization`` header of each call; it is never
  stored on the instance, never in results, never in ``repr``.

Fail-first: the module does not exist at 6d09e56 (ImportError on collection).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.agent_dev.git_tools import (
    NothingToCommit,
    ProtectedBranchRejected,
    RemoteRejected,
    TransportError,
)
from apps.agent_dev.github_transport import GitHubRestTransport, parse_github_remote
from core.contracts.repo_binding import RepoBinding

TOKEN = "ghp_" + "T" * 36  # synthetic; matches the strict scan shape on purpose
REMOTE = "https://github.com/acme/widgets.git"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@dataclass
class FakeGitHub:
    """Minimal stateful GitHub Git Data API double."""

    heads: dict[str, str] = field(default_factory=lambda: {"main": "a" * 40})
    protected: set[str] = field(default_factory=set)
    requests: list[httpx.Request] = field(default_factory=list)
    objects: int = 0
    fail_network: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_network:
            raise httpx.ConnectError("boom", request=request)
        path = request.url.path
        method = request.method
        if method == "GET" and "/git/ref/heads/" in path:
            branch = path.rsplit("/git/ref/heads/", 1)[1]
            if branch not in self.heads:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": self.heads[branch]}})
        if method == "GET" and "/git/commits/" in path:
            return httpx.Response(200, json={"tree": {"sha": "t" * 40}})
        if method == "POST" and path.endswith(("/git/blobs", "/git/trees", "/git/commits")):
            self.objects += 1
            return httpx.Response(201, json={"sha": f"{self.objects:040x}"})
        if method == "PATCH" and "/git/refs/heads/" in path:
            branch = path.rsplit("/git/refs/heads/", 1)[1]
            if branch in self.protected:
                return httpx.Response(
                    422, json={"message": "Changes must be made through a pull request."}
                )
            if branch == "stale":
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            self.heads[branch] = json.loads(request.content)["sha"]
            return httpx.Response(200, json={"object": {"sha": self.heads[branch]}})
        if method == "POST" and path.endswith("/git/refs"):
            body = json.loads(request.content)
            branch = body["ref"].removeprefix("refs/heads/")
            if branch in self.protected:
                return httpx.Response(422, json={"message": "protected branch"})
            self.heads[branch] = body["sha"]
            return httpx.Response(201, json={"ref": body["ref"]})
        if method == "POST" and path.endswith("/pulls"):
            body = json.loads(request.content)
            if body["head"] not in self.heads:
                return httpx.Response(422, json={"message": "Validation Failed"})
            return httpx.Response(
                201, json={"html_url": f"https://github.com/acme/widgets/pull/7?h={body['head']}"}
            )
        return httpx.Response(500, json={"message": f"unhandled {method} {path}"})


def _binding(tmp_path: Path, remote: str = REMOTE) -> RepoBinding:
    root = tmp_path / "work"
    root.mkdir(exist_ok=True)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    return RepoBinding(
        tenant_id=uuid4(), remote_url=remote, branch="main", local_root=str(root),
        credential_ref="credref_x",
    )


def _transport(gh: FakeGitHub) -> GitHubRestTransport:
    return GitHubRestTransport(transport=httpx.MockTransport(gh.handler))


def _auth_headers(gh: FakeGitHub) -> set[str]:
    return {r.headers.get("authorization", "") for r in gh.requests}


class TestRemoteParsing:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/acme/widgets.git",
            "https://github.com/acme/widgets",
            "https://github.com/acme/widgets/",
        ],
    )
    def test_accepts_github_https_forms(self, url: str) -> None:
        assert parse_github_remote(url) == ("acme", "widgets")

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/acme/widgets.git",
            "https://github.com/acme",
            "https://github.com/acme/widgets/extra",
            "https://github.com/../widgets",
            "https://github.com/acme/wid gets",
        ],
    )
    def test_refuses_everything_else(self, url: str) -> None:
        with pytest.raises(TransportError):
            parse_github_remote(url)


class TestFetchStatus:
    def test_fetch_returns_remote_head_and_uses_bearer_token_only_in_header(
        self, tmp_path: Path
    ) -> None:
        gh = FakeGitHub()
        t = _transport(gh)
        head = run(t.fetch(_binding(tmp_path), token=TOKEN))
        assert head == "a" * 40
        assert _auth_headers(gh) == {f"Bearer {TOKEN}"}
        assert TOKEN not in repr(t)

    def test_fetch_unknown_branch_is_transport_error(self, tmp_path: Path) -> None:
        gh = FakeGitHub(heads={})
        with pytest.raises(TransportError):
            run(_transport(gh).fetch(_binding(tmp_path), token=TOKEN))

    def test_fetch_network_failure_is_transport_error_without_token(self, tmp_path: Path) -> None:
        gh = FakeGitHub(fail_network=True)
        with pytest.raises(TransportError) as info:
            run(_transport(gh).fetch(_binding(tmp_path), token=TOKEN))
        assert TOKEN not in str(info.value)

    def test_status_is_local_and_needs_no_network(self, tmp_path: Path) -> None:
        gh = FakeGitHub()
        t = _transport(gh)
        binding = _binding(tmp_path)
        status = run(t.status(binding))
        assert status.branch == "main" and status.head is None and status.clean is True
        assert gh.requests == []


class TestLocalCommit:
    def test_commit_stages_snapshot_without_network(self, tmp_path: Path) -> None:
        gh = FakeGitHub()
        t = _transport(gh)
        binding = _binding(tmp_path)
        sha = run(t.commit(binding, message="m", paths=["README.md"]))
        assert isinstance(sha, str) and len(sha) == 40
        assert gh.requests == []
        status = run(t.status(binding))
        assert status.head == sha and status.clean is False and status.entries == ["README.md"]
        assert "README.md" in run(t.diff_summary(binding))

    def test_commit_missing_file_is_nothing_to_commit(self, tmp_path: Path) -> None:
        t = _transport(FakeGitHub())
        with pytest.raises(NothingToCommit):
            run(t.commit(_binding(tmp_path), message="m", paths=["absent.txt"]))

    @pytest.mark.parametrize("raw", ["/etc/passwd", "../outside.txt", "a/../../b"])
    def test_commit_refuses_paths_that_escape_the_root(self, tmp_path: Path, raw: str) -> None:
        t = _transport(FakeGitHub())
        with pytest.raises(TransportError):
            run(t.commit(_binding(tmp_path), message="m", paths=[raw]))

    def test_commit_is_content_addressed(self, tmp_path: Path) -> None:
        t = _transport(FakeGitHub())
        a, b = _binding(tmp_path / "1"), _binding(tmp_path / "2")
        s1 = run(t.commit(a, message="m", paths=["README.md"]))
        s2 = run(t.commit(b, message="m", paths=["README.md"]))
        assert s1 == s2


class TestPush:
    def test_push_uploads_objects_and_creates_branch(self, tmp_path: Path) -> None:
        gh = FakeGitHub()
        t = _transport(gh)
        binding = _binding(tmp_path)
        run(t.commit(binding, message="m", paths=["README.md"]))
        run(t.push(binding, branch="dev/x", token=TOKEN))
        assert "dev/x" in gh.heads
        assert gh.objects == 3  # blob + tree + commit
        assert _auth_headers(gh) == {f"Bearer {TOKEN}"}
        # after a successful push the staging area is clean again
        assert run(t.status(binding)).clean is True

    def test_push_without_staged_commit_is_nothing_to_commit(self, tmp_path: Path) -> None:
        gh = FakeGitHub()
        with pytest.raises(NothingToCommit):
            run(_transport(gh).push(_binding(tmp_path), branch="dev/x", token=TOKEN))
        assert gh.requests == []

    def test_push_to_protected_branch_is_typed(self, tmp_path: Path) -> None:
        gh = FakeGitHub(protected={"main"})
        t = _transport(gh)
        binding = _binding(tmp_path)
        run(t.commit(binding, message="m", paths=["README.md"]))
        with pytest.raises(ProtectedBranchRejected):
            run(t.push(binding, branch="main", token=TOKEN))
        assert gh.heads["main"] == "a" * 40  # ref never moved

    def test_non_fast_forward_is_remote_rejected(self, tmp_path: Path) -> None:
        gh = FakeGitHub(heads={"main": "a" * 40, "stale": "b" * 40})
        t = _transport(gh)
        binding = _binding(tmp_path)
        run(t.commit(binding, message="m", paths=["README.md"]))
        with pytest.raises(RemoteRejected) as info:
            run(t.push(binding, branch="stale", token=TOKEN))
        assert not isinstance(info.value, ProtectedBranchRejected)


class TestPullRequest:
    def test_open_pull_request_returns_html_url(self, tmp_path: Path) -> None:
        gh = FakeGitHub()
        t = _transport(gh)
        binding = _binding(tmp_path)
        run(t.commit(binding, message="m", paths=["README.md"]))
        run(t.push(binding, branch="dev/x", token=TOKEN))
        url = run(t.open_pull_request(binding, work_branch="dev/x", title="t", token=TOKEN))
        assert url.startswith("https://github.com/acme/widgets/pull/")
        body = json.loads(gh.requests[-1].content)
        assert body["base"] == "main" and body["head"] == "dev/x"

    def test_open_pull_request_for_unknown_head_is_remote_rejected(self, tmp_path: Path) -> None:
        t = _transport(FakeGitHub())
        with pytest.raises(RemoteRejected):
            run(t.open_pull_request(_binding(tmp_path), work_branch="nope", title="t", token=TOKEN))


def test_module_has_no_subprocess_or_shell() -> None:
    source = Path("apps/agent_dev/github_transport.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "create_subprocess", "shell=True"):
        assert forbidden not in source
