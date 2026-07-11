import io
import subprocess
from pathlib import Path
from unittest.mock import patch

from edelrep.infrastructure.updates.update_checker import UpdateChecker

_LOCAL_SHA = "abc123def456abc123def456abc123def456abcd"
_REMOTE_SHA = "ffeeddccbbaa9988776655443322110099887766"


def _patch_subprocess_run(stdout: str = _LOCAL_SHA):
    completed = subprocess.CompletedProcess(
        args=["git", "rev-parse", "HEAD"], returncode=0, stdout=stdout, stderr=""
    )
    return patch(
        "edelrep.infrastructure.updates.update_checker.subprocess.run",
        return_value=completed,
    )


def _patch_urlopen(payload: bytes):
    response = io.BytesIO(payload)
    return patch(
        "edelrep.infrastructure.updates.update_checker.urllib.request.urlopen",
        return_value=_ContextManager(response),
    )


class _ContextManager:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self._body

    def __exit__(self, exc_type, exc, tb):
        return False


def test_current_commit_reads_git_head(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with _patch_subprocess_run(stdout=f"{_LOCAL_SHA}\n"):
        assert checker.current_commit() == _LOCAL_SHA


def test_current_commit_returns_unknown_when_git_missing(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with patch(
        "edelrep.infrastructure.updates.update_checker.subprocess.run",
        side_effect=FileNotFoundError("git not on PATH"),
    ):
        assert checker.current_commit() == "unknown"


def test_current_commit_returns_unknown_on_git_failure(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with patch(
        "edelrep.infrastructure.updates.update_checker.subprocess.run",
        side_effect=subprocess.CalledProcessError(128, "git"),
    ):
        assert checker.current_commit() == "unknown"


def test_latest_commit_parses_github_payload(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    payload = b'{"sha": "%s", "commit": {}}' % _REMOTE_SHA.encode()
    with _patch_urlopen(payload):
        assert checker.latest_commit() == _REMOTE_SHA


def test_latest_commit_returns_unknown_on_network_error(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with patch(
        "edelrep.infrastructure.updates.update_checker.urllib.request.urlopen",
        side_effect=OSError("offline"),
    ):
        assert checker.latest_commit() == "unknown"


def test_latest_commit_returns_unknown_on_malformed_json(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with _patch_urlopen(b"<html>404</html>"):
        assert checker.latest_commit() == "unknown"


def test_status_flags_update_when_shas_differ(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    payload = b'{"sha": "%s"}' % _REMOTE_SHA.encode()
    with _patch_subprocess_run(_LOCAL_SHA), _patch_urlopen(payload):
        status = checker.status()
    assert status.current == _LOCAL_SHA
    assert status.latest == _REMOTE_SHA
    assert status.update_available is True
    assert status.current_short == _LOCAL_SHA[:7]
    assert status.latest_short == _REMOTE_SHA[:7]


def test_status_reports_up_to_date_when_shas_match(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    payload = b'{"sha": "%s"}' % _LOCAL_SHA.encode()
    with _patch_subprocess_run(_LOCAL_SHA), _patch_urlopen(payload):
        status = checker.status()
    assert status.update_available is False


def test_status_never_flags_update_when_either_side_is_unknown(tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    with patch(
        "edelrep.infrastructure.updates.update_checker.subprocess.run",
        side_effect=FileNotFoundError(),
    ), patch(
        "edelrep.infrastructure.updates.update_checker.urllib.request.urlopen",
        side_effect=OSError(),
    ):
        status = checker.status()
    assert status.current == "unknown"
    assert status.latest == "unknown"
    assert status.update_available is False
    assert status.current_short == "unknown"
    assert status.latest_short == "unknown"
