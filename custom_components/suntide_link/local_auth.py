"""The Link's local access token: small pure helpers, no Home Assistant imports.

From firmware 0.17.0 the Link answers its local REST only with
``Authorization: Bearer <token>``. The token is issued by the Suntide cloud
when the household turns on "Home Assistant and local access" for the Link
in the Suntide app. The app shows it; a Suntide cloud token can also read it
from ``GET /api/ext/v1/links/{deviceId}/local``.

The token is a credential: nothing here logs it, and nothing that fails
repeats it back in an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

# Outcomes of the cloud read, also used as config flow error keys.
CLOUD_OK = "ok"
CLOUD_LOCAL_ACCESS_OFF = "local_access_off"
CLOUD_LINK_NOT_FOUND = "link_not_in_account"
CLOUD_TOKEN_REJECTED = "invalid_cloud_token"
CLOUD_UNAVAILABLE = "cloud_unreachable"


def normalise_token(raw: str | None) -> str | None:
    """Tidy a pasted token; None when blank.

    The app shows 32 lower-case hex characters. People paste with spaces,
    line breaks or capitals, so those are forgiven here.
    """
    if raw is None:
        return None
    token = re.sub(r"\s+", "", raw).lower()
    return token or None


def is_valid_token(token: str | None) -> bool:
    return bool(token) and bool(_TOKEN_RE.match(token))


def local_headers(token: str | None) -> dict[str, str]:
    """Headers for the Link's local REST; none when no token is configured."""
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def local_url(host: str, path: str) -> str:
    return f"http://{host}{path}"


def cloud_local_path(device_id: str) -> str:
    return f"/api/ext/v1/links/{device_id}/local"


def looks_like_device_id(device_id: str | None) -> bool:
    """A Link id as the cloud knows it (e.g. link-0002), not an IP address.

    The manual path used to store the host as the device id; those entries
    cannot ask the cloud for a token.
    """
    if not device_id:
        return False
    # Letters, digits, hyphens and underscores only: an address (dots) or
    # anything that could change the cloud URL's path is refused.
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", device_id))


@dataclass(frozen=True)
class CloudLocalAccess:
    outcome: str
    token: str | None = None

    def __repr__(self) -> str:  # never print the token
        return f"CloudLocalAccess(outcome={self.outcome!r}, token={'set' if self.token else None})"


def parse_cloud_local(status: int, body: Any) -> CloudLocalAccess:
    """Read the cloud's answer to ``GET /api/ext/v1/links/{id}/local``.

    200 ``{"enabled": true, "token": "..."}`` is the only success. 200 with
    ``enabled: false`` means local access is off in the app for this Link.
    404 means the Link is not in the token's household (or not claimed).
    401 means the cloud token is unknown or revoked. Anything else (429, 5xx,
    a lock refusal) is treated as the cloud being unavailable for now.
    """
    if status == 401:
        return CloudLocalAccess(CLOUD_TOKEN_REJECTED)
    if status == 404:
        return CloudLocalAccess(CLOUD_LINK_NOT_FOUND)
    if status != 200 or not isinstance(body, dict):
        return CloudLocalAccess(CLOUD_UNAVAILABLE)
    if body.get("enabled") is not True:
        return CloudLocalAccess(CLOUD_LOCAL_ACCESS_OFF)
    token = normalise_token(body.get("token") if isinstance(body.get("token"), str) else None)
    if not is_valid_token(token):
        return CloudLocalAccess(CLOUD_UNAVAILABLE)
    return CloudLocalAccess(CLOUD_OK, token)


# Outcomes of probing the Link itself, also config flow error keys.
LINK_OK = "ok"
LINK_TOKEN_REJECTED = "invalid_local_token"
LINK_TOKEN_REQUIRED = "local_token_required"
LINK_UNREACHABLE = "cannot_connect"


def classify_link_status(status: int, token: str | None) -> str:
    """What a status code from ``/api/v1/state`` means.

    200 is fine with or without a token: firmware before 0.17.0 ignores the
    header. 401 means the token is wrong, or that one is needed.
    """
    if status == 200:
        return LINK_OK
    if status == 401:
        return LINK_TOKEN_REJECTED if token else LINK_TOKEN_REQUIRED
    return LINK_UNREACHABLE


# ---- Network calls (aiohttp session supplied by the caller) ----------------


async def fetch_cloud_local(session, base: str, cloud_token: str, device_id: str) -> CloudLocalAccess:
    """Ask the Suntide cloud for this Link's local access token."""
    import asyncio

    import aiohttp

    try:
        async with asyncio.timeout(15):
            resp = await session.get(
                f"{base}{cloud_local_path(device_id)}",
                headers={"Authorization": f"Bearer {cloud_token}"},
            )
            body: Any = None
            if resp.status == 200:
                try:
                    body = await resp.json()
                except (aiohttp.ContentTypeError, ValueError):
                    body = None
            return parse_cloud_local(resp.status, body)
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
        return CloudLocalAccess(CLOUD_UNAVAILABLE)


async def probe_link(session, host: str, token: str | None) -> tuple[str, str | None]:
    """Call ``/api/v1/state`` as the coordinator will; return (outcome, deviceId)."""
    import asyncio

    import aiohttp

    try:
        async with asyncio.timeout(5):
            resp = await session.get(
                local_url(host, "/api/v1/state"), headers=local_headers(token)
            )
            outcome = classify_link_status(resp.status, token)
            device_id = None
            if outcome == LINK_OK:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
                if isinstance(body, dict) and isinstance(body.get("deviceId"), str):
                    device_id = body["deviceId"] or None
            return outcome, device_id
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
        return LINK_UNREACHABLE, None
