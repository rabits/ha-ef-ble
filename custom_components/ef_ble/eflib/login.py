"""EcoFlow account login helper - region routing and credential probing."""

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiohttp


class Region(StrEnum):
    """Selectable EcoFlow account region"""

    AUTO = "Auto"
    US = "US"
    EU = "EU"
    APAC = "APAC"
    CN = "CN"

    @classmethod
    def _missing_(cls, value: object) -> "Region | None":
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None

    @property
    def base_url(self) -> str | None:
        """API host for this region, or None for AUTO."""
        return _REGION_BASE_URL.get(self)


_REGION_BASE_URL: dict[Region, str] = {
    Region.US: "api.ecoflow.com",
    Region.EU: "api-e.ecoflow.com",
    Region.APAC: "api-a.ecoflow.com",
    Region.CN: "api-cn.ecoflow.com",
}

# AUTO tries these in order for email logins. Phone numbers go straight to CN.
# `api.ecoflow.com` does not route to other regions automatically, so each endpoint
# has to be probed explicitly.
_AUTO_REGION_ORDER: tuple[Region, ...] = (Region.US, Region.EU, Region.APAC)


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
        """
        Resolve an EcoFlow user ID for the given identifier/password/region

        In `Region.AUTO` mode phone numbers go to `CN` and email addresses are tried
        against the regions in `_AUTO_REGION_ORDER` until one succeeds.
        """
        region = Region(region)
        identifier = identifier.strip()
        is_phone = self.is_phone_identifier(identifier)

        if region is Region.CN and not is_phone:
            return LoginResult(error="CN region requires phone number, not email")

        if region is Region.AUTO:
            regions_to_try = (Region.CN,) if is_phone else _AUTO_REGION_ORDER
        else:
            regions_to_try = (region,)

        last_error: str | None = None
        for try_region in regions_to_try:
            assert try_region.base_url is not None
            result = await self._try_login_at(
                try_region.base_url,
                identifier,
                password,
                is_phone=is_phone and try_region is Region.CN,
            )
            if result.user_id is not None:
                return result
            last_error = result.error

        return LoginResult(error=last_error)

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
