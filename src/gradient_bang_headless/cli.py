from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from .browser import BrowserConnectOptions, HeadlessBrowserError, HostedGameBrowserProcess
from .config import HeadlessConfig
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
    except (HeadlessApiError, HeadlessBridgeError, HeadlessBrowserError) as exc:
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
    login.add_argument("--email", required=True)
    login.add_argument("--password", required=True)
    _add_common_config_args(login)

    register = sub.add_parser("register", help="Create an account")
    register.add_argument("--email", required=True)
    register.add_argument("--password", required=True)
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
    character_create.add_argument("--name", required=True)
    _add_common_config_args(character_create)
    character_create.add_argument("--access-token")

    start_session = sub.add_parser("start-session", help="Create a bot session via /start")
    start_session.add_argument("--character-id", required=True)
    start_session.add_argument("--access-token")
    _add_start_options(start_session)
    _add_common_config_args(start_session)

    signup_and_start = sub.add_parser(
        "signup-and-start",
        help="Two-step bootstrap: register first, then rerun with --verify-url to finish",
    )
    signup_and_start.add_argument("--email", required=True)
    signup_and_start.add_argument("--password", required=True)
    signup_and_start.add_argument("--name", required=True)
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

    browser_connect = sub.add_parser(
        "browser-connect",
        help="Open the hosted game client in a browser, log in, and report state",
    )
    _add_browser_connect_args(browser_connect)

    browser_command = sub.add_parser(
        "browser-command",
        help="Open the hosted game client in a browser, send one command, and close",
    )
    _add_browser_connect_args(browser_command)
    browser_command.add_argument("--text", required=True)
    browser_command.add_argument("--input-timeout-ms", type=int, default=180_000)
    browser_command.add_argument("--wait-after-ms", type=int, default=15_000)
    browser_command.add_argument("--skip-input-wait", action="store_true")

    browser_sequence = sub.add_parser(
        "browser-sequence",
        help="Open the hosted game client in a browser, run a JSON step list, and close",
    )
    _add_browser_connect_args(browser_sequence)
    browser_sequence.add_argument("--steps", required=True)

    browser_contract_loop = sub.add_parser(
        "browser-contract-loop",
        help="Open the hosted game client and repeat a contract-advancement prompt",
    )
    _add_browser_connect_args(browser_contract_loop)
    browser_contract_loop.add_argument("--iterations", type=int, default=3)
    browser_contract_loop.add_argument(
        "--prompt",
        default="complete the next tutorial or contract step now if you can",
    )
    browser_contract_loop.add_argument("--input-timeout-ms", type=int, default=180_000)
    browser_contract_loop.add_argument("--wait-after-ms", type=int, default=60_000)
    browser_contract_loop.add_argument("--skip-input-wait", action="store_true")

    browser_command_watch = sub.add_parser(
        "browser-command-watch",
        help="Open the hosted game client, send one command, and poll until the task settles",
    )
    _add_browser_connect_args(browser_command_watch)
    browser_command_watch.add_argument("--text", required=True)
    browser_command_watch.add_argument("--input-timeout-ms", type=int, default=180_000)
    browser_command_watch.add_argument("--wait-after-ms", type=int, default=15_000)
    browser_command_watch.add_argument("--watch-timeout-ms", type=int, default=300_000)
    browser_command_watch.add_argument("--poll-interval-ms", type=int, default=15_000)
    browser_command_watch.add_argument("--skip-input-wait", action="store_true")

    browser_click = sub.add_parser(
        "browser-click",
        help="Open the hosted game client in a browser, click one button, and close",
    )
    _add_browser_connect_args(browser_click)
    browser_click.add_argument("--label", required=True)
    browser_click.add_argument("--timeout-ms", type=int, default=120_000)
    browser_click.add_argument("--wait-after-ms", type=int, default=5_000)
    browser_click.add_argument("--force", action="store_true")

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


def _add_browser_connect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--site-url", default="https://game.gradient-bang.com/")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--connect-timeout-ms", type=int, default=120_000)
    parser.add_argument("--post-connect-wait-ms", type=int, default=0)
    parser.add_argument("--body-text-limit", type=int, default=4_000)
    parser.add_argument("--log-console", action="store_true")
    _add_common_config_args(parser)


