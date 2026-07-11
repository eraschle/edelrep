"""Read the local git HEAD and compare against the GitHub upstream HEAD."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_GITHUB_API_URL = "https://api.github.com/repos/eraschle/edelrep/commits/master"
_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    current: str
    latest: str
    update_available: bool

    @property
    def current_short(self) -> str:
        return self.current[:7] if self.current != _UNKNOWN else _UNKNOWN

    @property
    def latest_short(self) -> str:
        return self.latest[:7] if self.latest != _UNKNOWN else _UNKNOWN


class UpdateChecker:
    """Determines whether the local checkout has an upstream update available.

    The local commit is read from ``git rev-parse HEAD`` in ``project_root``;
    the upstream commit is fetched from the public GitHub API (no auth
    needed because the repo is public).
    """

    def __init__(
        self,
        project_root: Path,
        *,
        api_url: str = _GITHUB_API_URL,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._root = project_root
        self._api_url = api_url
        self._timeout = timeout_seconds

    def current_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return _UNKNOWN

    def latest_commit(self) -> str:
        try:
            req = urllib.request.Request(
                self._api_url, headers={"Accept": "application/vnd.github+json"}
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.load(resp)
            sha = data.get("sha")
            return str(sha) if isinstance(sha, str) else _UNKNOWN
        except (OSError, ValueError):
            return _UNKNOWN

    def status(self) -> UpdateStatus:
        current = self.current_commit()
        latest = self.latest_commit()
        if current == _UNKNOWN or latest == _UNKNOWN:
            available = False
        else:
            available = current != latest
        return UpdateStatus(current=current, latest=latest, update_available=available)
