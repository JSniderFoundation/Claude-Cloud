"""Runtime configuration, read from environment variables (or a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Settings:
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", "dev-secret-change-me"))
    base_url: str = field(default_factory=lambda: os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/"))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", "./data")))
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", "sqlite:///./data/lienwaiver.db"))
    admin_user: str = field(default_factory=lambda: os.environ.get("ADMIN_USER", "admin"))
    admin_password: str = field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD", ""))
    ap_notify_email: str = field(default_factory=lambda: os.environ.get("AP_NOTIFY_EMAIL", ""))

    email_backend: str = field(default_factory=lambda: os.environ.get("EMAIL_BACKEND", "console"))
    email_from: str = field(default_factory=lambda: os.environ.get("EMAIL_FROM", "lienwaivers@example.com"))
    email_from_name: str = field(default_factory=lambda: os.environ.get("EMAIL_FROM_NAME", "Accounts Payable"))
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", "smtp.office365.com"))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.environ.get("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    graph_tenant_id: str = field(default_factory=lambda: os.environ.get("GRAPH_TENANT_ID", ""))
    graph_client_id: str = field(default_factory=lambda: os.environ.get("GRAPH_CLIENT_ID", ""))
    graph_client_secret: str = field(default_factory=lambda: os.environ.get("GRAPH_CLIENT_SECRET", ""))

    netsuite_backend: str = field(default_factory=lambda: os.environ.get("NETSUITE_BACKEND", "fake"))
    netsuite_account: str = field(default_factory=lambda: os.environ.get("NETSUITE_ACCOUNT", ""))
    netsuite_consumer_key: str = field(default_factory=lambda: os.environ.get("NETSUITE_CONSUMER_KEY", ""))
    netsuite_consumer_secret: str = field(default_factory=lambda: os.environ.get("NETSUITE_CONSUMER_SECRET", ""))
    netsuite_token_id: str = field(default_factory=lambda: os.environ.get("NETSUITE_TOKEN_ID", ""))
    netsuite_token_secret: str = field(default_factory=lambda: os.environ.get("NETSUITE_TOKEN_SECRET", ""))
    netsuite_project_segment: str = field(default_factory=lambda: os.environ.get("NETSUITE_PROJECT_SEGMENT", "csegnsps_seg_projec"))
    netsuite_subsidiary_id: str = field(default_factory=lambda: os.environ.get("NETSUITE_SUBSIDIARY_ID", ""))
    netsuite_sync_start: str = field(default_factory=lambda: os.environ.get("NETSUITE_SYNC_START", "2026-09-01"))
    netsuite_retainage_match: str = field(default_factory=lambda: os.environ.get("NETSUITE_RETAINAGE_MATCH", "Retainage"))
    netsuite_write_holds: bool = field(default_factory=lambda: os.environ.get("NETSUITE_WRITE_HOLDS", "false").lower() in ("1", "true", "yes"))
    netsuite_hold_field: str = field(default_factory=lambda: os.environ.get("NETSUITE_HOLD_FIELD", "custbody_lien_waiver_hold"))
    netsuite_sync_minutes: int = field(default_factory=lambda: int(os.environ.get("NETSUITE_SYNC_MINUTES", "15")))
    timezone: str = field(default_factory=lambda: os.environ.get("TIMEZONE", "America/New_York"))

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdfs"


_load_dotenv(Path(".env"))
settings = Settings()
