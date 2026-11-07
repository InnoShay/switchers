"""Switch HTTP client (SPEC §11.2): `SwitchHTTPClient` implements the `SwitchHTTP` protocol."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from roomservice.contracts.switch import OpError, SwitchHTTP
from roomservice.log import get_logger, redact

log = get_logger("switch.http")

RETRY_DELAYS: tuple[float, ...] = (0.3, 1.0, 2.0)

# SwitchHTTPClient structurally implements SwitchHTTP (Protocol); the import documents that.
__all__ = ["RETRY_DELAYS", "SwitchHTTP", "SwitchHTTPClient", "registration_body"]


def registration_body(
    name: str, display_name: str, description: str, connector_type: str, overwrite: bool = False
) -> dict:
    """Body of `POST /agents` (SPEC §11.3)."""
    body: dict[str, Any] = {
        "name": name,
        "display_name": display_name,
        "description": description,
        "connector_type": connector_type,
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }
    if overwrite:
        body["overwrite"] = True
    return body


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return redact(resp.text[:300]) or resp.reason_phrase
    if isinstance(data, dict):
        for key in ("detail", "error", "message"):
            if data.get(key):
                return redact(str(data[key]))[:300]
    return redact(str(data))[:300]


class SwitchHTTPClient:
    """Async client for the Switch agent HTTP API.

    Bearer = the agent API key, except `register` which uses the registration key.
    Retries network errors and 5xx (0.3 s, 1 s, 2 s); never retries 4xx.
    """

    def __init__(
        self,
        base_url: str,
        agent_id: str | None = None,
        api_key: str | None = None,
        registration_key: str | None = None,
        *,
        timeout: float = 15,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.agent_id = agent_id
        self._api_key = api_key
        self._registration_key = registration_key
        self._retry_delays = retry_delays
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- plumbing -----------------------------------------------------------------------

    def _agent_path(self, suffix: str) -> str:
        if not self.agent_id:
            raise RuntimeError("SwitchHTTPClient has no agent_id; register first")
        return f"/agents/{self.agent_id}{suffix}"

    def _auth(self, key: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        key: str | None,
        headers: dict[str, str] | None = None,
        retry: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        hdrs = {**self._auth(key), **(headers or {})}
        delays = self._retry_delays if retry else ()
        for attempt in range(len(delays) + 1):
            try:
                resp = await self._client.request(method, path, headers=hdrs, **kwargs)
            except httpx.TransportError as e:
                if attempt >= len(delays):
                    raise
                log.warning("%s %s network error (%s); retry %d", method, path, e, attempt + 1)
            else:
                if resp.status_code < 500 or attempt >= len(delays):
                    return resp
                log.warning("%s %s -> %d; retry %d", method, path, resp.status_code, attempt + 1)
            await asyncio.sleep(delays[attempt])
        raise AssertionError("unreachable")  # pragma: no cover

    def _raise_for_error(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise OpError(resp.status_code, _detail(resp))

    # -- SwitchHTTP ---------------------------------------------------------------------

    async def health(self) -> bool:
        try:
            resp = await self._request("GET", "/health", key=None, retry=False)
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    async def register(
        self,
        name: str,
        display_name: str,
        description: str,
        connector_type: str,
        overwrite: bool = False,
    ) -> tuple[str, str]:
        body = registration_body(name, display_name, description, connector_type, overwrite)
        resp = await self._request("POST", "/agents", key=self._registration_key, json=body)
        if resp.status_code == 409:
            raise OpError(409, "exists")
        self._raise_for_error(resp)
        data = resp.json()
        return data["id"], data["api_key"]

    async def list_ops(self) -> dict:
        resp = await self._request("GET", self._agent_path("/ops"), key=self._api_key)
        self._raise_for_error(resp)
        return resp.json()

    async def op(self, name: str, args: dict, conn_id: str | None = None) -> Any:
        payload = {k: v for k, v in (args or {}).items() if v is not None}
        headers = {"X-Switch-Connection-Id": conn_id} if conn_id else None
        resp = await self._request(
            "POST", self._agent_path(f"/ops/{name}"), key=self._api_key, headers=headers,
            json=payload,
        )  # fmt: skip
        self._raise_for_error(resp)
        if not resp.content:
            return None
        data = resp.json()
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    async def post(self, room_id: str, content: str) -> str:
        resp = await self._request(
            "POST",
            self._agent_path("/message"),
            key=self._api_key,
            json={"room_id": room_id, "content": content},
        )
        self._raise_for_error(resp)
        return str(resp.json().get("event_id", ""))

    async def upload(
        self,
        room_id: str,
        files: list[tuple[str, bytes, str]],
        caption: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        field = "file" if len(files) == 1 else "files"
        parts = [(field, (fname, data, mime)) for fname, data, mime in files]
        form = {k: v for k, v in (("caption", caption), ("thread_id", thread_id)) if v is not None}
        resp = await self._request(
            "POST",
            self._agent_path(f"/rooms/{room_id}/media"),
            key=self._api_key,
            files=parts,
            data=form,
        )
        self._raise_for_error(resp)
        return resp.json()

    async def typing(self, room_id: str, on: bool) -> None:
        try:
            await self._request(
                "POST",
                self._agent_path("/typing"),
                key=self._api_key,
                retry=False,
                json={"room_id": room_id, "is_typing": on},
            )
        except Exception as e:  # typing is cosmetic: swallow everything
            log.debug("typing failed: %s", e)

    async def renew_lease(self, conn_id: str) -> bool:
        try:
            resp = await self._request(
                "POST",
                self._agent_path("/leases/renew"),
                key=self._api_key,
                headers={"X-Switch-Connection-Id": conn_id},
            )
        except httpx.HTTPError:
            return False
        return 200 <= resp.status_code < 300
