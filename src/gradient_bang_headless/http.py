from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from .config import HeadlessConfig


class HeadlessApiError(RuntimeError):
    """Raised when an edge-function call fails."""

    def __init__(
        self,
        endpoint: str,
        status_code: int,
        message: str,
        *,
        payload: Any = None,
    ) -> None:
        super().__init__(f"{endpoint} failed with status {status_code}: {message}")
        self.endpoint = endpoint
        self.status_code = status_code
        self.message = message
        self.payload = payload


@dataclass(slots=True)
class EventScope:
    character_ids: list[str]
    ship_ids: list[str]
    corp_id: str | None = None


class HeadlessApiClient:
    """Small async client for control-plane and gameplay edge-function calls."""

    def __init__(self, config: HeadlessConfig, *, timeout: float = 30.0) -> None:
        self.config = config
        self._http = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "HeadlessApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    def _endpoint_url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        cleaned = endpoint.lstrip("/")
        return f"{self.config.functions_url}/{cleaned}"

    def _headers(
        self,
        *,
        access_token: str | None = None,
        api_token: str | None = None,
        require_api_token: bool = False,
    ) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        bearer = access_token or self.config.access_token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        token = api_token or self.config.api_token
        if token:
            headers["X-API-Token"] = token
        elif require_api_token:
            raise HeadlessApiError("headers", 0, "missing GB_API_TOKEN / EDGE_API_TOKEN")
        return headers

    async def request(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        payload: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        access_token: str | None = None,
        api_token: str | None = None,
        require_api_token: bool = False,
    ) -> Any:
        url = self._endpoint_url(endpoint)
        headers = self._headers(
            access_token=access_token,
            api_token=api_token,
            require_api_token=require_api_token,
        )
        response = await self._http.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=dict(payload) if payload is not None and method.upper() != "GET" else None,
        )

        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}

        if response.is_error:
            message = _extract_error_message(data) or response.text or "request failed"
            raise HeadlessApiError(endpoint, response.status_code, message, payload=data)

        if isinstance(data, Mapping) and data.get("success") is False:
            message = _extract_error_message(data) or "request failed"
            status = _coerce_status(data.get("status")) or response.status_code or 400
            raise HeadlessApiError(endpoint, status, message, payload=data)

        return data

    async def login(self, email: str, password: str) -> Any:
        return await self.request("login", payload={"email": email, "password": password})

    async def character_list(self, *, access_token: str | None = None) -> Any:
        return await self.request(
            "user_character_list",
            access_token=access_token,
        )

    async def character_create(
        self,
        name: str,
        *,
        access_token: str | None = None,
    ) -> Any:
        return await self.request(
            "user_character_create",
            payload={"name": name},
            access_token=access_token,
        )

    async def call_gameplay(
        self,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
        *,
        character_id: str | None = None,
        actor_character_id: str | None = None,
        api_token: str | None = None,
    ) -> Any:
        body = dict(payload or {})
        effective_character_id = character_id or self.config.character_id
        effective_actor_id = actor_character_id or self.config.actor_character_id

        if effective_character_id and "character_id" not in body:
            body["character_id"] = effective_character_id
        if effective_actor_id and "actor_character_id" not in body:
            body["actor_character_id"] = effective_actor_id

        return await self.request(
            endpoint,
            payload=body,
            api_token=api_token,
            require_api_token=True,
        )

    async def events_since(
        self,
        *,
        character_ids: list[str] | None = None,
        ship_ids: list[str] | None = None,
        corp_id: str | None = None,
        since_event_id: int | None = None,
        limit: int | None = None,
        initial_only: bool = False,
        api_token: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {}
        effective_character_ids = character_ids or (
            [self.config.character_id] if self.config.character_id else []
        )
        effective_ship_ids = ship_ids or []

        if effective_character_ids:
            if len(effective_character_ids) == 1:
                body["character_id"] = effective_character_ids[0]
            body["character_ids"] = effective_character_ids
        if effective_ship_ids:
            body["ship_ids"] = effective_ship_ids
        if corp_id:
            body["corp_id"] = corp_id
        if since_event_id is not None:
            body["since_event_id"] = since_event_id
        if limit is not None:
            body["limit"] = limit
        if initial_only:
            body["initial_only"] = True

        return await self.request(
            "events_since",
            payload=body,
            api_token=api_token,
            require_api_token=True,
        )

    async def follow_events(
        self,
        *,
        scope: EventScope,
        since_event_id: int | None = None,
        limit: int = 100,
        poll_interval: float = 1.0,
        api_token: str | None = None,
    ):
        cursor = since_event_id
        if cursor is None:
            seed = await self.events_since(
                character_ids=scope.character_ids,
                ship_ids=scope.ship_ids,
                corp_id=scope.corp_id,
                initial_only=True,
                api_token=api_token,
            )
            last_event_id = seed.get("last_event_id")
            cursor = last_event_id if isinstance(last_event_id, int) else 0

        while True:
            response = await self.events_since(
                character_ids=scope.character_ids,
                ship_ids=scope.ship_ids,
                corp_id=scope.corp_id,
                since_event_id=cursor,
                limit=limit,
                api_token=api_token,
            )
            events = response.get("events") if isinstance(response, Mapping) else []
            if isinstance(events, list):
                for event in events:
                    yield event

            last_event_id = response.get("last_event_id") if isinstance(response, Mapping) else None
            if isinstance(last_event_id, int):
                cursor = last_event_id

            await asyncio.sleep(poll_interval)


def _extract_error_message(data: Any) -> str | None:
    if isinstance(data, Mapping):
        error = data.get("error")
        if isinstance(error, str) and error.strip():
            return error
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return message
        code = data.get("code")
        if isinstance(code, str) and code.strip():
            return code
    elif isinstance(data, str) and data.strip():
        return data
    return None


def _coerce_status(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)
