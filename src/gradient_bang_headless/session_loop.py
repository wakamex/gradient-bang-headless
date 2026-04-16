from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .bridge import HeadlessBridgeError, HeadlessBridgeProcess


@dataclass(slots=True)
class LoopTargets:
    credits: int | None = None
    sector: int | None = None
    ship_type: str | None = None
    quest_code: str | None = None
    quest_step_name: str | None = None
    corp_ship_count: int | None = None
    corp_ship_type: str | None = None
    corp_ship_type_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "credits": self.credits,
            "sector": self.sector,
            "ship_type": self.ship_type,
            "quest_code": self.quest_code,
            "quest_step_name": self.quest_step_name,
            "corp_ship_count": self.corp_ship_count,
            "corp_ship_type": self.corp_ship_type,
            "corp_ship_type_count": self.corp_ship_type_count,
        }

    def active(self) -> bool:
        return any(value is not None for value in self.as_dict().values())


@dataclass(slots=True)
class SessionLoopOptions:
    objective: str
    bootstrap_timeout_seconds: float = 10.0
    duration_seconds: float = 300.0
    forever: bool = False
    send_start: bool = True
    status_interval_seconds: float = 20.0
    idle_reprompt_seconds: float = 45.0
    max_reprompts: int = 2
    reprompt_prefix: str = "Continue the current objective and act on it:"
    sample_limit: int = 40
    targets: LoopTargets = field(default_factory=LoopTargets)


