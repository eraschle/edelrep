import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EmailConfig:
    enabled: bool
    host: str
    user: str
    password_env: str
    folder: str = "INBOX"
    poll_interval_seconds: int = 300
    max_attachment_mb: int = 25
    allowed_senders: tuple[str, ...] = field(default_factory=tuple)


def load_email_config(toml_path: Path) -> EmailConfig:
    """Load the [email] section from a TOML file."""
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    section = data.get("email")
    if section is None:
        raise ValueError("config TOML missing [email] section")
    required = ["host", "user", "password_env"]
    missing = [k for k in required if k not in section]
    if missing:
        raise ValueError(f"email config missing required keys: {missing}")
    return EmailConfig(
        enabled=bool(section.get("enabled", True)),
        host=str(section["host"]),
        user=str(section["user"]),
        password_env=str(section["password_env"]),
        folder=str(section.get("folder", "INBOX")),
        poll_interval_seconds=int(section.get("poll_interval_seconds", 300)),
        max_attachment_mb=int(section.get("max_attachment_mb", 25)),
        allowed_senders=tuple(section.get("allowed_senders", ())),
    )
