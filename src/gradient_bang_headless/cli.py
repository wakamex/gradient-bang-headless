from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .config import HeadlessConfig, update_dotenv
from .bridge import HeadlessBridgeError, HeadlessBridgeProcess, SessionConnectOptions
from .http import (
    EventScope,
    HeadlessApiClient,
    HeadlessApiError,
    StartOptions,
    dump_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 1

    try:
        return asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        return 130
    except (HeadlessApiError, HeadlessBridgeError) as exc:
        print(str(exc), file=sys.stderr)
        payload = getattr(exc, "payload", None)
        if payload is not None:
            print(dump_json(payload), file=sys.stderr)
        stderr_tail = getattr(exc, "stderr_tail", None)
        if stderr_tail:
            print("\n".join(stderr_tail), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gb-headless")
    sub = parser.add_subparsers(dest="command")

    login = sub.add_parser("login", help="Call the public login endpoint")
    login.add_argument("--email")
    login.add_argument("--password")
    _add_common_config_args(login)

    auth_sync = sub.add_parser(
        "auth-sync",
        help="Login and persist runtime auth values into the repo-root .env",
    )
    auth_sync.add_argument("--email")
    auth_sync.add_argument("--password")
    auth_sync.add_argument("--character-name")
    auth_sync.add_argument("--character-id")
    _add_common_config_args(auth_sync)

    register = sub.add_parser("register", help="Create an account")
    register.add_argument("--email")
    register.add_argument("--password")
    _add_common_config_args(register)

    confirm_url = sub.add_parser(
        "confirm-url",
        help="Resolve an email verification URL and extract session tokens",
    )
    confirm_url.add_argument("--verify-url", required=True)
    _add_common_config_args(confirm_url)

    character_list = sub.add_parser("character-list", help="List characters for a JWT")
    _add_common_config_args(character_list)
    character_list.add_argument("--access-token")

    character_create = sub.add_parser("character-create", help="Create a character with a JWT")
    character_create.add_argument("--name")
    _add_common_config_args(character_create)
    character_create.add_argument("--access-token")

    start_session = sub.add_parser("start-session", help="Create a bot session via /start")
    start_session.add_argument("--character-id")
    start_session.add_argument("--access-token")
    _add_start_options(start_session)
    _add_common_config_args(start_session)

    signup_and_start = sub.add_parser(
        "signup-and-start",
        help="Two-step bootstrap: register first, then rerun with --verify-url to finish",
    )
    signup_and_start.add_argument("--email")
    signup_and_start.add_argument("--password")
    signup_and_start.add_argument("--name")
    signup_and_start.add_argument("--verify-url")
    signup_and_start.add_argument("--wait-timeout", type=float, default=10.0)
    signup_and_start.add_argument("--poll-interval", type=float, default=1.0)
    _add_start_options(signup_and_start)
    _add_common_config_args(signup_and_start)

    session_connect = sub.add_parser(
        "session-connect",
        help="Open a SmallWebRTC session through the Node bridge and report connect state",
    )
    _add_session_connect_args(session_connect)

    session_request = sub.add_parser(
        "session-request",
        help="Connect a SmallWebRTC session, send one client request, and close",
    )
    _add_session_connect_args(session_request)
    session_request.add_argument("--message-type", required=True)
    session_request.add_argument("--data", default="{}")
    session_request.add_argument("--timeout-ms", type=int)

    session_message = sub.add_parser(
        "session-message",
        help="Connect a SmallWebRTC session, send one client message, and close",
    )
    _add_session_connect_args(session_message)
    session_message.add_argument("--message-type", required=True)
    session_message.add_argument("--data", default="{}")
    session_message.add_argument("--wait-seconds", type=float, default=0.0)

    session_send_text = sub.add_parser(
        "session-send-text",
        help="Connect a SmallWebRTC session, send text to the bot, and close",
    )
    _add_session_connect_args(session_send_text)
    session_send_text.add_argument("--content", required=True)
    session_send_text.add_argument("--wait-seconds", type=float, default=0.0)

    session_start = sub.add_parser(
        "session-start",
        help="Connect a session, send the start message, and close",
    )
    _add_session_connect_args(session_start)
    session_start.add_argument("--wait-seconds", type=float, default=0.0)

    session_status = sub.add_parser(
        "session-status",
        help="Connect a session, request status, and wait for status.snapshot",
    )
    _add_session_connect_args(session_status)
    session_status.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_known_ports = sub.add_parser(
        "session-known-ports",
        help="Connect a session, request known ports, and wait for ports.list",
    )
    _add_session_connect_args(session_known_ports)
    session_known_ports.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_task_history = sub.add_parser(
        "session-task-history",
        help="Connect a session, request task history, and wait for task.history",
    )
    _add_session_connect_args(session_task_history)
    session_task_history.add_argument("--ship-id")
    session_task_history.add_argument("--max-rows", type=int)
    session_task_history.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_map = sub.add_parser(
        "session-map",
        help="Connect a session, request map data, and wait for map.region/map.local",
    )
    _add_session_connect_args(session_map)
    session_map.add_argument("--center-sector", type=int)
    session_map.add_argument("--bounds", type=int)
    session_map.add_argument("--fit-sector", action="append", dest="fit_sectors", type=int, default=[])
    session_map.add_argument("--max-hops", type=int)
    session_map.add_argument("--max-sectors", type=int)
    session_map.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_assign_quest = sub.add_parser(
        "session-assign-quest",
        help="Connect a session, assign a quest, and wait for quest.status",
    )
    _add_session_connect_args(session_assign_quest)
    session_assign_quest.add_argument("--quest-code", required=True)
    session_assign_quest.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_claim_reward = sub.add_parser(
        "session-claim-reward",
        help="Connect a session, claim a step reward, and wait for quest events",
    )
    _add_session_connect_args(session_claim_reward)
    session_claim_reward.add_argument("--quest-id", required=True)
    session_claim_reward.add_argument("--step-id", required=True)
    session_claim_reward.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_cancel_task = sub.add_parser(
        "session-cancel-task",
        help="Connect a session, cancel a task, and wait for task.history",
    )
    _add_session_connect_args(session_cancel_task)
    session_cancel_task.add_argument("--task-id", required=True)
    session_cancel_task.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_skip_tutorial = sub.add_parser(
        "session-skip-tutorial",
        help="Connect a session, send skip-tutorial, and close",
    )
    _add_session_connect_args(session_skip_tutorial)
    session_skip_tutorial.add_argument("--wait-seconds", type=float, default=0.0)

    session_user_text = sub.add_parser(
        "session-user-text",
        help="Connect a session, send user-text-input, and close",
    )
    _add_session_connect_args(session_user_text)
    session_user_text.add_argument("--text", required=True)
    session_user_text.add_argument("--wait-seconds", type=float, default=0.0)

    session_watch = sub.add_parser(
        "session-watch",
        help="Connect a session, optionally send one client message, wait, and dump raw events",
    )
    _add_session_connect_args(session_watch)
    session_watch.add_argument("--message-type")
    session_watch.add_argument("--data", default="{}")
    session_watch.add_argument("--duration-seconds", type=float, default=10.0)

    call = sub.add_parser("call", help="Generic edge-function call")
    call.add_argument("endpoint")
    call.add_argument("--method", default="POST", choices=["GET", "POST"])
    call.add_argument("--payload", default="{}")
    call.add_argument("--params", default="{}")
    call.add_argument("--access-token")
    call.add_argument("--api-token")
    call.add_argument("--require-api-token", action="store_true")
    _add_common_config_args(call)

    game_call = sub.add_parser(
        "game-call",
        help="Protected gameplay call with optional character auto-injection",
    )
    game_call.add_argument("endpoint")
    game_call.add_argument("--payload", default="{}")
    game_call.add_argument("--character-id")
    game_call.add_argument("--actor-character-id")
    game_call.add_argument("--api-token")
    _add_common_config_args(game_call)

    status = sub.add_parser("status", help="Call my_status with trusted gameplay auth")
    _add_gameplay_target_args(status)

    move = sub.add_parser("move", help="Move to an adjacent sector with trusted gameplay auth")
    move.add_argument("--to-sector", required=True, type=int)
    _add_gameplay_target_args(move)

    plot_course = sub.add_parser(
        "plot-course",
        help="Call plot_course with trusted gameplay auth",
    )
    plot_course.add_argument("--to-sector", required=True, type=int)
    plot_course.add_argument("--from-sector", type=int)
    _add_gameplay_target_args(plot_course)

    map_region = sub.add_parser(
        "map-region",
        help="Call local_map_region with trusted gameplay auth",
    )
    map_region.add_argument("--center-sector", type=int)
    map_region.add_argument("--max-hops", type=int)
    map_region.add_argument("--max-sectors", type=int)
    map_region.add_argument("--bounds", type=int)
    map_region.add_argument("--fit-sector", action="append", dest="fit_sectors", type=int, default=[])
    map_region.add_argument("--source")
    _add_gameplay_target_args(map_region)

    known_ports = sub.add_parser(
        "known-ports",
        help="Call list_known_ports with trusted gameplay auth",
    )
    known_ports.add_argument("--from-sector", type=int)
    known_ports.add_argument("--max-hops", type=int)
    known_ports.add_argument("--port-type")
    known_ports.add_argument("--commodity")
    known_ports.add_argument("--trade-type", choices=["buy", "sell"])
    mega_group = known_ports.add_mutually_exclusive_group()
    mega_group.add_argument("--mega", action="store_true")
    mega_group.add_argument("--non-mega", action="store_true")
    _add_gameplay_target_args(known_ports)

    trade = sub.add_parser("trade", help="Call trade with trusted gameplay auth")
    trade.add_argument("--commodity", required=True)
    trade.add_argument("--quantity", required=True, type=int)
    trade.add_argument("--trade-type", required=True, choices=["buy", "sell"])
    _add_gameplay_target_args(trade)

    recharge_warp = sub.add_parser(
        "recharge-warp",
        help="Call recharge_warp_power with trusted gameplay auth",
    )
    recharge_warp.add_argument("--units", required=True, type=int)
    _add_gameplay_target_args(recharge_warp)

    purchase_fighters = sub.add_parser(
        "purchase-fighters",
        help="Call purchase_fighters with trusted gameplay auth",
    )
    purchase_fighters.add_argument("--units", required=True, type=int)
    _add_gameplay_target_args(purchase_fighters)

    ship_definitions = sub.add_parser(
        "ship-definitions",
        help="Call ship_definitions with trusted gameplay auth",
    )
    ship_definitions.add_argument("--include-description", action="store_true")
    ship_definitions.add_argument("--api-token")
    _add_common_config_args(ship_definitions)

    ship_purchase = sub.add_parser(
        "ship-purchase",
        help="Call ship_purchase with trusted gameplay auth",
    )
    ship_purchase.add_argument("--ship-type", required=True)
    ship_purchase.add_argument("--expected-price", type=int)
    ship_purchase.add_argument("--purchase-type")
    ship_purchase.add_argument("--ship-name")
    ship_purchase.add_argument("--trade-in-ship-id")
    ship_purchase.add_argument("--corp-id")
    ship_purchase.add_argument("--initial-ship-credits", type=int)
    _add_gameplay_target_args(ship_purchase)

    quest_status = sub.add_parser(
        "quest-status",
        help="Call quest_status with trusted gameplay auth",
    )
    _add_gameplay_target_args(quest_status)

    quest_assign = sub.add_parser(
        "quest-assign",
        help="Call quest_assign with trusted gameplay auth",
    )
    quest_assign.add_argument("--quest-code", required=True)
    _add_gameplay_target_args(quest_assign)

    quest_claim_reward = sub.add_parser(
        "quest-claim-reward",
        help="Call quest_claim_reward with trusted gameplay auth",
    )
    quest_claim_reward.add_argument("--quest-id", required=True)
    quest_claim_reward.add_argument("--step-id", required=True)
    _add_gameplay_target_args(quest_claim_reward)

    events_since = sub.add_parser("events-since", help="Poll events_since")
    events_since.add_argument("--character-id", action="append", dest="character_ids", default=[])
    events_since.add_argument("--ship-id", action="append", dest="ship_ids", default=[])
    events_since.add_argument("--corp-id")
    events_since.add_argument("--since-event-id", type=int)
    events_since.add_argument("--limit", type=int, default=100)
    events_since.add_argument("--initial-only", action="store_true")
    events_since.add_argument("--follow", action="store_true")
    events_since.add_argument("--poll-interval", type=float, default=1.0)
    events_since.add_argument("--api-token")
    _add_common_config_args(events_since)

    return parser


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--functions-url")


def _add_start_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", choices=["daily", "smallwebrtc"], default="daily")
    parser.add_argument("--bypass-tutorial", action="store_true")
    parser.add_argument("--voice-id")
    parser.add_argument("--personality-tone")
    parser.add_argument("--character-name")


def _add_session_connect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--access-token")
    parser.add_argument("--character-id")
    parser.add_argument("--session-id")
    parser.add_argument("--connect-timeout-ms", type=int, default=20_000)
    parser.add_argument("--request-timeout-ms", type=int, default=20_000)
    parser.add_argument(
        "--bridge-log-level",
        choices=["none", "error", "warn", "info", "debug"],
        default="none",
    )
    _add_start_options(parser)
    _add_common_config_args(parser)


def _add_gameplay_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--character-id")
    parser.add_argument("--actor-character-id")
    parser.add_argument("--api-token")
    _add_common_config_args(parser)


async def dispatch(args: argparse.Namespace) -> int:
    config = config_from_args(args)

    if args.command == "login":
        async with HeadlessApiClient(config) as client:
            result = await client.login(
                _require_text(args.email, config.email, "email", env_name="GB_EMAIL"),
                _require_text(args.password, config.password, "password", env_name="GB_PASSWORD"),
            )
            print(dump_json(result))
            return 0

    if args.command == "auth-sync":
        async with HeadlessApiClient(config) as client:
            login_result = await client.login(
                _require_text(args.email, config.email, "email", env_name="GB_EMAIL"),
                _require_text(args.password, config.password, "password", env_name="GB_PASSWORD"),
            )

        session = login_result.get("session") if isinstance(login_result, dict) else None
        access_token = session.get("access_token") if isinstance(session, dict) else None
        refresh_token = session.get("refresh_token") if isinstance(session, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise HeadlessApiError(
                "auth-sync",
                0,
                "login did not return an access token",
                payload=login_result,
            )

        selected_character = _select_login_character(
            login_result,
            preferred_character_id=args.character_id,
            preferred_character_name=args.character_name or config.character_name,
        )
        updates: dict[str, str | None] = {
            "GB_ACCESS_TOKEN": access_token,
            "GB_REFRESH_TOKEN": refresh_token if isinstance(refresh_token, str) else None,
        }
        if selected_character is not None:
            updates["GB_CHARACTER_ID"] = selected_character["character_id"]

        env_file = update_dotenv(updates)
        print(
            dump_json(
                {
                    "success": True,
                    "env_file": str(env_file),
                    "wrote": sorted(updates.keys()),
                    "selected_character": selected_character,
                    "character_count": _count_login_characters(login_result),
                }
            )
        )
        return 0

    if args.command == "register":
        async with HeadlessApiClient(config) as client:
            result = await client.register(
                _require_text(args.email, config.email, "email", env_name="GB_EMAIL"),
                _require_text(args.password, config.password, "password", env_name="GB_PASSWORD"),
            )
            print(dump_json(result))
            return 0

    if args.command == "confirm-url":
        async with HeadlessApiClient(config) as client:
            result = await client.confirm_url(args.verify_url)
            print(dump_json(result))
            return 0

    if args.command == "character-list":
        async with HeadlessApiClient(config) as client:
            result = await client.character_list(access_token=args.access_token)
            print(dump_json(result))
            return 0

    if args.command == "character-create":
        async with HeadlessApiClient(config) as client:
            result = await client.character_create(
                _require_text(args.name, config.character_name, "name", env_name="GB_CHARACTER_NAME"),
                access_token=args.access_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "start-session":
        async with HeadlessApiClient(config) as client:
            result = await client.start_session(
                character_id=_require_text(
                    args.character_id,
                    config.character_id,
                    "character-id",
                    env_name="GB_CHARACTER_ID",
                ),
                access_token=_require_access_token(args.access_token, config),
                options=_start_options_from_args(args, config),
            )
            print(dump_json(result))
            return 0

    if args.command == "signup-and-start":
        async with HeadlessApiClient(config) as client:
            result = await client.signup_and_start(
                email=_require_text(args.email, config.email, "email", env_name="GB_EMAIL"),
                password=_require_text(
                    args.password,
                    config.password,
                    "password",
                    env_name="GB_PASSWORD",
                ),
                character_name=_require_text(
                    args.name,
                    config.character_name,
                    "name",
                    env_name="GB_CHARACTER_NAME",
                ),
                verify_url=args.verify_url,
                start_options=_start_options_from_args(args, config),
                wait_timeout=args.wait_timeout,
                poll_interval=args.poll_interval,
            )
            print(dump_json(result))
            return 0

    if args.command == "session-connect":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            result = await bridge.connect(_session_connect_options_from_args(args, config))
            print(
                dump_json(
                    {
                        "connect": result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-request":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            request_result = await bridge.send_client_request(
                args.message_type,
                _parse_json_object(args.data),
                timeout_ms=args.timeout_ms,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": request_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-message":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            send_result = await bridge.send_client_message(
                args.message_type,
                _parse_json_object(args.data),
            )
            if args.wait_seconds > 0:
                await asyncio.sleep(args.wait_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": send_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-send-text":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            send_result = await bridge.send_text(args.content)
            if args.wait_seconds > 0:
                await asyncio.sleep(args.wait_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": send_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-start":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.session_start(wait_seconds=args.wait_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-status":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-known-ports":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.get_known_ports(timeout=args.event_timeout_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-task-history":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.get_task_history(
                ship_id=args.ship_id,
                max_rows=args.max_rows,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-map":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.get_my_map(
                center_sector=args.center_sector,
                bounds=args.bounds,
                fit_sectors=args.fit_sectors or None,
                max_hops=args.max_hops,
                max_sectors=args.max_sectors,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-assign-quest":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.assign_quest(
                args.quest_code,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-claim-reward":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.claim_step_reward(
                quest_id=args.quest_id,
                step_id=args.step_id,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-cancel-task":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.cancel_task(
                args.task_id,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-skip-tutorial":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.skip_tutorial(wait_seconds=args.wait_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-user-text":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            action_result = await bridge.user_text_input(
                args.text,
                wait_seconds=args.wait_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-watch":
        if args.duration_seconds < 0:
            raise HeadlessBridgeError("session-watch", "--duration-seconds must be >= 0")
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await bridge.connect(_session_connect_options_from_args(args, config))
            sent_result = None
            if args.message_type:
                sent_result = await bridge.send_client_message(
                    args.message_type,
                    _parse_json_object(args.data),
                )
            if args.duration_seconds > 0:
                await asyncio.sleep(args.duration_seconds)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "sent": sent_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "call":
        async with HeadlessApiClient(config) as client:
            result = await client.request(
                args.endpoint,
                method=args.method,
                payload=_parse_json_object(args.payload),
                params=_parse_json_object(args.params),
                access_token=args.access_token,
                api_token=args.api_token,
                require_api_token=args.require_api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "game-call":
        async with HeadlessApiClient(config) as client:
            result = await client.call_gameplay(
                args.endpoint,
                payload=_parse_json_object(args.payload),
                character_id=args.character_id,
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "status":
        async with HeadlessApiClient(config) as client:
            result = await client.my_status(
                character_id=_require_character_id(args.character_id, config, operation="status"),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "move":
        async with HeadlessApiClient(config) as client:
            result = await client.move(
                args.to_sector,
                character_id=_require_character_id(args.character_id, config, operation="move"),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "plot-course":
        async with HeadlessApiClient(config) as client:
            result = await client.plot_course(
                args.to_sector,
                from_sector=args.from_sector,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="plot-course",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "map-region":
        async with HeadlessApiClient(config) as client:
            result = await client.local_map_region(
                center_sector=args.center_sector,
                max_hops=args.max_hops,
                max_sectors=args.max_sectors,
                bounds=args.bounds,
                fit_sectors=args.fit_sectors or None,
                source=args.source,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="map-region",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "known-ports":
        mega: bool | None = None
        if args.mega:
            mega = True
        elif args.non_mega:
            mega = False
        async with HeadlessApiClient(config) as client:
            result = await client.list_known_ports(
                from_sector=args.from_sector,
                max_hops=args.max_hops,
                port_type=args.port_type,
                commodity=args.commodity,
                trade_type=args.trade_type,
                mega=mega,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="known-ports",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "trade":
        async with HeadlessApiClient(config) as client:
            result = await client.trade(
                commodity=args.commodity,
                quantity=args.quantity,
                trade_type=args.trade_type,
                character_id=_require_character_id(args.character_id, config, operation="trade"),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "recharge-warp":
        async with HeadlessApiClient(config) as client:
            result = await client.recharge_warp_power(
                units=args.units,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="recharge-warp",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "purchase-fighters":
        async with HeadlessApiClient(config) as client:
            result = await client.purchase_fighters(
                units=args.units,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="purchase-fighters",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "ship-definitions":
        async with HeadlessApiClient(config) as client:
            result = await client.ship_definitions(
                include_description=args.include_description,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "ship-purchase":
        async with HeadlessApiClient(config) as client:
            result = await client.ship_purchase(
                ship_type=args.ship_type,
                expected_price=args.expected_price,
                purchase_type=args.purchase_type,
                ship_name=args.ship_name,
                trade_in_ship_id=args.trade_in_ship_id,
                corp_id=args.corp_id,
                initial_ship_credits=args.initial_ship_credits,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="ship-purchase",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "quest-status":
        async with HeadlessApiClient(config) as client:
            result = await client.quest_status(
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="quest-status",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "quest-assign":
        async with HeadlessApiClient(config) as client:
            result = await client.quest_assign(
                quest_code=args.quest_code,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="quest-assign",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "quest-claim-reward":
        async with HeadlessApiClient(config) as client:
            result = await client.quest_claim_reward(
                quest_id=args.quest_id,
                step_id=args.step_id,
                character_id=_require_character_id(
                    args.character_id,
                    config,
                    operation="quest-claim-reward",
                ),
                actor_character_id=args.actor_character_id,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    if args.command == "events-since":
        async with HeadlessApiClient(config) as client:
            character_ids = args.character_ids or ([config.character_id] if config.character_id else [])
            scope = EventScope(
                character_ids=character_ids,
                ship_ids=args.ship_ids,
                corp_id=args.corp_id,
            )

            if args.follow:
                async for event in client.follow_events(
                    scope=scope,
                    since_event_id=args.since_event_id,
                    limit=args.limit,
                    poll_interval=args.poll_interval,
                    api_token=args.api_token,
                ):
                    print(dump_json(event), flush=True)
                return 0

            result = await client.events_since(
                character_ids=scope.character_ids,
                ship_ids=scope.ship_ids,
                corp_id=scope.corp_id,
                since_event_id=args.since_event_id,
                limit=args.limit,
                initial_only=args.initial_only,
                api_token=args.api_token,
            )
            print(dump_json(result))
            return 0

    raise RuntimeError(f"Unhandled command {args.command}")


def config_from_args(args: argparse.Namespace) -> HeadlessConfig:
    config = HeadlessConfig.from_env()
    if getattr(args, "functions_url", None):
        config.functions_url = args.functions_url.rstrip("/")
    return config


def _start_options_from_args(args: argparse.Namespace, config: HeadlessConfig) -> StartOptions:
    return StartOptions(
        transport=args.transport,
        bypass_tutorial=args.bypass_tutorial,
        voice_id=args.voice_id,
        personality_tone=args.personality_tone,
        character_name=getattr(args, "character_name", None) or config.character_name,
    )


def _session_connect_options_from_args(
    args: argparse.Namespace,
    config: HeadlessConfig,
) -> SessionConnectOptions:
    access_token = _require_access_token(args.access_token, config)
    character_id = args.character_id or config.character_id
    session_id = getattr(args, "session_id", None)
    if not character_id and not session_id:
        raise HeadlessBridgeError(
            "cli",
            "missing --character-id/GB_CHARACTER_ID or --session-id",
        )
    return SessionConnectOptions(
        access_token=access_token,
        functions_url=config.functions_url,
        character_id=character_id,
        session_id=session_id,
        connect_timeout_ms=args.connect_timeout_ms,
        request_timeout_ms=args.request_timeout_ms,
        bypass_tutorial=args.bypass_tutorial,
        voice_id=args.voice_id,
        personality_tone=args.personality_tone,
        character_name=args.character_name,
    )

def _require_access_token(raw: str | None, config: HeadlessConfig) -> str:
    token = raw or config.access_token
    if not token:
        raise HeadlessApiError("cli", 0, "missing --access-token or GB_ACCESS_TOKEN")
    return token


def _require_character_id(
    raw: str | None,
    config: HeadlessConfig,
    *,
    operation: str,
) -> str:
    character_id = raw or config.character_id
    if not character_id:
        raise HeadlessApiError(
            operation,
            0,
            "missing --character-id or GB_CHARACTER_ID",
        )
    return character_id


def _require_text(
    raw: str | None,
    fallback: str | None,
    field_name: str,
    *,
    env_name: str,
) -> str:
    value = (raw or fallback or "").strip()
    if not value:
        raise HeadlessApiError(
            "cli",
            0,
            f"missing --{field_name} or {env_name}",
        )
    return value

def _count_login_characters(login_result: dict[str, Any]) -> int:
    characters = login_result.get("characters")
    if not isinstance(characters, list):
        return 0
    return sum(1 for item in characters if isinstance(item, dict))


def _select_login_character(
    login_result: dict[str, Any],
    *,
    preferred_character_id: str | None = None,
    preferred_character_name: str | None = None,
) -> dict[str, str] | None:
    characters_raw = login_result.get("characters")
    if not isinstance(characters_raw, list):
        return None

    characters = [
        item
        for item in characters_raw
        if isinstance(item, dict)
        and isinstance(item.get("character_id"), str)
        and isinstance(item.get("name"), str)
    ]
    if not characters:
        return None

    if preferred_character_id:
        for item in characters:
            if item["character_id"] == preferred_character_id:
                return {
                    "character_id": item["character_id"],
                    "name": item["name"],
                }

    normalized_name = (preferred_character_name or "").strip().casefold()
    if normalized_name:
        for item in characters:
            if item["name"].strip().casefold() == normalized_name:
                return {
                    "character_id": item["character_id"],
                    "name": item["name"],
                }

    if len(characters) == 1:
        item = characters[0]
        return {
            "character_id": item["character_id"],
            "name": item["name"],
        }

    return None


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise HeadlessApiError("cli", 0, "expected a JSON object")
    return parsed

if __name__ == "__main__":
    raise SystemExit(main())