class SessionStateTracker:
    def __init__(self, *, sample_limit: int = 40) -> None:
        self.status: dict[str, Any] | None = None
        self.ports: dict[str, Any] | None = None
        self.map_region: dict[str, Any] | None = None
        self.task_history: list[dict[str, Any]] | None = None
        self.task_events: dict[str, Any] | None = None
        self.chat_history: list[dict[str, Any]] | None = None
        self.ships: list[dict[str, Any]] | None = None
        self.ship_definitions: list[dict[str, Any]] | None = None
        self.corporation: dict[str, Any] | None = None
        self.quests: dict[str, dict[str, Any]] = {}
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=sample_limit)
        self.recent_bot_messages: deque[dict[str, Any]] = deque(maxlen=sample_limit)
        self.progress_count = 0
        self._signature = self._signature_text()

    def apply_event(self, event: dict[str, Any]) -> dict[str, Any]:
        summary = _summarize_bridge_event(event)
        if summary is not None:
            self.recent_events.append(summary)

        event_name = event.get("event")
        if event_name in {"bot_output", "bot_llm_text", "bot_tts_text"}:
            message = _extract_text_payload(event.get("data"))
            if message:
                self.recent_bot_messages.append(
                    {
                        "event": event_name,
                        "text": message,
                    }
                )

        server_message = _extract_server_message(event)
        if not isinstance(server_message, dict):
            return {"progress": False}

        if server_message.get("frame_type") != "event":
            return {"progress": False}

        server_event_name = server_message.get("event")
        payload = server_message.get("payload")
        if not isinstance(server_event_name, str):
            return {"progress": False}

        self._apply_server_event(server_event_name, payload)
        new_signature = self._signature_text()
        progress = new_signature != self._signature
        if progress:
            self.progress_count += 1
            self._signature = new_signature

        return {
            "progress": progress,
            "server_event": server_event_name,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "status": _status_summary(self.status),
            "quests": sorted(
                (_quest_summary(quest) for quest in self.quests.values()),
                key=lambda item: (str(item.get("code") or ""), str(item.get("quest_id") or "")),
            ),
            "ports": _ports_summary(self.ports),
            "map": _map_summary(self.map_region),
            "task_history": _task_history_summary(self.task_history),
            "task_events": _task_events_summary(self.task_events),
            "chat_history_count": len(self.chat_history or []),
            "ships_count": len(self.ships or []),
            "ship_definitions_count": len(self.ship_definitions or []),
            "corporation": _corporation_summary(self.corporation),
            "progress_count": self.progress_count,
            "recent_events": list(self.recent_events),
            "recent_bot_messages": list(self.recent_bot_messages),
        }

    def evaluate_targets(self, targets: LoopTargets) -> dict[str, bool]:
        results: dict[str, bool] = {}
        status = _status_summary(self.status)

        if targets.credits is not None:
            credits = status.get("ship_credits")
            results["credits"] = isinstance(credits, int) and credits >= targets.credits

        if targets.sector is not None:
            sector = status.get("sector_id")
            results["sector"] = isinstance(sector, int) and sector == targets.sector

        if targets.ship_type is not None:
            ship_type = status.get("ship_type")
            results["ship_type"] = ship_type == targets.ship_type

        if targets.quest_code is not None:
            quest = self.quests.get(targets.quest_code)
            results["quest_code"] = quest is not None
            if targets.quest_step_name is not None:
                step_name = None
                if isinstance(quest, dict):
                    current_step = quest.get("current_step")
                    if isinstance(current_step, dict):
                        step_name = current_step.get("name")
                results["quest_step_name"] = step_name == targets.quest_step_name
        elif targets.quest_step_name is not None:
            results["quest_step_name"] = any(
                _quest_summary(quest).get("current_step_name") == targets.quest_step_name
                for quest in self.quests.values()
            )

        corporation = self.corporation if isinstance(self.corporation, dict) else {}
        corporation_ships = corporation.get("ships") if isinstance(corporation, dict) else None
        active_corp_ships = (
            [ship for ship in corporation_ships if isinstance(ship, dict)]
            if isinstance(corporation_ships, list)
            else []
        )

        if targets.corp_ship_count is not None:
            results["corp_ship_count"] = len(active_corp_ships) >= targets.corp_ship_count

        if targets.corp_ship_type is not None:
            matching_corp_ships = [
                ship
                for ship in active_corp_ships
                if ship.get("ship_type") == targets.corp_ship_type
            ]
            required_count = targets.corp_ship_type_count or 1
            results["corp_ship_type"] = len(matching_corp_ships) >= required_count
            if targets.corp_ship_type_count is not None:
                results["corp_ship_type_count"] = len(matching_corp_ships) >= targets.corp_ship_type_count

        return results

    def targets_met(self, targets: LoopTargets) -> bool:
        evaluations = self.evaluate_targets(targets)
        return bool(evaluations) and all(evaluations.values())

    def _apply_server_event(self, event_name: str, payload: Any) -> None:
        if event_name == "status.snapshot" and isinstance(payload, dict):
            self.status = payload
            return
        if event_name == "quest.status" and isinstance(payload, dict):
            quests = payload.get("quests")
            if isinstance(quests, list):
                for quest in quests:
                    if not isinstance(quest, dict):
                        continue
                    key = str(quest.get("code") or quest.get("quest_id") or len(self.quests))
                    self.quests[key] = quest
                return
            key = str(payload.get("code") or payload.get("quest_id") or len(self.quests))
            self.quests[key] = payload
            return
        if event_name == "ports.list" and isinstance(payload, dict):
            self.ports = payload
            return
        if event_name in {"map.region", "map.local"} and isinstance(payload, dict):
            self.map_region = payload
            return
        if event_name == "task.history" and isinstance(payload, dict):
            tasks = payload.get("tasks")
            if isinstance(tasks, list):
                self.task_history = [item for item in tasks if isinstance(item, dict)]
            return
        if event_name == "event.query" and isinstance(payload, dict):
            self.task_events = payload
            return
        if event_name == "chat.history" and isinstance(payload, dict):
            messages = payload.get("messages")
            if isinstance(messages, list):
                self.chat_history = [item for item in messages if isinstance(item, dict)]
            return
        if event_name == "ships.list" and isinstance(payload, dict):
            ships = payload.get("ships")
            if isinstance(ships, list):
                self.ships = [item for item in ships if isinstance(item, dict)]
            return
        if event_name == "ship.definitions" and isinstance(payload, dict):
            definitions = payload.get("definitions")
            if isinstance(definitions, list):
                self.ship_definitions = [item for item in definitions if isinstance(item, dict)]
            return
        if event_name == "corporation.data" and isinstance(payload, dict):
            corporation = payload.get("corporation")
            if isinstance(corporation, dict):
                self.corporation = corporation
            else:
                self.corporation = None
            return
        if event_name == "corporation_info" and isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict):
                corporation = result.get("corporation")
                if isinstance(corporation, dict):
                    self.corporation = corporation

    def _signature_text(self) -> str:
        return json.dumps(
            {
                "status": _status_summary(self.status),
                "quests": sorted(
                    (_quest_summary(quest) for quest in self.quests.values()),
                    key=lambda item: (str(item.get("code") or ""), str(item.get("quest_id") or "")),
                ),
                "task_history": _task_history_summary(self.task_history),
                "corporation": _corporation_summary(self.corporation),
            },
            sort_keys=True,
        )


