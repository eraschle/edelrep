from pathlib import Path

import pytest

from edelrep.infrastructure.email.config import EmailConfig
from edelrep.presentation.container import build_container


def test_build_container_without_email_config_has_no_poller(tmp_path: Path) -> None:
    container = build_container(
        tmp_path / "store",
        tmp_path / "index.db",
        with_live_index=False,
    )
    assert container.email_poller is None
    container.projector.connection.close()


def test_build_container_with_disabled_email_has_no_poller(tmp_path: Path) -> None:
    cfg = EmailConfig(
        enabled=False,
        host="h",
        user="u",
        password_env="EMAIL_PASSWORD",
    )
    container = build_container(
        tmp_path / "store",
        tmp_path / "index.db",
        with_live_index=False,
        email_config=cfg,
    )
    assert container.email_poller is None
    container.projector.connection.close()


def test_build_container_raises_when_password_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EDELREP_TEST_NO_SUCH_VAR", raising=False)
    cfg = EmailConfig(
        enabled=True,
        host="h",
        user="u",
        password_env="EDELREP_TEST_NO_SUCH_VAR",
    )
    with pytest.raises(RuntimeError, match="EDELREP_TEST_NO_SUCH_VAR"):
        build_container(
            tmp_path / "store",
            tmp_path / "index.db",
            with_live_index=False,
            email_config=cfg,
        )


def test_build_container_with_enabled_email_creates_poller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDELREP_TEST_PWD", "secret123")
    cfg = EmailConfig(
        enabled=True,
        host="imap.test",
        user="u@test",
        password_env="EDELREP_TEST_PWD",
    )
    container = build_container(
        tmp_path / "store",
        tmp_path / "index.db",
        with_live_index=False,
        email_config=cfg,
    )
    try:
        assert container.email_poller is not None
        assert not container.email_poller.is_running()  # not started until lifespan
    finally:
        container.projector.connection.close()
