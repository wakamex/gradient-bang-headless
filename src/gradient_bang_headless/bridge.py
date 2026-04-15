from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import HeadlessConfig, repo_root


class HeadlessBridgeError(RuntimeError):
    """Raised when the Node bridge returns an error or exits unexpectedly."""

    def __init__(
        self,
        operation: str,
        message: str,
        *,
        payload: Any = None,
        stderr_tail: list[str] | None = None,
    ) -> None:
        super().__init__(f"{operation} failed: {message}")
        self.operation = operation
        self.message = message
        self.payload = payload
        self.stderr_tail = stderr_tail or []


@dataclass(slots=True)
class SessionConnectOptions:
    access_token: str
    functions_url: str
    character_id: str | None = None
    session_id: str | None = None
    connect_timeout_ms: int = 20_000
    request_timeout_ms: int = 20_000
    bypass_tutorial: bool = False
    voice_id: str | None = None
    personality_tone: str | None = None
    character_name: str | None = None

    def as_command(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "functionsUrl": self.functions_url,
            "accessToken": self.access_token,
            "connectTimeoutMs": self.connect_timeout_ms,
            "requestTimeoutMs": self.request_timeout_ms,
        }
        if self.character_id:
            payload["characterId"] = self.character_id
            payload["bypassTutorial"] = self.bypass_tutorial
        if self.session_id:
            payload["sessionId"] = self.session_id
        if self.voice_id:
            payload["voiceId"] = self.voice_id
        if self.personality_tone:
            payload["personalityTone"] = self.personality_tone
        if self.character_name:
            payload["characterName"] = self.character_name
        return payload


class HeadlessBridgeProcess:
    """Async wrapper around the JSON-lines Node SmallWebRTC bridge."""

    def __init__(
        self,
        config: HeadlessConfig,
        *,
        node_binary: str | None = None,
        bridge_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.node_binary = node_binary or config.node_binary or "node"
        self.bridge_dir = Path(
            bridge_dir or config.bridge_dir or (repo_root() / "bridge")
        ).resolve()
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._sequence = 0
        self._closed = False

    async def __aenter__(self) -> "HeadlessBridgeProcess":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @property
    def stderr_tail(self) -> list[str]:
        return list(self._stderr_tail)

    async def start(self) -> None:
        if self._process and self._process.returncode is None:
            return

        controller = self.bridge_dir / "src" / "controller.mjs"
        if not controller.exists():
            raise HeadlessBridgeError(
                "start",
                f"bridge controller not found at {controller}",
            )

        self._process = await asyncio.create_subprocess_exec(
            self.node_binary,
            "src/controller.mjs",
            cwd=str(self.bridge_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._closed = False
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await self.wait_for_event("bridge_ready", timeout=5.0)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._process and self._process.returncode is None:
            try:
                await self._send_command("close", {}, response_timeout=5.0)
            except Exception:
                if self._process.returncode is None:
                    self._process.terminate()
            finally:
                if self._process.returncode is None:
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()

        for task in (self._stdout_task, self._stderr_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._fail_pending("bridge closed")

    async def set_log_level(self, level: str) -> Any:
        return await self._send_command(
            "setLogLevel",
            {"level": level},
            response_timeout=5.0,
        )

    async def status(self) -> Any:
        return await self._send_command("status", {}, response_timeout=5.0)

    async def connect(self, options: SessionConnectOptions) -> Any:
        if not options.character_id and not options.session_id:
            raise HeadlessBridgeError(
                "connect",
                "either character_id or session_id is required",
            )
        response_timeout = max(options.connect_timeout_ms / 1000.0 + 5.0, 10.0)
        return await self._send_command(
            "connect",
            options.as_command(),
            response_timeout=response_timeout,
        )

    async def send_client_message(self, message_type: str, data: dict[str, Any] | None = None) -> Any:
        return await self._send_command(
            "sendClientMessage",
            {"messageType": message_type, "data": data or {}},
            response_timeout=10.0,
        )

    async def send_client_request(
        self,
        message_type: str,
        data: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "messageType": message_type,
            "data": data or {},
        }
        if timeout_ms is not None:
            payload["timeoutMs"] = timeout_ms
        response_timeout = 10.0 + ((timeout_ms or 0) / 1000.0)
        return await self._send_command(
            "sendClientRequest",
            payload,
            response_timeout=response_timeout,
        )

    async def send_text(
        self,
        content: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> Any:
        return await self._send_command(
            "sendText",
            {"content": content, "options": options or {}},
            response_timeout=10.0,
        )

    async def disconnect_bot(self) -> Any:
        return await self._send_command("disconnectBot", {}, response_timeout=5.0)

    async def disconnect(self) -> Any:
        return await self._send_command("disconnect", {}, response_timeout=5.0)

    async def next_event(self, *, timeout: float | None = None) -> dict[str, Any]:
        if timeout is None:
            return await self._events.get()
        return await asyncio.wait_for(self._events.get(), timeout=timeout)

    async def wait_for_event(self, event_name: str, *, timeout: float | None = None) -> dict[str, Any]:
        while True:
            event = await self.next_event(timeout=timeout)
            if event.get("event") == event_name:
                return event

    async def drain_events(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            try:
                items.append(self._events.get_nowait())
            except asyncio.QueueEmpty:
                return items

    async def _send_command(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        response_timeout: float,
    ) -> Any:
        await self.start()

        process = self._process
        if process is None or process.stdin is None:
            raise HeadlessBridgeError(operation, "bridge process is not available")

        self._sequence += 1
        command_id = f"cmd-{self._sequence}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[command_id] = future

        command = {"id": command_id, "op": operation, **payload}
        process.stdin.write((json.dumps(command) + "\n").encode())
        await process.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout=response_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(command_id, None)
            raise HeadlessBridgeError(
                operation,
                f"bridge response timed out after {response_timeout:.1f}s",
                stderr_tail=self.stderr_tail,
            ) from exc

        if not response.get("ok"):
            error = response.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HeadlessBridgeError(
                operation,
                message or "bridge command failed",
                payload=response,
                stderr_tail=self.stderr_tail,
            )

        return response.get("result")

    async def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None

        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            raw = line.decode(errors="replace").strip()
            if not raw:
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await self._events.put({"type": "raw", "line": raw})
                continue

            if message.get("type") == "response":
                command_id = message.get("id")
                future = self._pending.pop(command_id, None)
                if future and not future.done():
                    future.set_result(message)
                continue

            if message.get("type") == "fatal":
                self._fail_pending(message.get("error", {}).get("message", "bridge fatal error"))
                await self._events.put(message)
                continue

            await self._events.put(message)

        self._fail_pending("bridge stdout closed")

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None

        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            self._stderr_tail.append(line.decode(errors="replace").rstrip())

    def _fail_pending(self, message: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    HeadlessBridgeError("bridge", message, stderr_tail=self.stderr_tail)
                )
        self._pending.clear()


import contextlib