class SessionLoopRunner:
    def __init__(self, bridge: HeadlessBridgeProcess) -> None:
        self.bridge = bridge

    async def run(self, options: SessionLoopOptions) -> dict[str, Any]:
        tracker = SessionStateTracker(sample_limit=options.sample_limit)
        prompts_sent: list[str] = []
        status_poll_errors: list[str] = []

        await self._drain_pending(tracker)

        if options.send_start:
            await self.bridge.session_start()

        await self._collect_for(
            tracker,
            timeout=options.bootstrap_timeout_seconds,
        )

        if tracker.status is None:
            try:
                status_result = await self.bridge.get_my_status(
                    timeout=max(10.0, options.bootstrap_timeout_seconds),
                )
                tracker.apply_event(status_result["server_event"])
            except HeadlessBridgeError as exc:
                status_poll_errors.append(str(exc))

        initial_summary = tracker.summary()

        await self.bridge.user_text_input(options.objective)
        prompts_sent.append(options.objective)

        started_at = asyncio.get_running_loop().time()
        last_prompt_at = started_at
        last_progress_at = started_at
        last_status_poll_at = started_at
        reprompt_count = 0

        stop_reason = "duration_elapsed"
        while True:
            if tracker.targets_met(options.targets):
                stop_reason = "targets_met"
                break

            now = asyncio.get_running_loop().time()
            if not options.forever and now >= started_at + options.duration_seconds:
                stop_reason = "duration_elapsed"
                break

            timeout = _next_timeout(
                now=now,
                started_at=started_at,
                duration_seconds=options.duration_seconds,
                forever=options.forever,
                status_interval_seconds=options.status_interval_seconds,
                last_status_poll_at=last_status_poll_at,
                idle_reprompt_seconds=options.idle_reprompt_seconds,
                last_action_at=max(last_prompt_at, last_progress_at),
            )

            try:
                event = await self.bridge.next_event(timeout=timeout)
            except asyncio.TimeoutError:
                event = None

            if event is not None:
                result = tracker.apply_event(event)
                if result.get("progress"):
                    last_progress_at = asyncio.get_running_loop().time()
                continue

            now = asyncio.get_running_loop().time()
            if (
                options.status_interval_seconds > 0
                and now - last_status_poll_at >= options.status_interval_seconds
            ):
                last_status_poll_at = now
                try:
                    status_result = await self.bridge.get_my_status(
                        timeout=max(10.0, options.status_interval_seconds + 5.0),
                    )
                    result = tracker.apply_event(status_result["server_event"])
                    if result.get("progress"):
                        last_progress_at = asyncio.get_running_loop().time()
                except HeadlessBridgeError as exc:
                    status_poll_errors.append(str(exc))
                continue

            if (
                options.idle_reprompt_seconds > 0
                and now - max(last_prompt_at, last_progress_at) >= options.idle_reprompt_seconds
            ):
                if not options.forever and reprompt_count >= options.max_reprompts:
                    stop_reason = "idle_reprompt_limit"
                    break

                reprompt = f"{options.reprompt_prefix} {options.objective}".strip()
                await self.bridge.user_text_input(reprompt)
                prompts_sent.append(reprompt)
                reprompt_count += 1
                last_prompt_at = asyncio.get_running_loop().time()
                continue

        return {
            "success": stop_reason == "targets_met",
            "stop_reason": stop_reason,
            "objective": options.objective,
            "targets": options.targets.as_dict(),
            "targets_met": tracker.evaluate_targets(options.targets),
            "reprompt_count": reprompt_count,
            "prompts_sent": prompts_sent,
            "status_poll_errors": status_poll_errors,
            "initial_state": initial_summary,
            "final_state": tracker.summary(),
        }

    async def _collect_for(
        self,
        tracker: SessionStateTracker,
        *,
        timeout: float,
    ) -> None:
        if timeout <= 0:
            await self._drain_pending(tracker)
            return

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                event = await self.bridge.next_event(timeout=remaining)
            except asyncio.TimeoutError:
                break
            tracker.apply_event(event)

    async def _drain_pending(self, tracker: SessionStateTracker) -> None:
        for event in await self.bridge.drain_events():
            tracker.apply_event(event)


