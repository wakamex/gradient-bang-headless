from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from .config import HeadlessConfig, repo_root, update_dotenv
from .bridge import HeadlessBridgeError, HeadlessBridgeProcess, SessionConnectOptions
from .frontend_prompts import (
    build_buy_max_commodity_prompt,
    build_recharge_warp_prompt,
    build_corporation_ship_explore_task_description,
    build_corporation_ship_purchase_prompt,
    build_corporation_ship_task_prompt,
    build_garrison_collect_prompt,
    build_garrison_deploy_prompt,
    build_collect_unowned_ship_prompt,
    build_engage_combat_prompt,
    build_garrison_update_prompt,
    build_move_to_sector_prompt,
    build_sell_all_commodity_prompt,
    build_ship_rename_prompt,
    build_ship_purchase_prompt,
    build_trade_order_prompt,
    build_transfer_credits_prompt,
)
from .http import (
    EventScope,
    HeadlessApiClient,
    HeadlessApiError,
    StartOptions,
    dump_json,
)
from .session_loop import LoopTargets, SessionLoopOptions, SessionLoopRunner


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

    leaderboard_resources = sub.add_parser(
        "leaderboard-resources",
        help="Call the public leaderboard_resources endpoint",
    )
    leaderboard_resources.add_argument("--force-refresh", action="store_true")
    _add_common_config_args(leaderboard_resources)

    leaderboard_self_summary = sub.add_parser(
        "leaderboard-self-summary",
        help="Compare live self stats against current human leaderboard leaders",
    )
    _add_session_connect_args(leaderboard_self_summary)
    leaderboard_self_summary.add_argument("--force-refresh", action="store_true")
    leaderboard_self_summary.add_argument("--event-timeout-seconds", type=float, default=30.0)

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
        help="Open a session transport through the Node bridge and report connect state",
    )
    _add_session_connect_args(session_connect)

    session_request = sub.add_parser(
        "session-request",
        help="Connect a session transport, send one client request, and close",
    )
    _add_session_connect_args(session_request)
    session_request.add_argument("--message-type", required=True)
    session_request.add_argument("--data", default="{}")
    session_request.add_argument("--timeout-ms", type=int)

    session_message = sub.add_parser(
        "session-message",
        help="Connect a session transport, send one client message, and close",
    )
    _add_session_connect_args(session_message)
    session_message.add_argument("--message-type", required=True)
    session_message.add_argument("--data", default="{}")
    session_message.add_argument("--wait-seconds", type=float, default=0.0)

    session_send_text = sub.add_parser(
        "session-send-text",
        help="Connect a session transport, send text to the bot, and close",
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

    session_task_events = sub.add_parser(
        "session-task-events",
        help="Connect a session, request task events, and wait for event.query",
    )
    _add_session_connect_args(session_task_events)
    session_task_events.add_argument("--task-id", required=True)
    session_task_events.add_argument("--cursor")
    session_task_events.add_argument("--max-rows", type=int)
    session_task_events.add_argument("--event-timeout-seconds", type=float, default=30.0)

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

    session_chat_history = sub.add_parser(
        "session-chat-history",
        help="Connect a session, request chat history, and wait for chat.history",
    )
    _add_session_connect_args(session_chat_history)
    session_chat_history.add_argument("--since-hours", type=int)
    session_chat_history.add_argument("--max-rows", type=int)
    session_chat_history.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_ships = sub.add_parser(
        "session-ships",
        help="Connect a session, request owned ships, and wait for ships.list",
    )
    _add_session_connect_args(session_ships)
    session_ships.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_ship_definitions = sub.add_parser(
        "session-ship-definitions",
        help="Connect a session, request ship definitions, and wait for ship.definitions",
    )
    _add_session_connect_args(session_ship_definitions)
    session_ship_definitions.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_corporation = sub.add_parser(
        "session-corporation",
        help="Connect a session, request corporation data, and wait for corporation.data/corporation_info",
    )
    _add_session_connect_args(session_corporation)
    session_corporation.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_quest_status = sub.add_parser(
        "session-quest-status",
        help="Connect a session and wait for the next quest.status event",
    )
    _add_session_connect_args(session_quest_status)
    session_quest_status.add_argument("--event-timeout-seconds", type=float, default=30.0)

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

    session_claim_all_rewards = sub.add_parser(
        "session-claim-all-rewards",
        help="Connect a session and claim all currently available quest step rewards",
    )
    _add_session_connect_args(session_claim_all_rewards)
    session_claim_all_rewards.add_argument("--quest-code")
    session_claim_all_rewards.add_argument("--event-timeout-seconds", type=float, default=30.0)

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

    session_player_task = sub.add_parser(
        "session-player-task",
        help="Connect a session, send a personal task via text, and watch task lifecycle events",
    )
    _add_session_connect_args(session_player_task)
    session_player_task.add_argument("--task-description", required=True)
    session_player_task.add_argument("--wait-for-finish", action="store_true")
    session_player_task.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_recharge_warp = sub.add_parser(
        "session-recharge-warp",
        help="Connect a session, recharge warp at a mega-port via the proven player-task prompt, and watch task lifecycle events",
    )
    _add_session_connect_args(session_recharge_warp)
    session_recharge_warp.add_argument("--units", type=int)
    session_recharge_warp.add_argument("--wait-for-finish", action="store_true")
    session_recharge_warp.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_transfer_credits = sub.add_parser(
        "session-transfer-credits",
        help="Connect a session, transfer credits to another ship in-sector via the proven player-task prompt, and watch task lifecycle events",
    )
    _add_session_connect_args(session_transfer_credits)
    session_transfer_credits.add_argument("--amount", required=True, type=int)
    session_transfer_credits.add_argument("--to-ship-name", required=True)
    session_transfer_credits.add_argument("--to-ship-id")
    session_transfer_credits.add_argument("--wait-for-finish", action="store_true")
    session_transfer_credits.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_trade_route_loop = sub.add_parser(
        "session-trade-route-loop",
        help="Connect a session and run a deterministic personal trade route via bounded watched tasks",
    )
    _add_session_connect_args(session_trade_route_loop)
    session_trade_route_loop.add_argument("--buy-sector", required=True, type=int)
    session_trade_route_loop.add_argument("--sell-sector", required=True, type=int)
    session_trade_route_loop.add_argument(
        "--commodity",
        required=True,
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
    )
    session_trade_route_loop.add_argument("--max-cycles", type=int)
    session_trade_route_loop.add_argument("--target-credits", type=int)
    session_trade_route_loop.add_argument("--min-warp", type=int, default=50)
    session_trade_route_loop.add_argument("--step-retries", type=int, default=1)
    session_trade_route_loop.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_trade_order = sub.add_parser(
        "session-trade-order",
        help="Connect a session and send the exact website trade-order prompt",
    )
    _add_session_connect_args(session_trade_order)
    session_trade_order.add_argument("--trade-type", required=True, choices=["buy", "sell"])
    session_trade_order.add_argument(
        "--commodity",
        required=True,
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
    )
    session_trade_order.add_argument("--quantity", required=True, type=int)
    session_trade_order.add_argument("--price-per-unit", required=True, type=int)
    session_trade_order.add_argument("--wait-seconds", type=float, default=0.0)
    session_trade_order.set_defaults(wait_for_task_finish=True)
    session_trade_order.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_trade_order.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_purchase_ship = sub.add_parser(
        "session-purchase-ship",
        help="Connect a session and send the exact website ship purchase prompt",
    )
    _add_session_connect_args(session_purchase_ship)
    session_purchase_ship.add_argument("--ship-display-name", required=True)
    session_purchase_ship.add_argument("--replace-ship-id", required=True)
    session_purchase_ship.add_argument("--replace-ship-name", required=True)
    session_purchase_ship.add_argument("--wait-seconds", type=float, default=0.0)
    session_purchase_ship.set_defaults(wait_for_task_finish=True)
    session_purchase_ship.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_purchase_ship.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_purchase_corp_ship = sub.add_parser(
        "session-purchase-corp-ship",
        help="Connect a session and send the exact website corporation ship purchase prompt",
    )
    _add_session_connect_args(session_purchase_corp_ship)
    session_purchase_corp_ship.add_argument("--ship-display-name", required=True)
    session_purchase_corp_ship.add_argument("--wait-seconds", type=float, default=0.0)
    session_purchase_corp_ship.set_defaults(wait_for_task_finish=True)
    session_purchase_corp_ship.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_purchase_corp_ship.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_corp_task = sub.add_parser(
        "session-corp-task",
        help="Connect a session, task a corporation ship via player text, and watch for task lifecycle events",
    )
    _add_session_connect_args(session_corp_task)
    session_corp_task.add_argument("--ship-name", required=True)
    session_corp_task.add_argument("--ship-id")
    session_corp_task.add_argument("--task-description", required=True)
    session_corp_task.add_argument("--wait-for-finish", action="store_true")
    session_corp_task.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_corp_explore_loop = sub.add_parser(
        "session-corp-explore-loop",
        help="Connect a session, send repeated frontier exploration tasks for a corporation ship, and stop on explicit targets",
    )
    _add_session_connect_args(session_corp_explore_loop)
    session_corp_explore_loop.add_argument("--ship-name", required=True)
    session_corp_explore_loop.add_argument("--ship-id")
    session_corp_explore_loop.add_argument("--new-sectors-per-run", type=int, default=20)
    session_corp_explore_loop.add_argument("--max-runs", type=int)
    session_corp_explore_loop.add_argument("--target-known-sectors", type=int)
    session_corp_explore_loop.add_argument("--target-corp-sectors", type=int)
    session_corp_explore_loop.add_argument("--event-timeout-seconds", type=float, default=180.0)

    session_collect_unowned_ship = sub.add_parser(
        "session-collect-unowned-ship",
        help="Connect a session, send the exact website collect-unowned-ship prompt, and wait for the ship to appear in owned ships",
    )
    _add_session_connect_args(session_collect_unowned_ship)
    session_collect_unowned_ship.add_argument("--ship-id", required=True)
    session_collect_unowned_ship.add_argument("--event-timeout-seconds", type=float, default=45.0)
    session_collect_unowned_ship.add_argument("--poll-interval-seconds", type=float, default=3.0)

    session_salvage_collect = sub.add_parser(
        "session-salvage-collect",
        help="Connect a session, collect salvage via direct session message, and wait for salvage.collected",
    )
    _add_session_connect_args(session_salvage_collect)
    session_salvage_collect.add_argument("--salvage-id", required=True)
    session_salvage_collect.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_engage_combat = sub.add_parser(
        "session-engage-combat",
        help="Connect a session, send the exact website engage-combat prompt, and wait for the first combat event",
    )
    _add_session_connect_args(session_engage_combat)
    session_engage_combat.add_argument("--player-name", required=True)
    session_engage_combat.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_combat_action = sub.add_parser(
        "session-combat-action",
        help="Connect a session, submit a combat-action message, and wait for the first combat response event",
    )
    _add_session_connect_args(session_combat_action)
    session_combat_action.add_argument("--combat-id", required=True)
    session_combat_action.add_argument(
        "--action",
        required=True,
        choices=["attack", "brace", "flee", "pay"],
    )
    session_combat_action.add_argument("--round", required=True, type=int)
    session_combat_action.add_argument("--commit", type=int)
    session_combat_action.add_argument("--target-id")
    session_combat_action.add_argument("--to-sector", type=int)
    session_combat_action.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_garrison_deploy = sub.add_parser(
        "session-garrison-deploy",
        help="Connect a session, send the proven garrison-deploy prompt, and wait for the player task to finish",
    )
    _add_session_connect_args(session_garrison_deploy)
    session_garrison_deploy.add_argument("--quantity", required=True, type=int)
    session_garrison_deploy.add_argument(
        "--mode",
        choices=["offensive", "defensive", "toll"],
        default="offensive",
    )
    session_garrison_deploy.add_argument("--toll-amount", type=int)
    session_garrison_deploy.add_argument("--wait-seconds", type=float, default=0.0)
    session_garrison_deploy.set_defaults(wait_for_task_finish=True)
    session_garrison_deploy.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_garrison_deploy.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_garrison_collect = sub.add_parser(
        "session-garrison-collect",
        help="Connect a session, send the proven garrison-collect prompt, and wait for the player task to finish",
    )
    _add_session_connect_args(session_garrison_collect)
    session_garrison_collect.add_argument("--quantity", required=True, type=int)
    session_garrison_collect.add_argument("--wait-seconds", type=float, default=0.0)
    session_garrison_collect.set_defaults(wait_for_task_finish=True)
    session_garrison_collect.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_garrison_collect.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_garrison_update = sub.add_parser(
        "session-garrison-update",
        help="Connect a session, send the exact website garrison-update prompt, and wait for garrison.mode_changed",
    )
    _add_session_connect_args(session_garrison_update)
    session_garrison_update.add_argument(
        "--mode",
        required=True,
        choices=["offensive", "defensive", "toll"],
    )
    session_garrison_update.add_argument("--toll-amount", type=int)
    session_garrison_update.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_rename_ship = sub.add_parser(
        "session-rename-ship",
        help="Connect a session, send the current website ship-rename prompt, and wait for status to reflect the new name",
    )
    _add_session_connect_args(session_rename_ship)
    session_rename_ship.add_argument("--ship-name", required=True)
    session_rename_ship.add_argument("--event-timeout-seconds", type=float, default=45.0)
    session_rename_ship.add_argument("--poll-interval-seconds", type=float, default=3.0)

    session_watch = sub.add_parser(
        "session-watch",
        help="Connect a session, optionally send one client message, wait, and dump raw events",
    )
    _add_session_connect_args(session_watch)
    session_watch.add_argument("--message-type")
    session_watch.add_argument("--data", default="{}")
    session_watch.add_argument("--duration-seconds", type=float, default=10.0)

    loop = sub.add_parser(
        "loop",
        aliases=["session-loop"],
        help="Drive a bot objective over the live player session with status checks and reprompts",
    )
    _add_session_connect_args(loop)
    loop.add_argument("--objective", required=True)
    loop.add_argument("--bootstrap-timeout-seconds", type=float, default=10.0)
    loop.add_argument("--duration-seconds", type=float, default=300.0)
    loop.add_argument("--forever", action="store_true")
    loop.add_argument("--no-start", action="store_true")
    loop.add_argument("--status-interval-seconds", type=float, default=20.0)
    loop.add_argument("--idle-reprompt-seconds", type=float, default=45.0)
    loop.add_argument("--max-reprompts", type=int, default=2)
    loop.add_argument("--reprompt-prefix", default="Continue the current objective and act on it:")
    loop.add_argument("--target-credits", type=int)
    loop.add_argument("--target-sector", type=int)
    loop.add_argument("--target-ship-type")
    loop.add_argument("--target-quest-code")
    loop.add_argument("--target-quest-step-name")
    loop.add_argument("--target-corp-ship-count", type=int)
    loop.add_argument("--target-corp-ship-type")
    loop.add_argument("--target-corp-ship-type-count", type=int)

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
    parser.add_argument(
        "--transport",
        choices=["daily", "rawdaily", "smallwebrtc"],
        default="daily",
    )
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

    if args.command == "leaderboard-resources":
        async with HeadlessApiClient(config) as client:
            result = await client.leaderboard_resources(force_refresh=args.force_refresh)
            print(dump_json(result))
            return 0

    if args.command == "leaderboard-self-summary":
        async with HeadlessApiClient(config) as client:
            leaderboard_result = await client.leaderboard_resources(
                force_refresh=args.force_refresh,
            )

        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            await _connect_session_bridge(bridge, args, config)
            status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
            ships_result = await bridge.get_my_ships(timeout=args.event_timeout_seconds)

        print(
            dump_json(
                _leaderboard_self_summary(
                    config=config,
                    leaderboard_result=leaderboard_result,
                    status_result=status_result,
                    ships_result=ships_result,
                    transport=args.transport,
                )
            )
        )
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
            result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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

    if args.command == "session-task-events":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.get_task_events(
                args.task_id,
                cursor=args.cursor,
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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

    if args.command == "session-chat-history":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.get_chat_history(
                since_hours=args.since_hours,
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

    if args.command == "session-ships":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.get_my_ships(timeout=args.event_timeout_seconds)
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

    if args.command == "session-ship-definitions":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.get_ship_definitions(timeout=args.event_timeout_seconds)
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

    if args.command == "session-corporation":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.get_my_corporation(timeout=args.event_timeout_seconds)
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

    if args.command == "session-quest-status":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.wait_for_quest_status(timeout=args.event_timeout_seconds)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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

    if args.command == "session-claim-all-rewards":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            initial_status = await bridge.wait_for_quest_status(timeout=args.event_timeout_seconds)
            initial_events = await bridge.drain_events()
            latest_quest_status = _last_quest_status_event(
                [initial_status.get("server_event"), *initial_events]
            )
            claimable_steps = _collect_claimable_reward_steps(
                latest_quest_status,
                quest_code=args.quest_code,
            )
            claimed_steps: list[dict[str, Any]] = []
            latest_claimable = claimable_steps

            for step in claimable_steps:
                action_result = await bridge.claim_step_reward(
                    quest_id=step["quest_id"],
                    step_id=step["step_id"],
                    timeout=args.event_timeout_seconds,
                )
                action_events = await bridge.drain_events()
                latest_quest_status = _last_quest_status_event(
                    [action_result.get("server_event"), *action_events],
                    fallback=latest_quest_status,
                )
                _mark_reward_claimed(
                    latest_quest_status,
                    quest_id=step["quest_id"],
                    step_id=step["step_id"],
                )
                claimed_steps.append(
                    {
                        "quest_code": step["quest_code"],
                        "quest_id": step["quest_id"],
                        "step_id": step["step_id"],
                        "step_index": step["step_index"],
                        "step_name": step["step_name"],
                        "reward_credits": step["reward_credits"],
                    }
                )
                latest_claimable = _collect_claimable_reward_steps(
                    latest_quest_status,
                    quest_code=args.quest_code,
                )

            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "quest_code_filter": args.quest_code,
                        "claimable_steps": claimable_steps,
                        "claimed_steps": claimed_steps,
                        "remaining_claimable_steps": latest_claimable,
                        "final_quests": _quest_status_summary(latest_quest_status),
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-cancel-task":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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

    if args.command == "session-player-task":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                args.task_description,
                wait_seconds=0.0,
            )
            watch_result = await _watch_player_task(
                bridge,
                wait_for_finish=args.wait_for_finish,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": args.task_description,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-recharge-warp":
        prompt = _recharge_warp_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=0.0,
            )
            watch_result = await _watch_player_task(
                bridge,
                wait_for_finish=args.wait_for_finish,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-transfer-credits":
        prompt = _transfer_credits_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=0.0,
            )
            watch_result = await _watch_player_task(
                bridge,
                wait_for_finish=args.wait_for_finish,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-trade-route-loop":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_trade_route_loop(
                bridge,
                buy_sector=args.buy_sector,
                sell_sector=args.sell_sector,
                commodity=args.commodity,
                max_cycles=args.max_cycles,
                target_credits=args.target_credits,
                min_warp=args.min_warp,
                step_retries=args.step_retries,
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

    if args.command == "session-trade-order":
        prompt = _trade_order_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=args.wait_seconds,
            )
            watch_result = None
            if args.wait_for_task_finish:
                watch_result = await _watch_player_task(
                    bridge,
                    wait_for_finish=True,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-purchase-ship":
        prompt = _ship_purchase_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=args.wait_seconds,
            )
            watch_result = None
            if args.wait_for_task_finish:
                watch_result = await _watch_player_task(
                    bridge,
                    wait_for_finish=True,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-purchase-corp-ship":
        prompt = _corporation_ship_purchase_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=args.wait_seconds,
            )
            watch_result = None
            if args.wait_for_task_finish:
                watch_result = await _watch_player_task(
                    bridge,
                    wait_for_finish=True,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-corp-task":
        prompt = _corporation_ship_task_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(prompt)
            watch_result = await _watch_corporation_task(
                bridge,
                ship_id=args.ship_id,
                ship_name=args.ship_name,
                wait_for_finish=args.wait_for_finish,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-corp-explore-loop":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_corporation_explore_loop(
                bridge,
                ship_id=args.ship_id,
                ship_name=args.ship_name,
                new_sectors_per_run=args.new_sectors_per_run,
                max_runs=args.max_runs,
                target_known_sectors=args.target_known_sectors,
                target_corp_sectors=args.target_corp_sectors,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "action": action_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-collect-unowned-ship":
        prompt = _collect_unowned_ship_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(prompt)
            watch_result = await _wait_for_owned_ship(
                bridge,
                ship_id=args.ship_id,
                timeout=args.event_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-salvage-collect":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.salvage_collect(
                args.salvage_id,
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

    if args.command == "session-engage-combat":
        prompt = _engage_combat_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(prompt)
            watch_result = await _wait_for_first_combat_event(
                bridge,
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-combat-action":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.combat_action(
                combat_id=args.combat_id,
                action=args.action,
                round_number=args.round,
                commit=args.commit,
                target_id=args.target_id,
                to_sector=args.to_sector,
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

    if args.command == "session-garrison-deploy":
        prompt = _garrison_deploy_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=args.wait_seconds,
            )
            watch_result = None
            if args.wait_for_task_finish:
                watch_result = await _watch_player_task(
                    bridge,
                    wait_for_finish=True,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-garrison-collect":
        prompt = _garrison_collect_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(
                prompt,
                wait_seconds=args.wait_seconds,
            )
            watch_result = None
            if args.wait_for_task_finish:
                watch_result = await _watch_player_task(
                    bridge,
                    wait_for_finish=True,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-garrison-update":
        prompt = _garrison_update_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(prompt)
            watch_result = await _wait_for_named_server_event(
                bridge,
                event_names={"garrison.mode_changed"},
                timeout=args.event_timeout_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-rename-ship":
        prompt = _ship_rename_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await bridge.user_text_input(prompt)
            watch_result = await _wait_for_status_ship_name(
                bridge,
                ship_name=args.ship_name,
                timeout=args.event_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "prompt": prompt,
                        "result": action_result,
                        "watch": watch_result,
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
            connect_result = await _connect_session_bridge(bridge, args, config)
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

    if args.command in {"loop", "session-loop"}:
        if not args.forever and args.duration_seconds <= 0:
            raise HeadlessBridgeError("loop", "--duration-seconds must be > 0 unless --forever is set")
        if args.target_corp_ship_type_count is not None and not args.target_corp_ship_type:
            raise HeadlessBridgeError(
                "loop",
                "--target-corp-ship-type-count requires --target-corp-ship-type",
            )
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            runner = SessionLoopRunner(bridge)
            result = await runner.run(
                SessionLoopOptions(
                    objective=args.objective,
                    bootstrap_timeout_seconds=args.bootstrap_timeout_seconds,
                    duration_seconds=args.duration_seconds,
                    forever=args.forever,
                    send_start=not args.no_start,
                    status_interval_seconds=args.status_interval_seconds,
                    idle_reprompt_seconds=args.idle_reprompt_seconds,
                    max_reprompts=args.max_reprompts,
                    reprompt_prefix=args.reprompt_prefix,
                    targets=_loop_targets_from_args(args),
                )
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "result": result,
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
        transport=args.transport,
        character_id=character_id,
        session_id=session_id,
        connect_timeout_ms=args.connect_timeout_ms,
        request_timeout_ms=args.request_timeout_ms,
        bypass_tutorial=args.bypass_tutorial,
        voice_id=args.voice_id,
        personality_tone=args.personality_tone,
        character_name=args.character_name,
    )


def _is_start_unauthorized_error(exc: HeadlessBridgeError) -> bool:
    payload = exc.payload
    if not isinstance(payload, dict):
        return False
    events = payload.get("events")
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") != "http_request_completed":
            continue
        if event.get("status") != 401:
            continue
        url = event.get("url")
        if isinstance(url, str) and url.rstrip("/").endswith("/functions/v1/start"):
            return True
    return False


async def _refresh_session_access_token(config: HeadlessConfig) -> dict[str, Any]:
    email = _require_text(None, config.email, "email", env_name="GB_EMAIL")
    password = _require_text(None, config.password, "password", env_name="GB_PASSWORD")

    async with HeadlessApiClient(config) as client:
        login_result = await client.login(email, password)

    session = login_result.get("session") if isinstance(login_result, dict) else None
    access_token = session.get("access_token") if isinstance(session, dict) else None
    refresh_token = session.get("refresh_token") if isinstance(session, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise HeadlessApiError(
            "session-auth-refresh",
            0,
            "login did not return an access token",
            payload=login_result,
        )

    config.access_token = access_token
    config.refresh_token = refresh_token if isinstance(refresh_token, str) else None
    update_dotenv(
        {
            "GB_ACCESS_TOKEN": access_token,
            "GB_REFRESH_TOKEN": config.refresh_token,
        }
    )

    return {
        "access_token": access_token,
        "refresh_token": config.refresh_token,
        "login_result": login_result,
    }


async def _connect_session_bridge(
    bridge: HeadlessBridgeProcess,
    args: argparse.Namespace,
    config: HeadlessConfig,
) -> Any:
    options = _session_connect_options_from_args(args, config)
    try:
        return await bridge.connect(options)
    except HeadlessBridgeError as exc:
        if args.access_token or not _is_start_unauthorized_error(exc):
            raise
        await _refresh_session_access_token(config)
        refreshed_options = _session_connect_options_from_args(args, config)
        return await bridge.connect(refreshed_options)


def _loop_targets_from_args(args: argparse.Namespace) -> LoopTargets:
    return LoopTargets(
        credits=args.target_credits,
        sector=args.target_sector,
        ship_type=args.target_ship_type,
        quest_code=args.target_quest_code,
        quest_step_name=args.target_quest_step_name,
        corp_ship_count=args.target_corp_ship_count,
        corp_ship_type=args.target_corp_ship_type,
        corp_ship_type_count=args.target_corp_ship_type_count,
    )


def _trade_order_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_trade_order_prompt(
            trade_type=args.trade_type,
            quantity=args.quantity,
            commodity=args.commodity,
            price_per_unit=args.price_per_unit,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-trade-order", str(exc)) from exc


def _recharge_warp_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_recharge_warp_prompt(units=args.units)
    except ValueError as exc:
        raise HeadlessBridgeError("session-recharge-warp", str(exc)) from exc


def _transfer_credits_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_transfer_credits_prompt(
            amount=args.amount,
            to_ship_name=args.to_ship_name,
            to_ship_id=args.to_ship_id,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-transfer-credits", str(exc)) from exc


def _ship_purchase_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_ship_purchase_prompt(
            ship_display_name=args.ship_display_name,
            replace_ship_name=args.replace_ship_name,
            replace_ship_id=args.replace_ship_id,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-purchase-ship", str(exc)) from exc


def _corporation_ship_purchase_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_corporation_ship_purchase_prompt(
            ship_display_name=args.ship_display_name,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-purchase-corp-ship", str(exc)) from exc


def _corporation_ship_task_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_corporation_ship_task_prompt(
            ship_name=args.ship_name,
            ship_id=args.ship_id,
            task_description=args.task_description,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-corp-task", str(exc)) from exc


def _collect_unowned_ship_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_collect_unowned_ship_prompt(ship_id=args.ship_id)
    except ValueError as exc:
        raise HeadlessBridgeError("session-collect-unowned-ship", str(exc)) from exc


def _engage_combat_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_engage_combat_prompt(player_name=args.player_name)
    except ValueError as exc:
        raise HeadlessBridgeError("session-engage-combat", str(exc)) from exc


def _garrison_deploy_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_garrison_deploy_prompt(
            quantity=args.quantity,
            mode=args.mode,
            toll_amount=args.toll_amount,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-garrison-deploy", str(exc)) from exc


def _garrison_collect_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_garrison_collect_prompt(quantity=args.quantity)
    except ValueError as exc:
        raise HeadlessBridgeError("session-garrison-collect", str(exc)) from exc


def _garrison_update_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_garrison_update_prompt(
            mode=args.mode,
            toll_amount=args.toll_amount,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-garrison-update", str(exc)) from exc


def _ship_rename_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_ship_rename_prompt(ship_name=args.ship_name)
    except ValueError as exc:
        raise HeadlessBridgeError("session-rename-ship", str(exc)) from exc


def _extract_status_snapshot(server_event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(server_event, dict):
        return None
    if server_event.get("event") == "server_message":
        data = server_event.get("data")
        if isinstance(data, dict):
            return _extract_status_snapshot(data)
        return None
    if server_event.get("event") != "status.snapshot":
        return None
    payload = server_event.get("payload")
    return payload if isinstance(payload, dict) else None


def _status_snapshot_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    player = payload.get("player")
    ship = payload.get("ship")
    sector = payload.get("sector")
    cargo = ship.get("cargo") if isinstance(ship, dict) else None
    cargo_summary = cargo if isinstance(cargo, dict) else {}

    return {
        "sector_id": sector.get("id") if isinstance(sector, dict) else None,
        "port_code": (
            sector.get("port", {}).get("code")
            if isinstance(sector, dict) and isinstance(sector.get("port"), dict)
            else None
        ),
        "port_is_mega": (
            sector.get("port", {}).get("mega")
            if isinstance(sector, dict) and isinstance(sector.get("port"), dict)
            else None
        ),
        "port_prices": (
            sector.get("port", {}).get("prices")
            if isinstance(sector, dict) and isinstance(sector.get("port"), dict)
            and isinstance(sector.get("port", {}).get("prices"), dict)
            else {}
        ),
        "ship_id": ship.get("ship_id") if isinstance(ship, dict) else None,
        "ship_name": ship.get("ship_name") if isinstance(ship, dict) else None,
        "ship_credits": ship.get("credits") if isinstance(ship, dict) else None,
        "warp_power": ship.get("warp_power") if isinstance(ship, dict) else None,
        "current_task_id": ship.get("current_task_id") if isinstance(ship, dict) else None,
        "cargo": cargo_summary,
        "empty_holds": ship.get("empty_holds") if isinstance(ship, dict) else None,
        "known_sectors": player.get("total_sectors_known") if isinstance(player, dict) else None,
        "corp_sectors_visited": player.get("corp_sectors_visited") if isinstance(player, dict) else None,
        "sectors_visited": player.get("sectors_visited") if isinstance(player, dict) else None,
    }


def _extract_server_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event") != "server_message":
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    if data.get("frame_type") != "event":
        return None
    return data


def _normalize_compare_text(value: str | None) -> str:
    return (value or "").strip().casefold()


def _matches_identifier(candidate: str | None, wanted: str | None) -> bool:
    normalized_candidate = _normalize_compare_text(candidate)
    normalized_wanted = _normalize_compare_text(wanted)
    if not normalized_candidate or not normalized_wanted:
        return False
    return (
        normalized_candidate == normalized_wanted
        or normalized_candidate.startswith(normalized_wanted)
        or normalized_wanted.startswith(normalized_candidate)
    )


def _task_event_matches(
    server_event: dict[str, Any],
    *,
    ship_id: str | None,
    ship_name: str | None,
    required_scope: str | None = None,
) -> bool:
    payload = server_event.get("payload")
    if not isinstance(payload, dict):
        return False
    if required_scope and payload.get("task_scope") != required_scope:
        return False
    if ship_id and not _matches_identifier(payload.get("ship_id"), ship_id):
        return False
    if ship_name and _normalize_compare_text(payload.get("ship_name")) != _normalize_compare_text(ship_name):
        return False
    return True


def _select_ship_from_ships_event(
    server_event: dict[str, Any] | None,
    *,
    ship_id: str | None,
    ship_name: str | None,
) -> dict[str, Any] | None:
    if not isinstance(server_event, dict):
        return None
    extracted = _extract_server_event(server_event)
    if isinstance(extracted, dict):
        server_event = extracted
    payload = server_event.get("payload")
    if not isinstance(payload, dict):
        return None
    ships = payload.get("ships")
    if not isinstance(ships, list):
        return None
    for ship in ships:
        if not isinstance(ship, dict):
            continue
        if ship_id and _matches_identifier(ship.get("ship_id"), ship_id):
            return ship
        if ship_name and _normalize_compare_text(ship.get("ship_name")) == _normalize_compare_text(ship_name):
            return ship
    return None


def _select_ship_from_corporation_event(
    server_event: dict[str, Any] | None,
    *,
    ship_id: str | None,
    ship_name: str | None,
) -> dict[str, Any] | None:
    if not isinstance(server_event, dict):
        return None
    extracted = _extract_server_event(server_event)
    if isinstance(extracted, dict):
        server_event = extracted
    payload = server_event.get("payload")
    if not isinstance(payload, dict):
        return None
    corporation = payload.get("corporation")
    if not isinstance(corporation, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            corporation = result.get("corporation")
    if not isinstance(corporation, dict):
        return None
    ships = corporation.get("ships")
    if not isinstance(ships, list):
        return None
    for ship in ships:
        if not isinstance(ship, dict):
            continue
        ship_candidate_name = ship.get("name") or ship.get("ship_name")
        if ship_id and _matches_identifier(ship.get("ship_id"), ship_id):
            return ship
        if ship_name and _normalize_compare_text(ship_candidate_name) == _normalize_compare_text(ship_name):
            return ship
    return None


async def _watch_corporation_task(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str,
    wait_for_finish: bool,
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError("session-corp-task", "--event-timeout-seconds must be > 0")

    deadline = asyncio.get_running_loop().time() + timeout
    task_start: dict[str, Any] | None = None
    task_finish: dict[str, Any] | None = None
    started_task_id: str | None = None
    latest_quest_status: dict[str, Any] | None = None

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            event = await bridge.next_event(timeout=remaining)
        except asyncio.TimeoutError:
            break

        server_event = _extract_server_event(event)
        if not isinstance(server_event, dict):
            continue

        event_name = server_event.get("event")
        if event_name == "quest.status":
            latest_quest_status = server_event
            continue
        if event_name == "task.start" and _task_event_matches(
            server_event,
            ship_id=ship_id,
            ship_name=ship_name,
            required_scope="corp_ship",
        ):
            task_start = server_event
            payload = server_event.get("payload")
            if isinstance(payload, dict):
                started_task_id = payload.get("task_id")
            if not wait_for_finish:
                break
            continue
        if event_name == "task.finish" and _task_event_matches(
            server_event,
            ship_id=ship_id,
            ship_name=ship_name,
            required_scope="corp_ship",
        ):
            if task_start is None:
                continue
            payload = server_event.get("payload")
            if isinstance(payload, dict) and started_task_id:
                finish_task_id = payload.get("task_id")
                if finish_task_id != started_task_id:
                    continue
            task_finish = server_event
            break

    stop_reason = "timeout"
    if task_finish is not None:
        stop_reason = "task_finish"
    elif task_start is not None:
        stop_reason = "task_start"

    post_watch_errors: list[str] = []
    ships_event = None
    corporation_event = None

    try:
        ships_result = await bridge.get_my_ships(timeout=15.0)
    except HeadlessBridgeError as exc:
        post_watch_errors.append(str(exc))
    else:
        ships_event = ships_result.get("server_event")

    try:
        corporation_result = await bridge.get_my_corporation(timeout=15.0)
    except HeadlessBridgeError as exc:
        post_watch_errors.append(str(exc))
    else:
        corporation_event = corporation_result.get("server_event")

    result: dict[str, Any] = {
        "wait_for_finish": wait_for_finish,
        "stop_reason": stop_reason,
        "task_started": task_start is not None,
        "task_finished": task_finish is not None,
        "task_id": started_task_id,
        "task_start": task_start,
        "task_finish": task_finish,
        "matched_ship": _select_ship_from_ships_event(
            ships_event,
            ship_id=ship_id,
            ship_name=ship_name,
        ),
        "matched_corporation_ship": _select_ship_from_corporation_event(
            corporation_event,
            ship_id=ship_id,
            ship_name=ship_name,
        ),
        "post_watch_errors": post_watch_errors,
    }
    if latest_quest_status is not None:
        result["quests"] = _quest_status_summary(latest_quest_status)
        result["latest_quest_status"] = latest_quest_status
    return result


async def _fetch_owned_ship_snapshot(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str | None,
    timeout: float,
) -> dict[str, Any]:
    result = await bridge.get_my_ships(timeout=timeout)
    server_event = result.get("server_event")
    ship = _select_ship_from_ships_event(server_event, ship_id=ship_id, ship_name=ship_name)
    if ship is None:
        raise HeadlessBridgeError(
            "session-corp-explore-loop",
            "ships.list did not include the requested ship",
            payload=result,
        )
    return {
        "result": result,
        "ship": ship,
    }


async def _watch_player_task(
    bridge: HeadlessBridgeProcess,
    *,
    wait_for_finish: bool,
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError("session-user-text", "--event-timeout-seconds must be > 0")

    deadline = asyncio.get_running_loop().time() + timeout
    task_start: dict[str, Any] | None = None
    task_finish: dict[str, Any] | None = None
    started_task_id: str | None = None

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            event = await bridge.next_event(timeout=remaining)
        except asyncio.TimeoutError:
            break

        server_event = _extract_server_event(event)
        if not isinstance(server_event, dict):
            continue

        event_name = server_event.get("event")
        if event_name == "task.start" and _task_event_matches(
            server_event,
            ship_id=None,
            ship_name=None,
            required_scope="player_ship",
        ):
            task_start = server_event
            payload = server_event.get("payload")
            if isinstance(payload, dict):
                started_task_id = payload.get("task_id")
            if not wait_for_finish:
                break
            continue
        if event_name == "task.finish" and _task_event_matches(
            server_event,
            ship_id=None,
            ship_name=None,
            required_scope="player_ship",
        ):
            if task_start is None:
                continue
            payload = server_event.get("payload")
            if isinstance(payload, dict) and started_task_id:
                finish_task_id = payload.get("task_id")
                if finish_task_id != started_task_id:
                    continue
            task_finish = server_event
            break

    stop_reason = "timeout"
    if task_finish is not None:
        stop_reason = "task_finish"
    elif task_start is not None:
        stop_reason = "task_start"

    post_watch_errors: list[str] = []
    status_event = None
    try:
        status_result = await bridge.get_my_status(timeout=15.0)
    except HeadlessBridgeError as exc:
        post_watch_errors.append(str(exc))
    else:
        status_event = status_result.get("server_event")

    return {
        "wait_for_finish": wait_for_finish,
        "stop_reason": stop_reason,
        "task_started": task_start is not None,
        "task_finished": task_finish is not None,
        "task_id": started_task_id,
        "task_start": task_start,
        "task_finish": task_finish,
        "status": status_event,
        "post_watch_errors": post_watch_errors,
    }


async def _fetch_status_snapshot(
    bridge: HeadlessBridgeProcess,
    *,
    timeout: float,
) -> dict[str, Any]:
    result = await bridge.get_my_status(timeout=timeout)
    server_event = result.get("server_event")
    payload = _extract_status_snapshot(server_event)
    if payload is None:
        raise HeadlessBridgeError(
            "session-trade-route-loop",
            "status request did not return a status.snapshot payload",
            payload=result,
        )
    return {
        "result": result,
        "payload": payload,
        "summary": _status_snapshot_summary(payload),
    }


async def _run_player_task_prompt(
    bridge: HeadlessBridgeProcess,
    *,
    prompt: str,
    timeout: float,
) -> dict[str, Any]:
    action_result = await bridge.user_text_input(prompt, wait_seconds=0.0)
    watch_result = await _watch_player_task(
        bridge,
        wait_for_finish=True,
        timeout=timeout,
    )
    status_result = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
    return {
        "prompt": prompt,
        "result": action_result,
        "watch": watch_result,
        "status": status_result,
    }


async def _run_validated_player_step(
    bridge: HeadlessBridgeProcess,
    *,
    prompt: str,
    timeout: float,
    retries: int,
    validate,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(max(0, retries) + 1):
        action_result = await bridge.user_text_input(prompt, wait_seconds=0.0)
        watch_timeout = min(timeout, 20.0)
        watch_result = await _watch_player_task(
            bridge,
            wait_for_finish=True,
            timeout=watch_timeout,
        )
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout - watch_timeout)
        status_result = await _fetch_status_snapshot(bridge, timeout=min(timeout, 15.0))
        status_polls: list[dict[str, Any]] = []
        summary = status_result["summary"]

        while not validate(summary):
            current_task_id = summary.get("current_task_id")
            if not current_task_id:
                break
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(2.0, remaining))
            status_result = await _fetch_status_snapshot(bridge, timeout=min(remaining, 15.0))
            summary = status_result["summary"]
            status_polls.append(status_result)

        result = {
            "prompt": prompt,
            "result": action_result,
            "watch": watch_result,
            "status": status_result,
            "status_polls": status_polls,
        }
        attempts.append(result)
        if validate(summary):
            return {
                "success": True,
                "attempt_count": attempt + 1,
                "attempts": attempts,
                "result": result,
            }
    return {
        "success": False,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "result": attempts[-1] if attempts else None,
    }


def _cargo_units(summary: dict[str, Any], commodity: str) -> int:
    cargo = summary.get("cargo")
    if not isinstance(cargo, dict):
        return 0
    value = cargo.get(commodity)
    return int(value) if isinstance(value, int) else 0


def _total_cargo_units(summary: dict[str, Any]) -> int:
    cargo = summary.get("cargo")
    if not isinstance(cargo, dict):
        return 0
    total = 0
    for value in cargo.values():
        if isinstance(value, int):
            total += value
    return total


def _status_warp(summary: dict[str, Any]) -> int | None:
    warp = summary.get("warp_power")
    return warp if isinstance(warp, int) else None


def _port_price(summary: dict[str, Any], commodity: str) -> int | None:
    port_prices = summary.get("port_prices")
    if not isinstance(port_prices, dict):
        return None
    price = port_prices.get(commodity)
    return int(price) if isinstance(price, int) else None


def _build_route_buy_prompt(summary: dict[str, Any], commodity: str) -> str:
    price = _port_price(summary, commodity)
    empty_holds = summary.get("empty_holds")
    credits = summary.get("ship_credits")
    if isinstance(price, int) and price > 0 and isinstance(empty_holds, int) and empty_holds > 0 and isinstance(credits, int):
        quantity = min(empty_holds, credits // price)
        if quantity > 0:
            return build_trade_order_prompt(
                trade_type="BUY",
                quantity=quantity,
                commodity=commodity,
                price_per_unit=price,
            )
    return build_buy_max_commodity_prompt(commodity=commodity)


def _build_route_sell_prompt(summary: dict[str, Any], commodity: str) -> str:
    price = _port_price(summary, commodity)
    quantity = _cargo_units(summary, commodity)
    if isinstance(price, int) and price >= 0 and quantity > 0:
        return build_trade_order_prompt(
            trade_type="SELL",
            quantity=quantity,
            commodity=commodity,
            price_per_unit=price,
        )
    return build_sell_all_commodity_prompt(commodity=commodity)


async def _run_corporation_explore_loop(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str,
    new_sectors_per_run: int,
    max_runs: int | None,
    target_known_sectors: int | None,
    target_corp_sectors: int | None,
    timeout: float,
) -> dict[str, Any]:
    if new_sectors_per_run <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--new-sectors-per-run must be > 0")
    if max_runs is not None and max_runs <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--max-runs must be > 0")
    if target_known_sectors is not None and target_known_sectors <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--target-known-sectors must be > 0")
    if target_corp_sectors is not None and target_corp_sectors <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--target-corp-sectors must be > 0")
    if timeout <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--event-timeout-seconds must be > 0")

    task_description = build_corporation_ship_explore_task_description(new_sectors=new_sectors_per_run)
    initial_status = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
    initial_ship = await _fetch_owned_ship_snapshot(
        bridge,
        ship_id=ship_id,
        ship_name=ship_name,
        timeout=min(timeout, 30.0),
    )
    current_summary = initial_status["summary"]
    current_ship = initial_ship["ship"]
    runs: list[dict[str, Any]] = []
    stop_reason = "not_started"

    while True:
        known_sectors = current_summary.get("known_sectors")
        corp_sectors = current_summary.get("corp_sectors_visited")
        if target_known_sectors is not None and isinstance(known_sectors, int) and known_sectors >= target_known_sectors:
            stop_reason = "target_known_sectors_reached"
            break
        if target_corp_sectors is not None and isinstance(corp_sectors, int) and corp_sectors >= target_corp_sectors:
            stop_reason = "target_corp_sectors_reached"
            break
        if max_runs is not None and len(runs) >= max_runs:
            stop_reason = "max_runs_reached"
            break

        prompt = build_corporation_ship_task_prompt(
            ship_name=ship_name,
            ship_id=ship_id,
            task_description=task_description,
        )
        action_result = await bridge.user_text_input(prompt)
        watch_result = await _watch_corporation_task(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            wait_for_finish=True,
            timeout=timeout,
        )
        status_result = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
        ship_result = await _fetch_owned_ship_snapshot(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            timeout=min(timeout, 30.0),
        )
        next_summary = status_result["summary"]
        next_ship = ship_result["ship"]
        run_summary = {
            "prompt": prompt,
            "result": action_result,
            "watch": watch_result,
            "status": status_result,
            "ship": ship_result,
            "start_sector": current_ship.get("sector"),
            "end_sector": next_ship.get("sector"),
            "delta_known_sectors": (
                next_summary.get("known_sectors") - current_summary.get("known_sectors")
                if isinstance(next_summary.get("known_sectors"), int)
                and isinstance(current_summary.get("known_sectors"), int)
                else None
            ),
            "delta_corp_sectors": (
                next_summary.get("corp_sectors_visited") - current_summary.get("corp_sectors_visited")
                if isinstance(next_summary.get("corp_sectors_visited"), int)
                and isinstance(current_summary.get("corp_sectors_visited"), int)
                else None
            ),
        }
        progress_observed = (
            run_summary["end_sector"] != run_summary["start_sector"]
            or run_summary["delta_known_sectors"] not in {None, 0}
            or run_summary["delta_corp_sectors"] not in {None, 0}
        )
        run_summary["progress_observed"] = progress_observed
        run_summary["task_completion_inferred"] = bool(progress_observed and not watch_result.get("task_finished"))
        runs.append(run_summary)
        current_summary = next_summary
        current_ship = next_ship

        if not watch_result.get("task_finished") and not progress_observed:
            stop_reason = watch_result.get("stop_reason") or "task_not_finished"
            break
        if current_ship.get("destroyed_at") is not None:
            stop_reason = "ship_destroyed"
            break
        if (
            run_summary["end_sector"] == run_summary["start_sector"]
            and run_summary["delta_known_sectors"] in {None, 0}
            and run_summary["delta_corp_sectors"] in {None, 0}
        ):
            stop_reason = "no_progress"
            break

    return {
        "stop_reason": stop_reason,
        "task_description": task_description,
        "initial_status": initial_status,
        "initial_ship": initial_ship,
        "runs": runs,
        "final_status": {
            "summary": current_summary,
        },
        "final_ship": current_ship,
    }


async def _run_trade_route_loop(
    bridge: HeadlessBridgeProcess,
    *,
    buy_sector: int,
    sell_sector: int,
    commodity: str,
    max_cycles: int | None,
    target_credits: int | None,
    min_warp: int,
    step_retries: int,
    timeout: float,
) -> dict[str, Any]:
    if buy_sector <= 0 or sell_sector <= 0:
        raise HeadlessBridgeError("session-trade-route-loop", "sector ids must be > 0")
    if max_cycles is not None and max_cycles <= 0:
        raise HeadlessBridgeError("session-trade-route-loop", "--max-cycles must be > 0")
    if target_credits is not None and target_credits <= 0:
        raise HeadlessBridgeError("session-trade-route-loop", "--target-credits must be > 0")
    if min_warp < 0:
        raise HeadlessBridgeError("session-trade-route-loop", "--min-warp must be >= 0")
    if step_retries < 0:
        raise HeadlessBridgeError("session-trade-route-loop", "--step-retries must be >= 0")

    initial_status = await _fetch_status_snapshot(bridge, timeout=timeout)
    current_summary = initial_status["summary"]
    cycle_results: list[dict[str, Any]] = []
    recovery_steps: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []

    while True:
        current_sector = current_summary.get("sector_id")
        current_credits = current_summary.get("ship_credits")
        commodity_units = _cargo_units(current_summary, commodity)
        total_cargo_units = _total_cargo_units(current_summary)
        current_warp = _status_warp(current_summary)

        if target_credits is not None and isinstance(current_credits, int) and current_credits >= target_credits:
            stop_reason = "target_credits_reached"
            break
        if max_cycles is not None and len(cycle_results) >= max_cycles:
            stop_reason = "max_cycles_reached"
            break
        if total_cargo_units > commodity_units:
            stop_reason = "foreign_cargo_present"
            break
        if commodity_units > 0:
            if current_sector != sell_sector:
                move_prompt = build_move_to_sector_prompt(sector_id=sell_sector)
                move_outcome = await _run_validated_player_step(
                    bridge,
                    prompt=move_prompt,
                    timeout=timeout,
                    retries=step_retries,
                    validate=lambda summary: summary.get("sector_id") == sell_sector,
                )
                move_result = move_outcome["result"]
                after_move = move_result["status"]["summary"] if isinstance(move_result, dict) else current_summary
                recovery_steps.append(
                    {
                        "step": "move_to_sell_sector",
                        "sector": sell_sector,
                        "result": move_result,
                        "attempt_count": move_outcome["attempt_count"],
                    }
                )
                steps.append(recovery_steps[-1])
                if not move_outcome["success"]:
                    stop_reason = "recovery_move_failed"
                    current_summary = after_move
                    break
                current_summary = after_move
            sell_prompt = _build_route_sell_prompt(current_summary, commodity)
            sell_outcome = await _run_validated_player_step(
                bridge,
                prompt=sell_prompt,
                timeout=timeout,
                retries=step_retries,
                validate=lambda summary: _cargo_units(summary, commodity) == 0,
            )
            sell_result = sell_outcome["result"]
            after_sell = sell_result["status"]["summary"] if isinstance(sell_result, dict) else current_summary
            recovery_steps.append(
                    {
                        "step": "recovery_sell_all",
                        "commodity": commodity,
                        "result": sell_result,
                        "attempt_count": sell_outcome["attempt_count"],
                    }
            )
            steps.append(recovery_steps[-1])
            current_summary = after_sell
            if not sell_outcome["success"]:
                stop_reason = "recovery_sell_failed"
                break
            continue

        if current_warp is not None and current_warp < min_warp:
            stop_reason = "min_warp_reached"
            break

        cycle_start = dict(current_summary)
        cycle_step_results: list[dict[str, Any]] = []

        if current_sector != buy_sector:
            move_to_buy_prompt = build_move_to_sector_prompt(sector_id=buy_sector)
            move_to_buy_outcome = await _run_validated_player_step(
                bridge,
                prompt=move_to_buy_prompt,
                timeout=timeout,
                retries=step_retries,
                validate=lambda summary: summary.get("sector_id") == buy_sector,
            )
            move_to_buy_result = move_to_buy_outcome["result"]
            after_move_to_buy = (
                move_to_buy_result["status"]["summary"] if isinstance(move_to_buy_result, dict) else current_summary
            )
            cycle_step_results.append(
                {
                    "step": "move_to_buy_sector",
                    "sector": buy_sector,
                    "result": move_to_buy_result,
                    "attempt_count": move_to_buy_outcome["attempt_count"],
                }
            )
            steps.append(cycle_step_results[-1])
            if not move_to_buy_outcome["success"]:
                stop_reason = "move_to_buy_failed"
                current_summary = after_move_to_buy
                break
            current_summary = after_move_to_buy

        buy_prompt = _build_route_buy_prompt(current_summary, commodity)
        buy_outcome = await _run_validated_player_step(
            bridge,
            prompt=buy_prompt,
            timeout=timeout,
            retries=step_retries,
            validate=lambda summary: _cargo_units(summary, commodity) > 0,
        )
        buy_result = buy_outcome["result"]
        after_buy = buy_result["status"]["summary"] if isinstance(buy_result, dict) else current_summary
        cycle_step_results.append(
            {
                "step": "buy_max",
                "commodity": commodity,
                "result": buy_result,
                "attempt_count": buy_outcome["attempt_count"],
            }
        )
        steps.append(cycle_step_results[-1])
        if not buy_outcome["success"]:
            stop_reason = "buy_failed"
            current_summary = after_buy
            break
        current_summary = after_buy

        move_to_sell_prompt = build_move_to_sector_prompt(sector_id=sell_sector)
        move_to_sell_outcome = await _run_validated_player_step(
            bridge,
            prompt=move_to_sell_prompt,
            timeout=timeout,
            retries=step_retries,
            validate=lambda summary: summary.get("sector_id") == sell_sector,
        )
        move_to_sell_result = move_to_sell_outcome["result"]
        after_move_to_sell = (
            move_to_sell_result["status"]["summary"] if isinstance(move_to_sell_result, dict) else current_summary
        )
        cycle_step_results.append(
            {
                "step": "move_to_sell_sector",
                "sector": sell_sector,
                "result": move_to_sell_result,
                "attempt_count": move_to_sell_outcome["attempt_count"],
            }
        )
        steps.append(cycle_step_results[-1])
        if not move_to_sell_outcome["success"]:
            stop_reason = "move_to_sell_failed"
            current_summary = after_move_to_sell
            break
        current_summary = after_move_to_sell

        sell_prompt = _build_route_sell_prompt(current_summary, commodity)
        sell_outcome = await _run_validated_player_step(
            bridge,
            prompt=sell_prompt,
            timeout=timeout,
            retries=step_retries,
            validate=lambda summary: _cargo_units(summary, commodity) == 0,
        )
        sell_result = sell_outcome["result"]
        after_sell = sell_result["status"]["summary"] if isinstance(sell_result, dict) else current_summary
        cycle_step_results.append(
            {
                "step": "sell_all",
                "commodity": commodity,
                "result": sell_result,
                "attempt_count": sell_outcome["attempt_count"],
            }
        )
        steps.append(cycle_step_results[-1])
        if not sell_outcome["success"]:
            stop_reason = "sell_failed"
            current_summary = after_sell
            break

        cycle_end = dict(after_sell)
        cycle_results.append(
            {
                "cycle": len(cycle_results) + 1,
                "buy_sector": buy_sector,
                "sell_sector": sell_sector,
                "commodity": commodity,
                "start": cycle_start,
                "end": cycle_end,
                "profit": (
                    cycle_end["ship_credits"] - cycle_start["ship_credits"]
                    if isinstance(cycle_end.get("ship_credits"), int)
                    and isinstance(cycle_start.get("ship_credits"), int)
                    else None
                ),
                "warp_spent": (
                    cycle_start["warp_power"] - cycle_end["warp_power"]
                    if isinstance(cycle_end.get("warp_power"), int)
                    and isinstance(cycle_start.get("warp_power"), int)
                    else None
                ),
                "steps": cycle_step_results,
            }
        )
        current_summary = cycle_end

    return {
        "success": stop_reason in {"target_credits_reached", "max_cycles_reached", "min_warp_reached"},
        "stop_reason": stop_reason,
        "buy_sector": buy_sector,
        "sell_sector": sell_sector,
        "commodity": commodity,
        "target_credits": target_credits,
        "max_cycles": max_cycles,
        "min_warp": min_warp,
        "step_retries": step_retries,
        "cycles_completed": len(cycle_results),
        "initial_status": initial_status["summary"],
        "final_status": current_summary,
        "cycle_results": cycle_results,
        "recovery_steps": recovery_steps,
        "steps": steps,
    }


async def _wait_for_named_server_event(
    bridge: HeadlessBridgeProcess,
    *,
    event_names: set[str],
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError("wait_for_server_event", "--event-timeout-seconds must be > 0")

    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            event = await bridge.next_event(timeout=remaining)
        except asyncio.TimeoutError:
            break
        server_event = _extract_server_event(event)
        if not isinstance(server_event, dict):
            continue
        event_name = server_event.get("event")
        if isinstance(event_name, str) and event_name in event_names:
            return {
                "success": True,
                "stop_reason": "matched_event",
                "matched_event": event_name,
                "server_event": server_event,
            }

    return {
        "success": False,
        "stop_reason": "timeout",
        "matched_event": None,
        "server_event": None,
    }


async def _wait_for_first_combat_event(
    bridge: HeadlessBridgeProcess,
    *,
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError("session-engage-combat", "--event-timeout-seconds must be > 0")

    combat_events = {
        "combat.round_waiting",
        "combat.action_accepted",
        "combat.action_response",
        "combat.round_resolved",
        "combat.ended",
    }
    deadline = asyncio.get_running_loop().time() + timeout
    task_start = None
    task_finish = None

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            event = await bridge.next_event(timeout=remaining)
        except asyncio.TimeoutError:
            break
        server_event = _extract_server_event(event)
        if not isinstance(server_event, dict):
            continue
        event_name = server_event.get("event")
        if event_name == "task.start":
            task_start = server_event
            continue
        if event_name == "task.finish":
            task_finish = server_event
            continue
        if isinstance(event_name, str) and event_name in combat_events:
            return {
                "success": True,
                "stop_reason": "combat_event",
                "matched_event": event_name,
                "server_event": server_event,
                "task_start": task_start,
                "task_finish": task_finish,
            }

    return {
        "success": False,
        "stop_reason": "timeout",
        "matched_event": None,
        "server_event": None,
        "task_start": task_start,
        "task_finish": task_finish,
    }


def _extract_status_ship_name(server_event: dict[str, Any] | None) -> str | None:
    if not isinstance(server_event, dict):
        return None
    payload = server_event.get("payload")
    if not isinstance(payload, dict):
        return None
    ship = payload.get("ship")
    if not isinstance(ship, dict):
        return None
    ship_name = ship.get("ship_name")
    return ship_name if isinstance(ship_name, str) else None


async def _wait_for_owned_ship(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str,
    timeout: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError(
            "session-collect-unowned-ship",
            "--event-timeout-seconds must be > 0",
        )
    if poll_interval_seconds <= 0:
        raise HeadlessBridgeError(
            "session-collect-unowned-ship",
            "--poll-interval-seconds must be > 0",
        )

    deadline = asyncio.get_running_loop().time() + timeout
    polls = 0
    poll_errors: list[str] = []
    latest_ships_event = None

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        polls += 1
        try:
            ships_result = await bridge.get_my_ships(timeout=min(15.0, max(5.0, remaining)))
        except HeadlessBridgeError as exc:
            poll_errors.append(str(exc))
        else:
            latest_ships_event = ships_result.get("server_event")
            matched_ship = _select_ship_from_ships_event(
                latest_ships_event,
                ship_id=ship_id,
                ship_name=None,
            )
            if matched_ship is not None:
                return {
                    "success": True,
                    "stop_reason": "ship_visible",
                    "polls": polls,
                    "poll_errors": poll_errors,
                    "matched_ship": matched_ship,
                }

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "stop_reason": "timeout",
        "polls": polls,
        "poll_errors": poll_errors,
        "matched_ship": _select_ship_from_ships_event(
            latest_ships_event,
            ship_id=ship_id,
            ship_name=None,
        ),
    }


async def _wait_for_status_ship_name(
    bridge: HeadlessBridgeProcess,
    *,
    ship_name: str,
    timeout: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError("session-rename-ship", "--event-timeout-seconds must be > 0")
    if poll_interval_seconds <= 0:
        raise HeadlessBridgeError(
            "session-rename-ship",
            "--poll-interval-seconds must be > 0",
        )

    deadline = asyncio.get_running_loop().time() + timeout
    polls = 0
    poll_errors: list[str] = []
    latest_status_event = None

    wanted_ship_name = _normalize_compare_text(ship_name)
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        polls += 1
        try:
            status_result = await bridge.get_my_status(timeout=min(15.0, max(5.0, remaining)))
        except HeadlessBridgeError as exc:
            poll_errors.append(str(exc))
        else:
            latest_status_event = status_result.get("server_event")
            if _normalize_compare_text(_extract_status_ship_name(latest_status_event)) == wanted_ship_name:
                return {
                    "success": True,
                    "stop_reason": "ship_renamed",
                    "polls": polls,
                    "poll_errors": poll_errors,
                    "matched_ship_name": _extract_status_ship_name(latest_status_event),
                    "status": latest_status_event,
                }

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "stop_reason": "timeout",
        "polls": polls,
        "poll_errors": poll_errors,
        "matched_ship_name": _extract_status_ship_name(latest_status_event),
        "status": latest_status_event,
    }


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


def _last_quest_status_event(
    events: list[Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    latest = fallback
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") != "server_message":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("event") != "quest.status":
            continue
        latest = data
    return latest


def _collect_claimable_reward_steps(
    quest_status_event: dict[str, Any] | None,
    *,
    quest_code: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(quest_status_event, dict):
        return []

    payload = quest_status_event.get("payload")
    if not isinstance(payload, dict):
        return []

    quests = payload.get("quests")
    if not isinstance(quests, list):
        return []

    filtered_code = (quest_code or "").strip() or None
    claimable: list[dict[str, Any]] = []
    for quest in quests:
        if not isinstance(quest, dict):
            continue
        current_code = quest.get("code")
        if filtered_code and current_code != filtered_code:
            continue
        quest_id = quest.get("quest_id")
        if not isinstance(quest_id, str) or not quest_id:
            continue
        completed_steps = quest.get("completed_steps")
        if not isinstance(completed_steps, list):
            continue
        for step in completed_steps:
            if not isinstance(step, dict):
                continue
            if not step.get("completed") or step.get("reward_claimed"):
                continue
            step_id = step.get("step_id")
            if not isinstance(step_id, str) or not step_id:
                continue
            claimable.append(
                {
                    "quest_code": current_code,
                    "quest_id": quest_id,
                    "step_id": step_id,
                    "step_index": step.get("step_index"),
                    "step_name": step.get("name"),
                    "reward_credits": step.get("reward_credits"),
                }
            )

    claimable.sort(
        key=lambda item: (
            str(item.get("quest_code") or ""),
            int(item["step_index"]) if isinstance(item.get("step_index"), int) else 0,
            str(item.get("step_id") or ""),
        )
    )
    return claimable


def _mark_reward_claimed(
    quest_status_event: dict[str, Any] | None,
    *,
    quest_id: str,
    step_id: str,
) -> None:
    if not isinstance(quest_status_event, dict):
        return

    payload = quest_status_event.get("payload")
    if not isinstance(payload, dict):
        return

    quests = payload.get("quests")
    if not isinstance(quests, list):
        return

    for quest in quests:
        if not isinstance(quest, dict):
            continue
        if quest.get("quest_id") != quest_id:
            continue
        completed_steps = quest.get("completed_steps")
        if not isinstance(completed_steps, list):
            return
        for step in completed_steps:
            if not isinstance(step, dict):
                continue
            if step.get("step_id") == step_id:
                step["reward_claimed"] = True
                return


def _quest_status_summary(quest_status_event: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(quest_status_event, dict):
        return []

    payload = quest_status_event.get("payload")
    if not isinstance(payload, dict):
        return []

    quests = payload.get("quests")
    if not isinstance(quests, list):
        return []

    summary: list[dict[str, Any]] = []
    for quest in quests:
        if not isinstance(quest, dict):
            continue
        current_step = quest.get("current_step")
        current_step_name = None
        if isinstance(current_step, dict):
            current_step_name = current_step.get("name")
        summary.append(
            {
                "quest_code": quest.get("code"),
                "quest_id": quest.get("quest_id"),
                "status": quest.get("status"),
                "current_step_index": quest.get("current_step_index"),
                "current_step_name": current_step_name,
                "claimable_reward_steps": len(
                    _collect_claimable_reward_steps(
                        {
                            "payload": {
                                "quests": [quest],
                            }
                        }
                    )
                ),
            }
        )
    return summary


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


def _leaderboard_self_summary(
    *,
    config: HeadlessConfig,
    leaderboard_result: dict[str, Any],
    status_result: dict[str, Any],
    ships_result: dict[str, Any],
    transport: str,
) -> dict[str, Any]:
    status_payload = _extract_bridge_payload(status_result)
    ships_payload = _extract_bridge_payload(ships_result)
    player = status_payload.get("player") if isinstance(status_payload, dict) else None
    ship = status_payload.get("ship") if isinstance(status_payload, dict) else None
    source = status_payload.get("source") if isinstance(status_payload, dict) else None
    ships = ships_payload.get("ships") if isinstance(ships_payload, dict) else None

    player_name = player.get("name") if isinstance(player, dict) else None
    character_id = player.get("id") if isinstance(player, dict) else None
    if not isinstance(player_name, str) or not player_name:
        player_name = config.character_name
    if not isinstance(character_id, str) or not character_id:
        character_id = config.character_id

    wealth_rows = _human_leaderboard_rows(leaderboard_result.get("wealth"), "total_wealth")
    trading_rows = _human_leaderboard_rows(leaderboard_result.get("trading"), "total_trade_volume")
    exploration_rows = _human_leaderboard_rows(leaderboard_result.get("exploration"), "sectors_visited")

    wealth_entry = _find_leaderboard_entry(wealth_rows, character_id)
    trading_entry = _find_leaderboard_entry(trading_rows, character_id)
    exploration_entry = _find_leaderboard_entry(exploration_rows, character_id)

    wealth_estimate = _estimate_visible_wealth(ships, player)

    exploration_value = (
        _coerce_int(exploration_entry.get("sectors_visited"))
        if isinstance(exploration_entry, dict)
        else _estimate_exploration_value(player)
    )
    reported_sectors_visited = _coerce_int(player.get("sectors_visited")) if isinstance(player, dict) else 0
    corp_sectors_visited = _coerce_int(player.get("corp_sectors_visited")) if isinstance(player, dict) else None
    total_sectors_known = _coerce_int(player.get("total_sectors_known")) if isinstance(player, dict) else None

    wealth_leader = wealth_rows[0] if wealth_rows else None
    trading_leader = trading_rows[0] if trading_rows else None
    exploration_leader = exploration_rows[0] if exploration_rows else None

    return {
        "player_name": player_name,
        "character_id": character_id,
        "transport": transport,
        "leaderboard_cached": bool(leaderboard_result.get("cached")),
        "status_timestamp": source.get("timestamp") if isinstance(source, dict) else None,
        "summary": {
            "wealth": {
                "self": {
                    "estimated_total_wealth": wealth_estimate["total_wealth"],
                    "bank_credits": wealth_estimate["bank_credits"],
                    "ship_credits": wealth_estimate["ship_credits"],
                    "cargo_value": wealth_estimate["cargo_value"],
                    "ship_value": wealth_estimate["ship_value"],
                    "ships_owned_visible": wealth_estimate["ships_owned_visible"],
                    "corp_ships_visible": wealth_estimate["corp_ships_visible"],
                    "active_ship_name": ship.get("ship_name") if isinstance(ship, dict) else None,
                    "active_ship_type": ship.get("ship_type") if isinstance(ship, dict) else None,
                    "note": "Estimated from live visible ships plus bank credits.",
                },
                "leader": _leader_summary(wealth_leader, "total_wealth"),
                "leaderboard": _leaderboard_position(
                    wealth_rows,
                    wealth_entry,
                    "total_wealth",
                    wealth_estimate["total_wealth"],
                ),
            },
            "trading": {
                "self": (
                    {
                        "total_trade_volume": _coerce_int(trading_entry.get("total_trade_volume")),
                        "total_trades": _coerce_int(trading_entry.get("total_trades")),
                        "ports_visited": _coerce_int(trading_entry.get("ports_visited")),
                        "note": "Exact only when your row is present on the visible board.",
                    }
                    if isinstance(trading_entry, dict)
                    else {
                        "total_trade_volume": None,
                        "total_trades": None,
                        "ports_visited": None,
                        "note": "Unavailable from current self-read surfaces when off the visible board.",
                    }
                ),
                "leader": _leader_summary(trading_leader, "total_trade_volume"),
                "leaderboard": _leaderboard_position(
                    trading_rows,
                    trading_entry,
                    "total_trade_volume",
                    _coerce_int(trading_entry.get("total_trade_volume")) if isinstance(trading_entry, dict) else None,
                ),
            },
            "exploration": {
                "self": {
                    "estimated_sectors_visited": exploration_value,
                    "sectors_visited": reported_sectors_visited,
                    "corp_sectors_visited": corp_sectors_visited,
                    "total_sectors_known": total_sectors_known,
                    "note": "Estimate prefers the production leaderboard row when visible and otherwise falls back to live known-sector counts because leaderboard exploration unions personal and corporation discovery.",
                },
                "leader": _leader_summary(exploration_leader, "sectors_visited"),
                "leaderboard": _leaderboard_position(
                    exploration_rows,
                    exploration_entry,
                    "sectors_visited",
                    exploration_value,
                ),
            },
        },
    }


def _extract_bridge_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    server_event = result.get("server_event")
    if not isinstance(server_event, dict):
        return {}
    data = server_event.get("data")
    if not isinstance(data, dict):
        return {}
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return {}
    return payload


def _human_leaderboard_rows(entries: Any, stat_key: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    rows = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("player_type") == "human"
    ]
    rows.sort(key=lambda entry: _coerce_int(entry.get(stat_key)), reverse=True)
    return rows


def _find_leaderboard_entry(
    rows: list[dict[str, Any]],
    character_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(character_id, str) or not character_id:
        return None
    for row in rows:
        if row.get("player_id") == character_id:
            return row
    return None


def _leader_summary(entry: dict[str, Any] | None, stat_key: str) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    summary = {
        "player_name": entry.get("player_name"),
        "value": _coerce_int(entry.get(stat_key)),
    }
    if stat_key == "total_wealth":
        summary["ships_owned"] = _coerce_int(entry.get("ships_owned"))
    if stat_key == "total_trade_volume":
        summary["total_trades"] = _coerce_int(entry.get("total_trades"))
        summary["ports_visited"] = _coerce_int(entry.get("ports_visited"))
    return summary


def _leaderboard_position(
    rows: list[dict[str, Any]],
    own_entry: dict[str, Any] | None,
    stat_key: str,
    self_value: int | None,
) -> dict[str, Any]:
    floor_entry = rows[-1] if rows else None
    leader_entry = rows[0] if rows else None
    visible_rank = None
    if isinstance(own_entry, dict):
        try:
            visible_rank = rows.index(own_entry) + 1
        except ValueError:
            visible_rank = None

    floor_value = _coerce_int(floor_entry.get(stat_key)) if isinstance(floor_entry, dict) else None
    leader_value = _coerce_int(leader_entry.get(stat_key)) if isinstance(leader_entry, dict) else None

    gap_to_visible_floor = None
    if self_value is not None and floor_value is not None:
        gap_to_visible_floor = max(0, floor_value - self_value)

    gap_to_leader = None
    if self_value is not None and leader_value is not None:
        gap_to_leader = max(0, leader_value - self_value)

    return {
        "visible_rank": visible_rank,
        "off_visible_board": visible_rank is None,
        "visible_board_size": len(rows),
        "visible_floor": (
            {
                "player_name": floor_entry.get("player_name"),
                "value": floor_value,
            }
            if isinstance(floor_entry, dict)
            else None
        ),
        "gap_to_visible_floor": gap_to_visible_floor,
        "gap_to_leader": gap_to_leader,
    }


def _estimate_visible_wealth(ships: Any, player: Any) -> dict[str, int]:
    bank_credits = _coerce_int(player.get("credits_in_bank")) if isinstance(player, dict) else 0
    ship_credits = 0
    cargo_value = 0
    ship_value = 0
    ships_owned_visible = 0
    corp_ships_visible = 0
    ship_base_values = _load_ship_base_values()

    if isinstance(ships, list):
        for ship in ships:
            if not isinstance(ship, dict):
                continue
            if ship.get("destroyed_at") is not None:
                continue
            ships_owned_visible += 1
            if ship.get("owner_type") == "corporation":
                corp_ships_visible += 1
            ship_credits += _coerce_int(ship.get("credits"))
            cargo = ship.get("cargo")
            if isinstance(cargo, dict):
                cargo_value += (
                    _coerce_int(cargo.get("quantum_foam"))
                    + _coerce_int(cargo.get("retro_organics"))
                    + _coerce_int(cargo.get("neuro_symbolics"))
                ) * 100
            ship_type = ship.get("ship_type")
            if isinstance(ship_type, str):
                ship_value += ship_base_values.get(ship_type, 0)

    return {
        "total_wealth": bank_credits + ship_credits + cargo_value + ship_value,
        "bank_credits": bank_credits,
        "ship_credits": ship_credits,
        "cargo_value": cargo_value,
        "ship_value": ship_value,
        "ships_owned_visible": ships_owned_visible,
        "corp_ships_visible": corp_ships_visible,
    }


def _estimate_exploration_value(player: Any) -> int:
    if not isinstance(player, dict):
        return 0
    total_known = _coerce_int(player.get("total_sectors_known"))
    sectors_visited = _coerce_int(player.get("sectors_visited"))
    corp_sectors_visited = _coerce_int(player.get("corp_sectors_visited"))
    return max(total_known, sectors_visited, corp_sectors_visited)


def _load_ship_base_values() -> dict[str, int]:
    ships_file = repo_root() / "upstream" / "client" / "app" / "src" / "types" / "ships.ts"
    try:
        text = ships_file.read_text()
    except OSError:
        return {}

    ship_type_re = re.compile(r'ship_type:\s*"([^"]+)"')
    base_value_re = re.compile(r"base_value:\s*(\d+)")
    current_ship_type: str | None = None
    values: dict[str, int] = {}

    for line in text.splitlines():
        ship_match = ship_type_re.search(line)
        if ship_match:
            current_ship_type = ship_match.group(1)
            continue
        base_match = base_value_re.search(line)
        if base_match and current_ship_type:
            values[current_ship_type] = int(base_match.group(1))
            current_ship_type = None

    return values


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise HeadlessApiError("cli", 0, "expected a JSON object")
    return parsed

if __name__ == "__main__":
    raise SystemExit(main())
