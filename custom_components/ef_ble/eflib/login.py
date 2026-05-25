"""EcoFlow account login helper - region routing and credential probing."""

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiohttp


class Region(StrEnum):
    """Selectable EcoFlow API host"""

    AUTO = "auto"
    API = "api"
    API_E = "api-e"
    API_A = "api-a"
    API_J = "api-j"
    API_R = "api-r"
    API_CN = "api-cn"

    @classmethod
    def _missing_(cls, value: object) -> "Region | None":
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None

    @property
    def base_url(self) -> str | None:
        """Hostname for this region, or None for `AUTO`"""
        if self is Region.AUTO:
            return None
        return f"{self.value}.ecoflow.com"


@dataclass(frozen=True)
class LoginResult:
    user_id: str | None = None
    error: str | None = None


class EcoFlowLogin:
    """Resolve an EcoFlow user ID from credentials and a region selection"""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    @staticmethod
    def is_phone_identifier(identifier: str) -> bool:
        """Return True if identifier looks like an E.164 phone number"""
        digits = identifier.removeprefix("+").replace(" ", "")
        return digits.isdigit() and 6 <= len(digits) <= 15

    async def login(
        self,
        identifier: str,
        password: str,
        region: Region | str,
    ) -> LoginResult:
        """Resolve an EcoFlow user ID for the given identifier/password/region"""
        region = Region(region)
        identifier = identifier.strip()
        is_phone = self.is_phone_identifier(identifier)

        if region is Region.API_CN and not is_phone:
            return LoginResult(error="api-cn requires phone number, not email")

        if region is Region.AUTO:
            region = Region.API_CN if is_phone else Region.API

        assert region.base_url is not None
        return await self._try_login_at(
            region.base_url,
            identifier,
            password,
            is_phone=is_phone and region is Region.API_CN,
        )

    async def _try_login_at(
        self,
        base_url: str,
        identifier: str,
        password: str,
        *,
        is_phone: bool,
    ) -> LoginResult:
        json_payload: dict[str, Any] = {
            "scene": "IOT_APP",
            "appVersion": "1.0.0",
            "password": base64.b64encode(password.encode()).decode(),
            "oauth": {"bundleId": "com.ef.EcoFlow"},
            "userType": "ECOFLOW",
        }
        if is_phone:
            json_payload["phone"] = identifier.removeprefix("+86")
        else:
            json_payload["email"] = identifier

        async with self._session.post(
            url=f"https://{base_url}/auth/login",
            json=json_payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as response:
            if not response.ok:
                return LoginResult(
                    error=(
                        f"Login failed with status code {response.status}: "
                        f"{response.reason}"
                    )
                )

            result_json = await response.json()
            if result_json["code"] != "0":
                return LoginResult(error=f"Login failed: '{result_json['message']}'")

            return LoginResult(user_id=result_json["data"]["user"]["userId"])
