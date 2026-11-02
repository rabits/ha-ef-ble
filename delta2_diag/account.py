"""EcoFlow user ID: the only account detail BLE authentication needs"""

import contextlib
import os
import sys
from pathlib import Path

import aiohttp

from custom_components.ef_ble.eflib.login import EcoFlowLogin, Region

USER_ID_ENV = "EF_USER_ID"


class AccountError(Exception):
    pass


def user_id_path() -> Path:
    """Per-user config location, outside the repository so it can't be committed"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "delta2-diag" / "user_id"


def load_user_id() -> str | None:
    if user_id := os.environ.get(USER_ID_ENV, "").strip():
        return user_id
    try:
        return user_id_path().read_text(encoding="ascii").strip() or None
    except FileNotFoundError:
        return None


def save_user_id(user_id: str) -> Path:
    path = user_id_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(user_id, encoding="ascii")
    # Only takes effect on POSIX; on Windows the file sits in the user's own profile
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return path


async def fetch_user_id(email: str, password: str, region: Region) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            result = await EcoFlowLogin(session).login(email, password, region)
        except aiohttp.ClientError as e:
            raise AccountError(f"could not reach EcoFlow: {e}") from e

    if result.user_id is None:
        raise AccountError(result.error or "EcoFlow returned no User ID")
    return str(result.user_id)
