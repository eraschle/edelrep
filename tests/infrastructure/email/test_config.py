from pathlib import Path

import pytest

from edelrep.infrastructure.email.config import EmailConfig, load_email_config


def test_loads_minimal_config(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
host = "imap.example.com"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
""",
        encoding="utf-8",
    )
    config = load_email_config(toml)
    assert config.host == "imap.example.com"
    assert config.user == "werkstatt@firma.ch"
    assert config.password_env == "EMAIL_PASSWORD"
    # Defaults
    assert config.enabled is True
    assert config.folder == "INBOX"
    assert config.poll_interval_seconds == 300
    assert config.max_attachment_mb == 25
    assert config.allowed_senders == ()


def test_loads_full_config(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
enabled = true
host = "imap.example.com"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
folder = "Werkstatt"
poll_interval_seconds = 600
max_attachment_mb = 50
allowed_senders = ["*@firma.ch", "kunde@partner.ch"]
""",
        encoding="utf-8",
    )
    config = load_email_config(toml)
    assert config.folder == "Werkstatt"
    assert config.poll_interval_seconds == 600
    assert config.max_attachment_mb == 50
    assert config.allowed_senders == ("*@firma.ch", "kunde@partner.ch")


def test_disabled_config(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
enabled = false
host = "imap.example.com"
user = "werkstatt@firma.ch"
password_env = "EMAIL_PASSWORD"
""",
        encoding="utf-8",
    )
    config = load_email_config(toml)
    assert config.enabled is False


def test_missing_required_host_raises(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
user = "u"
password_env = "EMAIL_PASSWORD"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="host"):
        load_email_config(toml)


def test_missing_required_user_raises(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
host = "imap.example.com"
password_env = "EMAIL_PASSWORD"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="user"):
        load_email_config(toml)


def test_missing_required_password_env_raises(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
[email]
host = "imap.example.com"
user = "u"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="password_env"):
        load_email_config(toml)


def test_email_config_is_frozen() -> None:
    config = EmailConfig(
        enabled=True,
        host="h",
        user="u",
        password_env="P",
    )
    with pytest.raises(AttributeError):
        config.host = "other"  # type: ignore[misc]


def test_missing_email_section_raises(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text("# no email section\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_email_config(toml)
