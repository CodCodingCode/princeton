"""Gmail OAuth sign-in helpers.

Installed-app flow using google-auth-oauthlib. The Streamlit UI calls
`run_sign_in_flow()` once (opens a browser, stores a token on disk) and the
agent/email-send code later calls `load_cached_credentials()` to pick the
token back up — no env vars required.

Paths:
  client secrets  → $NEOVAX_GOOGLE_CLIENT_SECRET or ~/.config/neovax/client_secret.json
  token cache     → $NEOVAX_GMAIL_TOKEN or $NEOANTIGEN_CACHE/gmail_token.json
  sender sidecar  → <token_path>.sender  (plain text with the signed-in email)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
]


def default_client_secret_path() -> Path:
    override = os.environ.get("NEOVAX_GOOGLE_CLIENT_SECRET")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "neovax" / "client_secret.json"


def default_token_path() -> Path:
    override = os.environ.get("NEOVAX_GMAIL_TOKEN")
    if override:
        return Path(override).expanduser()
    cache_root = Path(os.environ.get("NEOANTIGEN_CACHE", Path.home() / ".cache" / "neoantigen"))
    return cache_root / "gmail_token.json"


def _sender_sidecar_path(token_path: Path) -> Path:
    return token_path.with_suffix(token_path.suffix + ".sender")


def _require_oauthlib() -> None:
    try:
        import google_auth_oauthlib  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "google-auth-oauthlib is required for Gmail sign-in. "
            "Install with: pip install google-auth-oauthlib"
        ) from e


def load_cached_credentials() -> Any | None:
    """Load token from disk, refresh if expired. Returns Credentials or None."""
    token_path = default_token_path()
    if not token_path.exists():
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        return None

    try:
        data = json.loads(token_path.read_text())
        creds = Credentials.from_authorized_user_info(data, SCOPES)
    except Exception:
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            try:
                token_path.chmod(0o600)
            except OSError:
                pass
            return creds
        except Exception:
            return None

    return None


def run_sign_in_flow(
    client_secret_path: Path | None = None,
    port: int = 0,
    open_browser: bool = True,
) -> tuple[Any, str]:
    """Run the OAuth installed-app flow. Returns (credentials, sender_email).

    Blocks until the user completes the browser consent. Writes the token
    (mode 0600) and a sidecar file with the discovered sender email.
    """
    _require_oauthlib()
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = client_secret_path or default_client_secret_path()
    if not secrets.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found at {secrets}. "
            "Create a 'Desktop app' OAuth client in Google Cloud Console "
            "and save the JSON there (or set NEOVAX_GOOGLE_CLIENT_SECRET)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(port=port, open_browser=open_browser)

    token_path = default_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    try:
        token_path.chmod(0o600)
    except OSError:
        pass

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    sender_email = profile.get("emailAddress", "")

    sidecar = _sender_sidecar_path(token_path)
    sidecar.write_text(sender_email)
    try:
        sidecar.chmod(0o600)
    except OSError:
        pass

    return creds, sender_email


def get_sender_email() -> str | None:
    """Return the cached signed-in email, or fetch it via getProfile if needed."""
    token_path = default_token_path()
    sidecar = _sender_sidecar_path(token_path)
    if sidecar.exists():
        value = sidecar.read_text().strip()
        if value:
            return value

    creds = load_cached_credentials()
    if creds is None:
        return None

    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "")
        if email:
            sidecar.write_text(email)
            try:
                sidecar.chmod(0o600)
            except OSError:
                pass
            return email
    except Exception:
        return None

    return None


def sign_out() -> None:
    """Delete the cached token + sender sidecar."""
    token_path = default_token_path()
    sidecar = _sender_sidecar_path(token_path)
    for p in (token_path, sidecar):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def is_signed_in() -> bool:
    return load_cached_credentials() is not None