def _extract_server_message(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event") != "server_message":
        return None
    data = event.get("data")
    return data if isinstance(data, dict) else None


def _extract_text_payload(payload: Any) -> str | None:
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if isinstance(payload, dict):
        for key in ("text", "message", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _status_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    player = payload.get("player")
    ship = payload.get("ship")
    sector = payload.get("sector")
    port = sector.get("port") if isinstance(sector, dict) else None

    return {
        "player_name": player.get("name") if isinstance(player, dict) else None,
        "sector_id": sector.get("id") if isinstance(sector, dict) else None,
        "sector_region": sector.get("region") if isinstance(sector, dict) else None,
        "ship_id": ship.get("ship_id") if isinstance(ship, dict) else None,
        "ship_name": ship.get("ship_name") if isinstance(ship, dict) else None,
        "ship_type": ship.get("ship_type") if isinstance(ship, dict) else None,
        "ship_credits": ship.get("credits") if isinstance(ship, dict) else None,
        "cargo": ship.get("cargo") if isinstance(ship, dict) else None,
        "warp_power": ship.get("warp_power") if isinstance(ship, dict) else None,
        "fighters": ship.get("fighters") if isinstance(ship, dict) else None,
        "port_id": port.get("id") if isinstance(port, dict) else None,
        "port_code": port.get("code") if isinstance(port, dict) else None,
        "port_mega": port.get("mega") if isinstance(port, dict) else None,
    }


def _quest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    current_step = payload.get("current_step")
    if not isinstance(current_step, dict):
        current_step = {}

    return {
        "quest_id": payload.get("quest_id"),
        "code": payload.get("code"),
        "name": payload.get("name"),
        "current_step_index": payload.get("current_step_index"),
        "current_step_id": current_step.get("step_id"),
        "current_step_name": current_step.get("name"),
        "reward_claimed": current_step.get("reward_claimed"),
    }


def _task_history_summary(tasks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(tasks, list):
        return []
    summary: list[dict[str, Any]] = []
    for task in tasks[:5]:
        summary.append(
            {
                "task_id": task.get("task_id"),
                "task_short_id": task.get("task_short_id"),
                "task_type": task.get("task_type"),
                "status": task.get("status"),
                "title": task.get("title"),
            }
        )
    return summary


def _ports_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    ports = payload.get("ports")
    if not isinstance(ports, list):
        return {}
    return {
        "count": len(ports),
        "sample": [
            {
                "sector_id": _extract_port_sector_id(port),
                "code": _extract_port_value(port, "code"),
                "mega": _extract_port_value(port, "mega"),
                "prices": _extract_port_value(port, "prices"),
            }
            for port in ports[:5]
            if isinstance(port, dict)
        ],
    }


def _map_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    sectors = payload.get("sectors")
    return {
        "sector_count": len(sectors) if isinstance(sectors, list) else None,
        "center_sector": payload.get("center_sector"),
        "bounds": payload.get("bounds"),
    }


def _task_events_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    events = payload.get("events")
    return {
        "count": len(events) if isinstance(events, list) else None,
        "cursor": payload.get("cursor"),
    }


def _corporation_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    ships = payload.get("ships")
    ship_types: dict[str, int] = {}
    if isinstance(ships, list):
        for ship in ships:
            if not isinstance(ship, dict):
                continue
            ship_type = ship.get("ship_type")
            if not isinstance(ship_type, str) or not ship_type:
                continue
            ship_types[ship_type] = ship_types.get(ship_type, 0) + 1
    return {
        "corp_id": payload.get("corp_id"),
        "name": payload.get("name"),
        "member_count": payload.get("member_count"),
        "ship_count": len(ships) if isinstance(ships, list) else None,
        "ship_types": ship_types,
    }


def _summarize_bridge_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_name = event.get("event")
    if not isinstance(event_name, str):
        return None

    if event_name == "server_message":
        server_message = _extract_server_message(event)
        if not isinstance(server_message, dict):
            return {"event": event_name}
        summary: dict[str, Any] = {
            "event": server_message.get("event"),
            "frame_type": server_message.get("frame_type"),
        }
        if summary["event"] == "status.snapshot":
            payload = server_message.get("payload")
            if isinstance(payload, dict):
                summary["sector_id"] = _status_summary(payload).get("sector_id")
                summary["ship_credits"] = _status_summary(payload).get("ship_credits")
        return summary

    if event_name in {"bot_output", "bot_llm_text", "bot_tts_text"}:
        return {
            "event": event_name,
            "text": _extract_text_payload(event.get("data")),
        }

    if event_name == "transport_state_changed":
        return {
            "event": event_name,
            "state": event.get("state"),
        }

    return {"event": event_name}


def _extract_port_value(port: dict[str, Any], key: str) -> Any:
    if key in port:
        return port.get(key)
    nested = port.get("port")
    if isinstance(nested, dict):
        return nested.get(key)
    sector = port.get("sector")
    if isinstance(sector, dict):
        nested_port = sector.get("port")
        if isinstance(nested_port, dict):
            return nested_port.get(key)
    return None


def _extract_port_sector_id(port: dict[str, Any]) -> Any:
    if "sector_id" in port:
        return port.get("sector_id")
    sector = port.get("sector")
    if isinstance(sector, dict):
        return sector.get("id")
    return port.get("id")


def _next_timeout(
    *,
    now: float,
    started_at: float,
    duration_seconds: float,
    forever: bool,
    status_interval_seconds: float,
    last_status_poll_at: float,
    idle_reprompt_seconds: float,
    last_action_at: float,
) -> float | None:
    deadlines: list[float] = []

    if not forever:
        deadlines.append(started_at + duration_seconds)
    if status_interval_seconds > 0:
        deadlines.append(last_status_poll_at + status_interval_seconds)
    if idle_reprompt_seconds > 0:
        deadlines.append(last_action_at + idle_reprompt_seconds)

    if not deadlines:
        return None

    return max(0.0, min(deadlines) - now)