async def dispatch(args: argparse.Namespace) -> int:
    config = config_from_args(args)

    if args.command == "login":
        async with HeadlessApiClient(config) as client:
            result = await client.login(args.email, args.password)
            print(dump_json(result))
            return 0

    if args.command == "register":
        async with HeadlessApiClient(config) as client:
            result = await client.register(args.email, args.password)
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
            result = await client.character_create(args.name, access_token=args.access_token)
            print(dump_json(result))
            return 0

    if args.command == "start-session":
        async with HeadlessApiClient(config) as client:
            result = await client.start_session(
                character_id=args.character_id,
                access_token=_require_access_token(args.access_token, config),
                options=_start_options_from_args(args),
            )
            print(dump_json(result))
            return 0

    if args.command == "signup-and-start":
        async with HeadlessApiClient(config) as client:
            result = await client.signup_and_start(
                email=args.email,
                password=args.password,
                character_name=args.name,
                verify_url=args.verify_url,
                start_options=_start_options_from_args(args),
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

    if args.command == "browser-connect":
        async with HostedGameBrowserProcess(config) as browser:
            result = await browser.connect(_browser_connect_options_from_args(args))
            print(
                dump_json(
                    {
                        "connect": result,
                        "events": await browser.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "browser-command":
        async with HostedGameBrowserProcess(config) as browser:
            connect_result = await browser.connect(_browser_connect_options_from_args(args))
            command_result = await browser.send_command(
                args.text,
                wait_after_ms=args.wait_after_ms,
                wait_for_input_enabled=not args.skip_input_wait,
                input_timeout_ms=args.input_timeout_ms,
                body_text_limit=args.body_text_limit,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": command_result,
                        "events": await browser.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "browser-sequence":
        async with HostedGameBrowserProcess(config) as browser:
            connect_result = await browser.connect(_browser_connect_options_from_args(args))
            steps = _parse_json_array(args.steps)
            results: list[dict[str, Any]] = []
            for index, step in enumerate(steps):
                step_type = step.get("type")
                if step_type == "command":
                    result = await browser.send_command(
                        _require_browser_step_string(step, "text"),
                        wait_after_ms=int(step.get("wait_after_ms", 15_000)),
                        wait_for_input_enabled=not bool(step.get("skip_input_wait", False)),
                        input_timeout_ms=int(step.get("input_timeout_ms", 180_000)),
                        body_text_limit=int(step.get("body_text_limit", args.body_text_limit)),
                    )
                elif step_type == "click":
                    result = await browser.click_button(
                        _require_browser_step_string(step, "label"),
                        wait_after_ms=int(step.get("wait_after_ms", 5_000)),
                        timeout_ms=int(step.get("timeout_ms", 120_000)),
                        force=bool(step.get("force", False)),
                        body_text_limit=int(step.get("body_text_limit", args.body_text_limit)),
                    )
                elif step_type == "status":
                    result = await browser.status(
                        body_text_limit=int(step.get("body_text_limit", args.body_text_limit))
                    )
                elif step_type == "wait":
                    wait_ms = int(step.get("wait_ms", 0))
                    if wait_ms < 0:
                        raise HeadlessBrowserError(
                            "browser-sequence",
                            f"wait_ms must be >= 0 at index {index}",
                        )
                    await asyncio.sleep(wait_ms / 1000.0)
                    result = {"waited_ms": wait_ms}
                elif step_type == "screenshot":
                    result = await browser.screenshot(
                        _require_browser_step_string(step, "path"),
                        full_page=bool(step.get("full_page", True)),
                    )
                else:
                    raise HeadlessBrowserError(
                        "browser-sequence",
                        f"unsupported step type at index {index}: {step_type!r}",
                    )
                results.append(
                    {
                        "index": index,
                        "type": step_type,
                        "result": result,
                    }
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "results": results,
                        "events": await browser.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "browser-contract-loop":
        if args.iterations < 1:
            raise HeadlessBrowserError(
                "browser-contract-loop",
                "--iterations must be >= 1",
            )
        async with HostedGameBrowserProcess(config) as browser:
            connect_result = await browser.connect(_browser_connect_options_from_args(args))
            iterations: list[dict[str, Any]] = []
            for iteration in range(args.iterations):
                command_result = await browser.send_command(
                    args.prompt,
                    wait_after_ms=args.wait_after_ms,
                    wait_for_input_enabled=not args.skip_input_wait,
                    input_timeout_ms=args.input_timeout_ms,
                    body_text_limit=args.body_text_limit,
                )
                status_result = await browser.status(body_text_limit=args.body_text_limit)
                iterations.append(
                    {
                        "iteration": iteration + 1,
                        "command": command_result,
                        "status": status_result,
                    }
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "iterations": iterations,
                        "events": await browser.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "browser-command-watch":
        if args.watch_timeout_ms < 0:
            raise HeadlessBrowserError(
                "browser-command-watch",
                "--watch-timeout-ms must be >= 0",
            )
        if args.poll_interval_ms < 1:
            raise HeadlessBrowserError(
                "browser-command-watch",
                "--poll-interval-ms must be >= 1",
            )
        async with HostedGameBrowserProcess(config) as browser:
            connect_result = await browser.connect(_browser_connect_options_from_args(args))
            command_result = await browser.send_command(
                args.text,
                wait_after_ms=args.wait_after_ms,
                wait_for_input_enabled=not args.skip_input_wait,
                input_timeout_ms=args.input_timeout_ms,
                body_text_limit=args.body_text_limit,
            )
            updates: list[dict[str, Any]] = []
            final_result = command_result
            stop_reason = "watch_timeout"
            initial_state = _extract_engine_status(command_result)
            if initial_state in {"COMPLETED", "IDLE"}:
                stop_reason = f"engine_status:{initial_state.lower()}"
            else:
                started_at = asyncio.get_running_loop().time()
                while (asyncio.get_running_loop().time() - started_at) * 1000 < args.watch_timeout_ms:
                    await asyncio.sleep(args.poll_interval_ms / 1000.0)
                    status_result = await browser.status(body_text_limit=args.body_text_limit)
                    engine_state = _extract_engine_status(status_result)
                    elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
                    updates.append(
                        {
                            "elapsed_ms": elapsed_ms,
                            "engine_status": engine_state,
                            "status": status_result,
                        }
                    )
                    final_result = status_result
                    if engine_state in {"COMPLETED", "IDLE"}:
                        stop_reason = f"engine_status:{engine_state.lower()}"
                        break
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "command": command_result,
                        "updates": updates,
                        "final": final_result,
                        "stopReason": stop_reason,
                        "events": await browser.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "browser-click":
        async with HostedGameBrowserProcess(config) as browser:
            connect_result = await browser.connect(_browser_connect_options_from_args(args))
            click_result = await browser.click_button(
                args.label,
                wait_after_ms=args.wait_after_ms,
                timeout_ms=args.timeout_ms,
                force=args.force,
                body_text_limit=args.body_text_limit,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": click_result,
                        "events": await browser.drain_events(),
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


def _start_options_from_args(args: argparse.Namespace) -> StartOptions:
    return StartOptions(
        transport=args.transport,
        bypass_tutorial=args.bypass_tutorial,
        voice_id=args.voice_id,
        personality_tone=args.personality_tone,
        character_name=args.character_name,
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


def _browser_connect_options_from_args(args: argparse.Namespace) -> BrowserConnectOptions:
    return BrowserConnectOptions(
        email=args.email,
        password=args.password,
        character_name=args.character_name,
        site_url=args.site_url,
        headless=not args.headful,
        connect_timeout_ms=args.connect_timeout_ms,
        post_connect_wait_ms=args.post_connect_wait_ms,
        body_text_limit=args.body_text_limit,
        log_console=args.log_console,
    )


def _require_access_token(raw: str | None, config: HeadlessConfig) -> str:
    token = raw or config.access_token
    if not token:
        raise HeadlessApiError("cli", 0, "missing --access-token or GB_ACCESS_TOKEN")
    return token


def _require_browser_step_string(step: dict[str, Any], key: str) -> str:
    value = step.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HeadlessBrowserError("browser-sequence", f"step field {key!r} is required")
    return value


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise HeadlessApiError("cli", 0, "expected a JSON object")
    return parsed


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        raise HeadlessApiError("cli", 0, "expected a JSON array of objects")
    return parsed


def _extract_engine_status(result: dict[str, Any]) -> str | None:
    body = result.get("bodyText")
    if not isinstance(body, str):
        return None
    match = re.search(r"ENGINE STATUS:\s*([A-Z]+)", body)
    if not match:
        return None
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
