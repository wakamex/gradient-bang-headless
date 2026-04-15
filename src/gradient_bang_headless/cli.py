from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .config import HeadlessConfig
from .http import EventScope, HeadlessApiClient, HeadlessApiError, dump_json


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 1

    try:
        return asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        return 130
    except HeadlessApiError as exc:
        print(str(exc), file=sys.stderr)
        if exc.payload is not None:
            print(dump_json(exc.payload), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gb-headless")
    sub = parser.add_subparsers(dest="command")

    login = sub.add_parser("login", help="Call the public login endpoint")
    login.add_argument("--email", required=True)
    login.add_argument("--password", required=True)
    _add_common_config_args(login)

    character_list = sub.add_parser("character-list", help="List characters for a JWT")
    _add_common_config_args(character_list)
    character_list.add_argument("--access-token")

    character_create = sub.add_parser("character-create", help="Create a character with a JWT")
    character_create.add_argument("--name", required=True)
    _add_common_config_args(character_create)
    character_create.add_argument("--access-token")

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


async def dispatch(args: argparse.Namespace) -> int:
    config = config_from_args(args)

    if args.command == "login":
        async with HeadlessApiClient(config) as client:
            result = await client.login(args.email, args.password)
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


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise HeadlessApiError("cli", 0, "expected a JSON object")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
