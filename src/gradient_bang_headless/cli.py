from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import deque
from typing import Any

from .config import HeadlessConfig, repo_root, update_dotenv
from .bridge import HeadlessBridgeError, HeadlessBridgeProcess, SessionConnectOptions
from .frontend_prompts import (
    build_buy_max_commodity_prompt,
    build_corporation_ship_move_to_sector_task_description,
    build_recharge_warp_prompt,
    build_corporation_ship_explore_task_description,
    build_corporation_ship_transfer_warp_task_description,
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
    build_transfer_warp_prompt,
)
from .http import (
    EventScope,
    HeadlessApiClient,
    HeadlessApiError,
    StartOptions,
    dump_json,
)
from .session_loop import LoopTargets, SessionLoopOptions, SessionLoopRunner


RESOURCE_PORT_CODE_ORDER = [
    "quantum_foam",
    "retro_organics",
    "neuro_symbolics",
]


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

    leaderboard_neighbors = sub.add_parser(
        "leaderboard-neighbors",
        help="Show the nearest visible leaderboard rows above and below the current player",
    )
    _add_session_connect_args(leaderboard_neighbors)
    leaderboard_neighbors.add_argument("--force-refresh", action="store_true")
    leaderboard_neighbors.add_argument("--event-timeout-seconds", type=float, default=30.0)

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

    session_nearest_mega_port = sub.add_parser(
        "session-nearest-mega-port",
        help="Connect a session, inspect the known map, and rank the nearest known mega-ports",
    )
    _add_session_connect_args(session_nearest_mega_port)
    session_nearest_mega_port.add_argument("--limit", type=int, default=5)
    session_nearest_mega_port.add_argument("--map-max-hops", type=int, default=100)
    session_nearest_mega_port.add_argument("--map-max-sectors", type=int, default=2000)
    session_nearest_mega_port.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_trade_opportunities = sub.add_parser(
        "session-trade-opportunities",
        help="Connect a session, read current status plus known ports, and rank the best visible trade routes",
    )
    _add_session_connect_args(session_trade_opportunities)
    session_trade_opportunities.add_argument(
        "--commodity",
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
        action="append",
        dest="commodities",
        default=[],
    )
    session_trade_opportunities.add_argument("--limit", type=int, default=10)
    session_trade_opportunities.add_argument("--map-max-hops", type=int, default=30)
    session_trade_opportunities.add_argument("--map-max-sectors", type=int, default=500)
    session_trade_opportunities.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_auto_trade_loop = sub.add_parser(
        "session-auto-trade-loop",
        help="Connect a session, rank visible routes for a leaderboard goal, and run the chosen deterministic trade loop",
    )
    _add_session_connect_args(session_auto_trade_loop)
    session_auto_trade_loop.add_argument(
        "--goal",
        choices=["wealth", "trading", "profit"],
        default="wealth",
    )
    session_auto_trade_loop.add_argument(
        "--commodity",
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
        action="append",
        dest="commodities",
        default=[],
    )
    session_auto_trade_loop.add_argument("--limit", type=int, default=10)
    session_auto_trade_loop.add_argument("--map-max-hops", type=int, default=30)
    session_auto_trade_loop.add_argument("--map-max-sectors", type=int, default=500)
    session_auto_trade_loop.add_argument("--max-cycles", type=int)
    session_auto_trade_loop.add_argument("--target-credits", type=int)
    session_auto_trade_loop.add_argument("--min-warp", type=int, default=50)
    session_auto_trade_loop.add_argument("--step-retries", type=int, default=1)
    session_auto_trade_loop.add_argument("--event-timeout-seconds", type=float, default=60.0)

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

    session_frontier_candidates = sub.add_parser(
        "session-frontier-candidates",
        help="Connect a session, inspect visited/unvisited map nodes, and rank the best frontier sectors for exploration",
    )
    _add_session_connect_args(session_frontier_candidates)
    session_frontier_candidates.add_argument("--center-sector", type=int)
    session_frontier_candidates.add_argument("--ship-name")
    session_frontier_candidates.add_argument("--ship-id")
    session_frontier_candidates.add_argument("--limit", type=int, default=10)
    session_frontier_candidates.add_argument("--max-hops", type=int, default=8)
    session_frontier_candidates.add_argument("--max-sectors", type=int, default=500)
    session_frontier_candidates.add_argument(
        "--validate-limit",
        type=int,
        default=10,
        help="How many top stub-bearing candidates to validate by probing whether their stub sectors are centerable; 0 disables validation",
    )
    session_frontier_candidates.add_argument("--event-timeout-seconds", type=float, default=30.0)

    session_probe_frontier_loop = sub.add_parser(
        "session-probe-frontier-loop",
        help="Connect a session, find the best validated frontier branch, move a probe there, and run one bounded exploration pass per branch",
    )
    _add_session_connect_args(session_probe_frontier_loop)
    session_probe_frontier_loop.add_argument("--ship-name", required=True)
    session_probe_frontier_loop.add_argument("--ship-id")
    session_probe_frontier_loop.add_argument("--search-center-sector", type=int)
    session_probe_frontier_loop.add_argument("--candidate-limit", type=int, default=12)
    session_probe_frontier_loop.add_argument("--max-hops", type=int, default=10)
    session_probe_frontier_loop.add_argument("--max-sectors", type=int, default=2000)
    session_probe_frontier_loop.add_argument("--validate-limit", type=int, default=12)
    session_probe_frontier_loop.add_argument("--max-frontiers", type=int, default=3)
    session_probe_frontier_loop.add_argument("--new-sectors-per-run", type=int, default=10)
    session_probe_frontier_loop.add_argument("--event-timeout-seconds", type=float, default=180.0)

    session_probe_fleet_loop = sub.add_parser(
        "session-probe-fleet-loop",
        help="Connect once, select eligible corporation probes, then run one probe-frontier worker subprocess per ship",
    )
    _add_session_connect_args(session_probe_fleet_loop)
    session_probe_fleet_loop.add_argument("--ship-name", action="append", dest="ship_names", default=[])
    session_probe_fleet_loop.add_argument("--ship-id", action="append", dest="ship_ids", default=[])
    session_probe_fleet_loop.add_argument("--search-center-sector", type=int)
    session_probe_fleet_loop.add_argument("--candidate-limit", type=int, default=12)
    session_probe_fleet_loop.add_argument("--max-hops", type=int, default=10)
    session_probe_fleet_loop.add_argument("--max-sectors", type=int, default=2000)
    session_probe_fleet_loop.add_argument("--validate-limit", type=int, default=12)
    session_probe_fleet_loop.add_argument("--max-frontiers", type=int, default=1)
    session_probe_fleet_loop.add_argument("--new-sectors-per-run", type=int, default=10)
    session_probe_fleet_loop.add_argument("--min-probe-warp", type=int, default=1)
    session_probe_fleet_loop.add_argument("--parallelism", type=int, default=4)
    session_probe_fleet_loop.add_argument("--max-probes", type=int)
    session_probe_fleet_loop.add_argument("--event-timeout-seconds", type=float, default=180.0)

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

    session_move_to_sector = sub.add_parser(
        "session-move-to-sector",
        help="Connect a session, send the exact move-to-sector prompt, and validate arrival",
    )
    _add_session_connect_args(session_move_to_sector)
    session_move_to_sector.add_argument("--sector-id", required=True, type=int)
    session_move_to_sector.add_argument("--step-retries", type=int, default=1)
    session_move_to_sector.add_argument("--max-segments", type=int, default=12)
    session_move_to_sector.add_argument("--event-timeout-seconds", type=float, default=60.0)

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
    session_transfer_credits.set_defaults(wait_for_finish=True)
    session_transfer_credits.add_argument("--amount", required=True, type=int)
    session_transfer_credits.add_argument("--to-ship-name", required=True)
    session_transfer_credits.add_argument("--to-ship-id")
    session_transfer_credits.add_argument("--wait-for-finish", action="store_true")
    session_transfer_credits.add_argument(
        "--no-wait-for-finish",
        action="store_false",
        dest="wait_for_finish",
        help="Return after task start instead of waiting for task completion",
    )
    session_transfer_credits.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_transfer_warp = sub.add_parser(
        "session-transfer-warp",
        help="Connect a session, transfer warp power to another ship in-sector via the proven player-task prompt, and watch task lifecycle events",
    )
    _add_session_connect_args(session_transfer_warp)
    session_transfer_warp.set_defaults(wait_for_finish=True)
    session_transfer_warp.add_argument("--units", required=True, type=int)
    session_transfer_warp.add_argument("--to-ship-name", required=True)
    session_transfer_warp.add_argument("--to-ship-id")
    session_transfer_warp.add_argument("--wait-for-finish", action="store_true")
    session_transfer_warp.add_argument(
        "--no-wait-for-finish",
        action="store_false",
        dest="wait_for_finish",
        help="Return after task start instead of waiting for task completion",
    )
    session_transfer_warp.add_argument("--event-timeout-seconds", type=float, default=60.0)

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

    session_shuttle_loop = sub.add_parser(
        "session-shuttle-loop",
        help="Connect a session and run a two-leg shuttle loop between fixed sectors with exact trade orders on both ends",
    )
    _add_session_connect_args(session_shuttle_loop)
    session_shuttle_loop.add_argument("--home-sector", required=True, type=int)
    session_shuttle_loop.add_argument("--away-sector", required=True, type=int)
    session_shuttle_loop.add_argument(
        "--home-commodity",
        required=True,
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
    )
    session_shuttle_loop.add_argument(
        "--away-commodity",
        required=True,
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
    )
    session_shuttle_loop.add_argument("--max-cycles", type=int)
    session_shuttle_loop.add_argument("--target-credits", type=int)
    session_shuttle_loop.add_argument("--min-warp", type=int, default=50)
    session_shuttle_loop.add_argument("--step-retries", type=int, default=1)
    session_shuttle_loop.add_argument(
        "--finish-loaded-home",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_shuttle_loop.add_argument("--event-timeout-seconds", type=float, default=60.0)

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

    session_liquidate_cargo = sub.add_parser(
        "session-liquidate-cargo",
        help="Connect a session, route to a legal buyer for the current cargo, and liquidate it with an exact sell order",
    )
    _add_session_connect_args(session_liquidate_cargo)
    session_liquidate_cargo.add_argument(
        "--commodity",
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
        help="Cargo commodity to liquidate; defaults to inferring the only loaded commodity",
    )
    session_liquidate_cargo.add_argument(
        "--goal",
        choices=["nearest", "best-price", "best-price-per-hop"],
        default="best-price-per-hop",
    )
    session_liquidate_cargo.add_argument("--step-retries", type=int, default=1)
    session_liquidate_cargo.add_argument("--max-segments", type=int, default=8)
    session_liquidate_cargo.add_argument("--map-max-hops", type=int, default=20)
    session_liquidate_cargo.add_argument("--map-max-sectors", type=int, default=500)
    session_liquidate_cargo.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_load_cargo = sub.add_parser(
        "session-load-cargo",
        help="Connect a session and buy a specific commodity at the current port with an exact trade order",
    )
    _add_session_connect_args(session_load_cargo)
    session_load_cargo.add_argument(
        "--commodity",
        required=True,
        choices=["quantum_foam", "retro_organics", "neuro_symbolics"],
    )
    session_load_cargo.add_argument("--quantity", type=int)
    session_load_cargo.set_defaults(wait_for_task_finish=True)
    session_load_cargo.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_load_cargo.add_argument("--event-timeout-seconds", type=float, default=45.0)

    session_wealth_loadout = sub.add_parser(
        "session-wealth-loadout",
        help="Connect a session and buy the cheapest currently sellable cargo to maximize immediate leaderboard wealth",
    )
    _add_session_connect_args(session_wealth_loadout)
    session_wealth_loadout.set_defaults(wait_for_task_finish=True)
    session_wealth_loadout.add_argument(
        "--wait-for-task-finish",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_wealth_loadout.add_argument("--event-timeout-seconds", type=float, default=45.0)

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
    session_purchase_corp_ship.add_argument("--count", type=int, default=1)
    session_purchase_corp_ship.add_argument(
        "--start-session",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    session_purchase_corp_ship.add_argument("--start-wait-seconds", type=float, default=1.0)
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

    session_corp_move_to_sector = sub.add_parser(
        "session-corp-move-to-sector",
        help="Connect a session and keep reissuing the proven corp move prompt until the ship arrives or stops making progress",
    )
    _add_session_connect_args(session_corp_move_to_sector)
    session_corp_move_to_sector.add_argument("--ship-name", required=True)
    session_corp_move_to_sector.add_argument("--ship-id")
    session_corp_move_to_sector.add_argument("--sector-id", required=True, type=int)
    session_corp_move_to_sector.add_argument("--max-segments", type=int, default=12)
    session_corp_move_to_sector.add_argument("--event-timeout-seconds", type=float, default=60.0)

    session_corp_explore_loop = sub.add_parser(
        "session-corp-explore-loop",
        help="Connect a session, send repeated frontier exploration tasks for a corporation ship, and stop on explicit targets",
    )
    _add_session_connect_args(session_corp_explore_loop)
    session_corp_explore_loop.add_argument("--ship-name", required=True)
    session_corp_explore_loop.add_argument("--ship-id")
    session_corp_explore_loop.add_argument(
        "--start-sector",
        type=int,
        help="Optional known frontier sector to move the corporation ship to before starting exploration",
    )
    session_corp_explore_loop.add_argument("--new-sectors-per-run", type=int, default=20)
    session_corp_explore_loop.add_argument("--max-runs", type=int)
    session_corp_explore_loop.add_argument("--target-known-sectors", type=int)
    session_corp_explore_loop.add_argument("--target-corp-sectors", type=int)
    session_corp_explore_loop.add_argument("--event-timeout-seconds", type=float, default=180.0)

    session_corp_transfer_warp = sub.add_parser(
        "session-corp-transfer-warp",
        help="Connect a session, task a corporation ship to transfer warp power in-sector, and watch task lifecycle events",
    )
    _add_session_connect_args(session_corp_transfer_warp)
    session_corp_transfer_warp.set_defaults(wait_for_finish=True)
    session_corp_transfer_warp.add_argument("--ship-name", required=True)
    session_corp_transfer_warp.add_argument("--ship-id")
    session_corp_transfer_warp.add_argument("--units", required=True, type=int)
    session_corp_transfer_warp.add_argument("--to-ship-name", required=True)
    session_corp_transfer_warp.add_argument("--to-ship-id")
    session_corp_transfer_warp.add_argument("--wait-for-finish", action="store_true")
    session_corp_transfer_warp.add_argument(
        "--no-wait-for-finish",
        action="store_false",
        dest="wait_for_finish",
        help="Return after task start instead of waiting for task completion",
    )
    session_corp_transfer_warp.add_argument("--event-timeout-seconds", type=float, default=120.0)

    session_collect_unowned_ship = sub.add_parser(
        "session-collect-unowned-ship",
        help="Connect a session, send the exact website collect-unowned-ship prompt, and wait for the ship to appear in owned ships",
    )
    _add_session_connect_args(session_collect_unowned_ship)
    session_collect_unowned_ship.add_argument("--ship-id", required=True)
    session_collect_unowned_ship.add_argument("--sector-id", type=int)
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

    if args.command == "leaderboard-neighbors":
        async with HeadlessApiClient(config) as client:
            leaderboard_result = await client.leaderboard_resources(
                force_refresh=args.force_refresh,
            )

        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)

        print(
            dump_json(
                {
                    "connect": connect_result,
                    "neighbors": _leaderboard_neighbors(
                        config=config,
                        leaderboard_result=leaderboard_result,
                        status_result=status_result,
                        transport=args.transport,
                    ),
                }
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

    if args.command == "session-nearest-mega-port":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
            current_sector = _coerce_int(_extract_bridge_payload(status_result).get("sector", {}).get("id"))
            map_result = await bridge.get_my_map(
                center_sector=current_sector,
                max_hops=args.map_max_hops,
                max_sectors=args.map_max_sectors,
                timeout=args.event_timeout_seconds,
            )
            summary = _rank_nearest_mega_ports(
                status_result=status_result,
                map_result=map_result,
                limit=args.limit,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "summary": summary,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-trade-opportunities":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
            ports_result = await bridge.get_known_ports(timeout=args.event_timeout_seconds)
            map_result = await bridge.get_my_map(
                center_sector=_coerce_int(_extract_bridge_payload(status_result).get("sector", {}).get("id")),
                max_hops=args.map_max_hops,
                max_sectors=args.map_max_sectors,
                timeout=args.event_timeout_seconds,
            )
            summary = _rank_trade_opportunities(
                status_result=status_result,
                ports_result=ports_result,
                map_result=map_result,
                commodities=args.commodities,
                limit=args.limit,
            )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "summary": summary,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-auto-trade-loop":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_auto_trade_loop(
                bridge,
                goal=args.goal,
                commodities=args.commodities,
                limit=args.limit,
                map_max_hops=args.map_max_hops,
                map_max_sectors=args.map_max_sectors,
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
            center_sector = args.center_sector
            if center_sector is None:
                status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
                center_sector = _coerce_int(_extract_bridge_payload(status_result).get("sector", {}).get("id"))
                if center_sector <= 0:
                    raise HeadlessBridgeError(
                        "session-map",
                        "could not determine current sector for map center",
                    )
            action_result = await bridge.get_my_map(
                center_sector=center_sector,
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

    if args.command == "session-frontier-candidates":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            focus_ship = None
            origin_sector = args.center_sector or 0
            if args.ship_id or args.ship_name:
                ship_result = await _fetch_owned_ship_snapshot(
                    bridge,
                    ship_id=args.ship_id,
                    ship_name=args.ship_name,
                    timeout=args.event_timeout_seconds,
                )
                focus_ship = ship_result["ship"]
                if origin_sector <= 0:
                    origin_sector = _coerce_int(focus_ship.get("sector")) or _coerce_int(
                        focus_ship.get("sector_id")
                    )
            if origin_sector <= 0:
                status_result = await bridge.get_my_status(timeout=args.event_timeout_seconds)
                origin_sector = _coerce_int(_extract_bridge_payload(status_result).get("sector", {}).get("id"))
            if origin_sector <= 0:
                raise HeadlessBridgeError(
                    "session-frontier-candidates",
                    "could not determine a center sector",
                )
            map_result = await bridge.get_my_map(
                center_sector=origin_sector,
                max_hops=args.max_hops,
                max_sectors=args.max_sectors,
                timeout=args.event_timeout_seconds,
            )
            summary = _rank_frontier_candidates(
                origin_sector=origin_sector,
                map_result=map_result,
                focus_ship=focus_ship,
                limit=args.limit,
            )
            if args.validate_limit > 0:
                summary = await _validate_frontier_candidates(
                    bridge,
                    summary=summary,
                    validate_limit=args.validate_limit,
                    timeout=args.event_timeout_seconds,
                )
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "summary": summary,
                        "events": await bridge.drain_events(),
                    }
                )
            )
            return 0

    if args.command == "session-probe-frontier-loop":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_probe_frontier_loop(
                bridge,
                ship_id=args.ship_id,
                ship_name=args.ship_name,
                search_center_sector=args.search_center_sector,
                candidate_limit=args.candidate_limit,
                max_hops=args.max_hops,
                max_sectors=args.max_sectors,
                validate_limit=args.validate_limit,
                max_frontiers=args.max_frontiers,
                new_sectors_per_run=args.new_sectors_per_run,
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

    if args.command == "session-probe-fleet-loop":
        result = await _run_probe_fleet_loop(args, config)
        print(dump_json(result))
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

    if args.command == "session-move-to-sector":
        prompt = _move_to_sector_prompt_from_args(args)
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_move_to_sector(
                bridge,
                sector_id=args.sector_id,
                prompt=prompt,
                retries=args.step_retries,
                max_segments=args.max_segments,
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

    if args.command == "session-transfer-warp":
        prompt = _transfer_warp_prompt_from_args(args)
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

    if args.command == "session-shuttle-loop":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_shuttle_loop(
                bridge,
                home_sector=args.home_sector,
                away_sector=args.away_sector,
                home_commodity=args.home_commodity,
                away_commodity=args.away_commodity,
                max_cycles=args.max_cycles,
                target_credits=args.target_credits,
                min_warp=args.min_warp,
                step_retries=args.step_retries,
                finish_loaded_home=args.finish_loaded_home,
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

    if args.command == "session-liquidate-cargo":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_liquidate_cargo(
                bridge,
                commodity=args.commodity,
                goal=args.goal,
                retries=args.step_retries,
                max_segments=args.max_segments,
                map_max_hops=args.map_max_hops,
                map_max_sectors=args.map_max_sectors,
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

    if args.command == "session-load-cargo":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_load_cargo(
                bridge,
                commodity=args.commodity,
                quantity=args.quantity,
                wait_for_finish=args.wait_for_task_finish,
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

    if args.command == "session-wealth-loadout":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_wealth_loadout(
                bridge,
                wait_for_finish=args.wait_for_task_finish,
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
            start_result = None
            if args.start_session:
                start_result = await bridge.session_start(wait_seconds=args.start_wait_seconds)
            initial_corporation = await bridge.get_my_corporation(
                timeout=min(args.event_timeout_seconds, 15.0),
            )
            known_ship_ids = _corporation_ship_id_set(initial_corporation)
            purchases: list[dict[str, Any]] = []
            watch_result = None
            for purchase_index in range(args.count):
                action_result = await bridge.user_text_input(
                    prompt,
                    wait_seconds=args.wait_seconds,
                )
                purchase_result: dict[str, Any] = {
                    "purchase_index": purchase_index + 1,
                    "prompt": prompt,
                    "result": action_result,
                }
                if args.wait_for_task_finish:
                    watch_result = await _watch_corporation_ship_purchase(
                        bridge,
                        known_ship_ids=known_ship_ids,
                        timeout=args.event_timeout_seconds,
                    )
                    purchase_result["watch"] = watch_result
                    new_ship_ids = watch_result.get("new_ship_ids") or []
                    if new_ship_ids:
                        known_ship_ids.update(
                            ship_id for ship_id in new_ship_ids if isinstance(ship_id, str) and ship_id
                        )
                    if not watch_result.get("success"):
                        purchases.append(purchase_result)
                        break
                purchases.append(purchase_result)
            print(
                dump_json(
                    {
                        "connect": connect_result,
                        "start": start_result,
                        "initial_corporation": initial_corporation,
                        "purchases": purchases,
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

    if args.command == "session-corp-move-to-sector":
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            action_result = await _run_corporation_move_to_sector(
                bridge,
                ship_id=args.ship_id,
                ship_name=args.ship_name,
                sector_id=args.sector_id,
                max_segments=args.max_segments,
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

    if args.command == "session-corp-transfer-warp":
        prompt = _corporation_ship_transfer_warp_prompt_from_args(args)
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
                start_sector=args.start_sector,
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
        async with HeadlessBridgeProcess(config) as bridge:
            await bridge.set_log_level(args.bridge_log_level)
            connect_result = await _connect_session_bridge(bridge, args, config)
            initial_status = None
            current_sector_id = args.sector_id
            if current_sector_id is None:
                initial_status = await _fetch_status_snapshot_with_retries(
                    bridge,
                    timeout=min(args.event_timeout_seconds, 30.0),
                    context="session-collect-unowned-ship",
                )
                current_sector_id = _coerce_int(initial_status["summary"].get("sector_id"))
            prompt = _collect_unowned_ship_prompt_from_args(
                args,
                current_sector_id=current_sector_id,
            )
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
                        "initial_status": initial_status,
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


def _is_daily_connect_timeout_error(exc: HeadlessBridgeError) -> bool:
    message = getattr(exc, "message", "") or ""
    if "connect timed out after" not in message:
        return False
    payload = exc.payload
    if not isinstance(payload, dict):
        return False
    events = payload.get("events")
    if not isinstance(events, list):
        return False
    saw_connected = False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "connected":
            saw_connected = True
            continue
        if event.get("event") == "transport_state_changed" and event.get("state") == "connected":
            saw_connected = True
    return saw_connected


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
        if options.transport == "daily" and _is_daily_connect_timeout_error(exc):
            retried_options = SessionConnectOptions(
                access_token=options.access_token,
                functions_url=options.functions_url,
                transport=options.transport,
                character_id=options.character_id,
                session_id=options.session_id,
                connect_timeout_ms=max(options.connect_timeout_ms * 2, 40_000),
                request_timeout_ms=max(options.request_timeout_ms, options.connect_timeout_ms * 2),
                bypass_tutorial=options.bypass_tutorial,
                voice_id=options.voice_id,
                personality_tone=options.personality_tone,
                character_name=options.character_name,
            )
            return await bridge.connect(retried_options)
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


def _move_to_sector_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_move_to_sector_prompt(sector_id=args.sector_id)
    except ValueError as exc:
        raise HeadlessBridgeError("session-move-to-sector", str(exc)) from exc


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


def _transfer_warp_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        return build_transfer_warp_prompt(
            units=args.units,
            to_ship_name=args.to_ship_name,
            to_ship_id=args.to_ship_id,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-transfer-warp", str(exc)) from exc


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


def _corporation_ship_move_to_sector_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        task_description = build_corporation_ship_move_to_sector_task_description(
            sector_id=args.sector_id,
        )
        return build_corporation_ship_task_prompt(
            ship_name=args.ship_name,
            ship_id=args.ship_id,
            task_description=task_description,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-corp-move-to-sector", str(exc)) from exc


def _corporation_ship_transfer_warp_prompt_from_args(args: argparse.Namespace) -> str:
    try:
        task_description = build_corporation_ship_transfer_warp_task_description(
            units=args.units,
            to_ship_name=args.to_ship_name,
            to_ship_id=args.to_ship_id,
        )
        return build_corporation_ship_task_prompt(
            ship_name=args.ship_name,
            ship_id=args.ship_id,
            task_description=task_description,
        )
    except ValueError as exc:
        raise HeadlessBridgeError("session-corp-transfer-warp", str(exc)) from exc


def _collect_unowned_ship_prompt_from_args(
    args: argparse.Namespace,
    *,
    current_sector_id: int | None = None,
) -> str:
    try:
        sector_id = args.sector_id if args.sector_id is not None else current_sector_id
        if sector_id is None:
            raise ValueError("sector_id is required")
        return build_collect_unowned_ship_prompt(ship_id=args.ship_id, sector_id=sector_id)
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
        "port_stock": (
            sector.get("port", {}).get("stock")
            if isinstance(sector, dict) and isinstance(sector.get("port"), dict)
            and isinstance(sector.get("port", {}).get("stock"), dict)
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


def _extract_corporation_ships_from_bridge_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _extract_bridge_payload(result)
    corporation = payload.get("corporation")
    if not isinstance(corporation, dict):
        result_payload = payload.get("result")
        if isinstance(result_payload, dict):
            corporation = result_payload.get("corporation")
    if not isinstance(corporation, dict):
        return []
    ships = corporation.get("ships")
    if not isinstance(ships, list):
        return []
    return [ship for ship in ships if isinstance(ship, dict)]


def _corporation_ship_id_set(result: dict[str, Any]) -> set[str]:
    ship_ids: set[str] = set()
    for ship in _extract_corporation_ships_from_bridge_result(result):
        ship_id = ship.get("ship_id")
        if isinstance(ship_id, str) and ship_id:
            ship_ids.add(ship_id)
    return ship_ids


async def _watch_corporation_ship_purchase(
    bridge: HeadlessBridgeProcess,
    *,
    known_ship_ids: set[str],
    timeout: float,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError(
            "session-purchase-corp-ship",
            "--event-timeout-seconds must be > 0",
        )

    deadline = asyncio.get_running_loop().time() + timeout
    attempts = 0
    errors: list[str] = []
    last_result: dict[str, Any] | None = None

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        attempts += 1
        try:
            corporation_result = await bridge.get_my_corporation(timeout=min(remaining, 15.0))
        except HeadlessBridgeError as exc:
            errors.append(str(exc))
            await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))
            continue

        last_result = corporation_result
        ships = _extract_corporation_ships_from_bridge_result(corporation_result)
        new_ships = [
            ship
            for ship in ships
            if isinstance(ship.get("ship_id"), str) and ship.get("ship_id") not in known_ship_ids
        ]
        if new_ships:
            return {
                "success": True,
                "stop_reason": "fleet_grew",
                "attempts": attempts,
                "new_ships": new_ships,
                "new_ship_ids": [
                    ship.get("ship_id")
                    for ship in new_ships
                    if isinstance(ship.get("ship_id"), str) and ship.get("ship_id")
                ],
                "corporation": corporation_result.get("server_event"),
                "post_watch_errors": errors,
            }
        await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))

    return {
        "success": False,
        "stop_reason": "timeout",
        "attempts": attempts,
        "new_ships": [],
        "new_ship_ids": [],
        "corporation": None if last_result is None else last_result.get("server_event"),
        "post_watch_errors": errors,
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


async def _fetch_status_snapshot_with_retries(
    bridge: HeadlessBridgeProcess,
    *,
    timeout: float,
    context: str,
) -> dict[str, Any]:
    if timeout <= 0:
        raise HeadlessBridgeError(context, "--event-timeout-seconds must be > 0")

    deadline = asyncio.get_running_loop().time() + timeout
    errors: list[str] = []
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise HeadlessBridgeError(
                context,
                "timed out recovering status.snapshot",
                payload={"errors": errors},
            )
        try:
            return await _fetch_status_snapshot(bridge, timeout=min(remaining, 15.0))
        except HeadlessBridgeError as exc:
            errors.append(str(exc))
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 1.0:
                raise HeadlessBridgeError(
                    context,
                    "timed out recovering status.snapshot",
                    payload={"errors": errors},
                ) from exc
            await asyncio.sleep(min(2.0, max(0.25, remaining)))


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


async def _run_move_to_sector(
    bridge: HeadlessBridgeProcess,
    *,
    sector_id: int,
    prompt: str,
    retries: int,
    max_segments: int,
    timeout: float,
) -> dict[str, Any]:
    if sector_id <= 0:
        raise HeadlessBridgeError("session-move-to-sector", "--sector-id must be > 0")
    if retries < 0:
        raise HeadlessBridgeError("session-move-to-sector", "--step-retries must be >= 0")
    if max_segments <= 0:
        raise HeadlessBridgeError("session-move-to-sector", "--max-segments must be > 0")

    initial_status = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
    initial_summary = initial_status["summary"]
    if initial_summary.get("sector_id") == sector_id:
        return {
            "prompt": prompt,
            "already_there": True,
            "initial_status": initial_status,
            "result": None,
            "final_status": initial_status,
        }

    current_status = initial_status
    current_summary = initial_summary
    segments: list[dict[str, Any]] = []
    stop_reason = "max_segments_reached"

    for _ in range(max_segments):
        if current_summary.get("sector_id") == sector_id:
            stop_reason = "arrived"
            break

        start_summary = current_summary
        step_result = await _run_validated_player_step(
            bridge,
            prompt=prompt,
            timeout=timeout,
            retries=retries,
            validate=lambda summary: summary.get("sector_id") == sector_id,
        )
        final_attempt = step_result.get("result")
        final_status = final_attempt.get("status") if isinstance(final_attempt, dict) else None
        final_summary = final_status.get("summary") if isinstance(final_status, dict) else {}

        progress_observed = final_summary.get("sector_id") != start_summary.get("sector_id")
        segment = {
            "step": step_result,
            "start_sector": start_summary.get("sector_id"),
            "end_sector": final_summary.get("sector_id"),
            "start_warp": start_summary.get("warp_power"),
            "end_warp": final_summary.get("warp_power"),
            "progress_observed": progress_observed,
            "task_completion_inferred": bool(progress_observed and not step_result.get("success")),
        }
        segments.append(segment)
        if isinstance(final_status, dict):
            current_status = final_status
            current_summary = final_summary

        if current_summary.get("sector_id") == sector_id:
            stop_reason = "arrived"
            break
        if not progress_observed:
            stop_reason = "no_progress"
            break

    return {
        "prompt": prompt,
        "already_there": False,
        "initial_status": initial_status,
        "segments": segments,
        "stop_reason": stop_reason,
        "final_status": current_status,
    }


def _select_wealth_loadout(summary: dict[str, Any]) -> dict[str, Any]:
    port_code = summary.get("port_code")
    empty_holds = _coerce_int(summary.get("empty_holds"))
    ship_credits = _coerce_int(summary.get("ship_credits"))
    if empty_holds <= 0:
        raise HeadlessBridgeError("session-wealth-loadout", "no empty holds available")
    if ship_credits <= 0:
        raise HeadlessBridgeError("session-wealth-loadout", "no ship credits available")

    choices: list[dict[str, Any]] = []
    for commodity in RESOURCE_PORT_CODE_ORDER:
        if not _port_allows_buy(port_code, commodity):
            continue
        price = _port_price(summary, commodity)
        if price is None or price <= 0:
            continue
        quantity = min(empty_holds, ship_credits // price)
        if quantity <= 0:
            continue
        choices.append(
            {
                "commodity": commodity,
                "price_per_unit": price,
                "quantity": quantity,
                "estimated_wealth_delta": quantity * max(0, 100 - price),
            }
        )

    if not choices:
        raise HeadlessBridgeError(
            "session-wealth-loadout",
            "current sector does not sell any affordable commodities",
            payload={"summary": summary},
        )

    choices.sort(
        key=lambda item: (
            item["price_per_unit"],
            -item["estimated_wealth_delta"],
            item["commodity"],
        )
    )
    return choices[0]


def _select_explicit_loadout(
    summary: dict[str, Any],
    *,
    commodity: str,
    quantity: int | None,
) -> dict[str, Any]:
    port_code = summary.get("port_code")
    if not _port_allows_buy(port_code, commodity):
        raise HeadlessBridgeError(
            "session-load-cargo",
            f"current port does not sell {commodity}",
            payload={"summary": summary},
        )

    empty_holds = _coerce_int(summary.get("empty_holds"))
    ship_credits = _coerce_int(summary.get("ship_credits"))
    if empty_holds <= 0:
        raise HeadlessBridgeError("session-load-cargo", "no empty holds available")
    if ship_credits <= 0:
        raise HeadlessBridgeError("session-load-cargo", "no ship credits available")

    price = _port_price(summary, commodity)
    if price is None or price <= 0:
        raise HeadlessBridgeError(
            "session-load-cargo",
            f"no current port price for {commodity}",
            payload={"summary": summary},
        )

    max_quantity = min(empty_holds, ship_credits // price)
    stock = _port_stock(summary, commodity)
    if stock is not None and stock >= 0:
        max_quantity = min(max_quantity, stock)
    if max_quantity <= 0:
        raise HeadlessBridgeError(
            "session-load-cargo",
            f"cannot afford any {commodity} at the current port",
            payload={"summary": summary},
        )

    selected_quantity = max_quantity if quantity is None else quantity
    if selected_quantity <= 0:
        raise HeadlessBridgeError("session-load-cargo", "--quantity must be > 0")
    if selected_quantity > max_quantity:
        raise HeadlessBridgeError(
            "session-load-cargo",
            f"requested quantity exceeds current capacity/credits/stock for {commodity}",
            payload={
                "commodity": commodity,
                "requested_quantity": selected_quantity,
                "max_quantity": max_quantity,
                "price_per_unit": price,
                "stock_available": stock,
            },
        )

    return {
        "commodity": commodity,
        "price_per_unit": price,
        "quantity": selected_quantity,
        "max_quantity": max_quantity,
        "stock_available": stock,
    }


def _select_loaded_commodity(summary: dict[str, Any], preferred: str | None) -> dict[str, Any]:
    cargo = summary.get("cargo")
    if not isinstance(cargo, dict):
        raise HeadlessBridgeError("session-liquidate-cargo", "ship cargo is unavailable")

    if preferred is not None:
        units = _cargo_units(summary, preferred)
        if units <= 0:
            raise HeadlessBridgeError(
                "session-liquidate-cargo",
                f"ship is not carrying any {preferred}",
                payload={"summary": summary},
            )
        return {
            "commodity": preferred,
            "quantity": units,
        }

    loaded = [
        {
            "commodity": commodity,
            "quantity": _cargo_units(summary, commodity),
        }
        for commodity in RESOURCE_PORT_CODE_ORDER
        if _cargo_units(summary, commodity) > 0
    ]
    if not loaded:
        raise HeadlessBridgeError("session-liquidate-cargo", "ship is not carrying any cargo")
    if len(loaded) > 1:
        raise HeadlessBridgeError(
            "session-liquidate-cargo",
            "ship is carrying multiple commodities; pass --commodity to choose one",
            payload={"loaded": loaded, "summary": summary},
        )
    return loaded[0]


def _rank_cargo_sale_opportunities(
    *,
    status_result: dict[str, Any],
    ports_result: dict[str, Any],
    map_result: dict[str, Any] | None,
    commodity: str,
    quantity: int,
) -> dict[str, Any]:
    if quantity <= 0:
        raise HeadlessBridgeError("session-liquidate-cargo", "quantity must be > 0")

    status_payload = _extract_bridge_payload(status_result)
    ports_payload = _extract_bridge_payload(ports_result)
    map_payload = _extract_bridge_payload(map_result or {})

    sector = status_payload.get("sector") if isinstance(status_payload, dict) else None
    ports = ports_payload.get("ports") if isinstance(ports_payload, dict) else None
    graph = _map_graph_from_payload(map_payload)
    current_sector = _coerce_int(sector.get("id")) if isinstance(sector, dict) else 0
    distances_from_current = _shortest_path_lengths(graph, start=current_sector) if current_sector > 0 else {}

    rows: list[dict[str, Any]] = []
    if isinstance(ports, list):
        for port in ports:
            if not isinstance(port, dict):
                continue
            port_sector = port.get("sector")
            if not isinstance(port_sector, dict):
                continue
            port_info = port_sector.get("port")
            if not isinstance(port_info, dict):
                continue
            port_code = port_info.get("code")
            if not _port_allows_sell(str(port_code), commodity):
                continue
            prices = port_info.get("prices")
            if not isinstance(prices, dict):
                continue
            sell_price = _coerce_int(prices.get(commodity))
            if sell_price <= 0:
                continue
            sector_id = _coerce_int(port_sector.get("id"))
            if sector_id <= 0:
                continue
            distance = distances_from_current.get(sector_id, _coerce_int(port.get("hops_from_start")))
            sale_value = sell_price * quantity
            rows.append(
                {
                    "commodity": commodity,
                    "quantity": quantity,
                    "sell_sector": sector_id,
                    "sell_port_code": port_code,
                    "sell_price": sell_price,
                    "expected_sale_value": sale_value,
                    "distance_to_sell": distance,
                    "sale_value_per_hop": round(sale_value / max(distance, 1), 2),
                }
            )

    rows.sort(
        key=lambda row: (
            row["sale_value_per_hop"],
            row["sell_price"],
            -row["distance_to_sell"],
        ),
        reverse=True,
    )
    return {
        "current_sector": current_sector or None,
        "commodity": commodity,
        "quantity": quantity,
        "nearest": min(rows, key=lambda row: (row["distance_to_sell"], -row["sell_price"]), default=None),
        "best_by_price": max(rows, key=lambda row: row["sell_price"], default=None),
        "best_by_price_per_hop": max(rows, key=lambda row: row["sale_value_per_hop"], default=None),
        "opportunities": rows,
    }


def _select_cargo_sale_opportunity(summary: dict[str, Any], goal: str) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    if goal == "nearest":
        selected = summary.get("nearest")
    elif goal == "best-price":
        selected = summary.get("best_by_price")
    else:
        selected = summary.get("best_by_price_per_hop")
    return selected if isinstance(selected, dict) else None


async def _run_wealth_loadout(
    bridge: HeadlessBridgeProcess,
    *,
    wait_for_finish: bool,
    timeout: float,
) -> dict[str, Any]:
    initial_status = await _fetch_status_snapshot_with_retries(
        bridge,
        timeout=min(timeout, 30.0),
        context="session-wealth-loadout",
    )
    initial_summary = initial_status["summary"]
    selection = _select_wealth_loadout(initial_summary)
    prompt = build_trade_order_prompt(
        trade_type="BUY",
        quantity=selection["quantity"],
        commodity=selection["commodity"],
        price_per_unit=selection["price_per_unit"],
    )
    action_result = await bridge.user_text_input(prompt, wait_seconds=0.0)
    watch_result = None
    final_status = initial_status
    if wait_for_finish:
        watch_result = await _watch_player_task(
            bridge,
            wait_for_finish=True,
            timeout=timeout,
        )
        final_status = await _fetch_status_snapshot_with_retries(
            bridge,
            timeout=min(timeout, 30.0),
            context="session-wealth-loadout",
        )
    return {
        "selection": selection,
        "prompt": prompt,
        "initial_status": initial_status,
        "result": action_result,
        "watch": watch_result,
        "final_status": final_status,
    }


async def _run_load_cargo(
    bridge: HeadlessBridgeProcess,
    *,
    commodity: str,
    quantity: int | None,
    wait_for_finish: bool,
    timeout: float,
) -> dict[str, Any]:
    initial_status = await _fetch_status_snapshot_with_retries(
        bridge,
        timeout=min(timeout, 30.0),
        context="session-load-cargo",
    )
    initial_summary = initial_status["summary"]
    selection = _select_explicit_loadout(
        initial_summary,
        commodity=commodity,
        quantity=quantity,
    )
    prompt = build_trade_order_prompt(
        trade_type="BUY",
        quantity=selection["quantity"],
        commodity=selection["commodity"],
        price_per_unit=selection["price_per_unit"],
    )
    action_result = await bridge.user_text_input(prompt, wait_seconds=0.0)
    watch_result = None
    final_status = initial_status
    if wait_for_finish:
        watch_result = await _watch_player_task(
            bridge,
            wait_for_finish=True,
            timeout=timeout,
        )
        final_status = await _fetch_status_snapshot_with_retries(
            bridge,
            timeout=min(timeout, 30.0),
            context="session-load-cargo",
        )
    return {
        "selection": selection,
        "prompt": prompt,
        "initial_status": initial_status,
        "result": action_result,
        "watch": watch_result,
        "final_status": final_status,
    }


async def _run_liquidate_cargo(
    bridge: HeadlessBridgeProcess,
    *,
    commodity: str | None,
    goal: str,
    retries: int,
    max_segments: int,
    map_max_hops: int,
    map_max_sectors: int,
    timeout: float,
) -> dict[str, Any]:
    initial_status = await _fetch_status_snapshot_with_retries(
        bridge,
        timeout=min(timeout, 30.0),
        context="session-liquidate-cargo",
    )
    initial_summary = initial_status["summary"]
    loaded = _select_loaded_commodity(initial_summary, commodity)
    loaded_commodity = loaded["commodity"]
    loaded_quantity = loaded["quantity"]

    current_sector = _coerce_int(initial_summary.get("sector_id"))
    current_price = _port_price(initial_summary, loaded_commodity)
    selected: dict[str, Any] | None = None
    opportunities: dict[str, Any] | None = None
    if (
        current_sector > 0
        and _port_allows_sell(str(initial_summary.get("port_code")), loaded_commodity)
        and isinstance(current_price, int)
        and current_price > 0
    ):
        selected = {
            "commodity": loaded_commodity,
            "quantity": loaded_quantity,
            "sell_sector": current_sector,
            "sell_port_code": initial_summary.get("port_code"),
            "sell_price": current_price,
            "expected_sale_value": current_price * loaded_quantity,
            "distance_to_sell": 0,
            "sale_value_per_hop": current_price * loaded_quantity,
        }
    else:
        ports_result = await bridge.get_known_ports(timeout=timeout)
        map_result = await bridge.get_my_map(
            center_sector=current_sector,
            max_hops=map_max_hops,
            max_sectors=map_max_sectors,
            timeout=timeout,
        )
        opportunities = _rank_cargo_sale_opportunities(
            status_result=initial_status,
            ports_result=ports_result,
            map_result=map_result,
            commodity=loaded_commodity,
            quantity=loaded_quantity,
        )
        selected = _select_cargo_sale_opportunity(opportunities, goal)
        if not isinstance(selected, dict):
            raise HeadlessBridgeError(
                "session-liquidate-cargo",
                f"no reachable legal buyer for {loaded_commodity}",
                payload=opportunities,
            )

    move_result = None
    current_status = initial_status
    current_summary = initial_summary
    sell_sector = _coerce_int(selected.get("sell_sector"))
    if sell_sector > 0 and current_summary.get("sector_id") != sell_sector:
        move_result = await _run_move_to_sector(
            bridge,
            sector_id=sell_sector,
            prompt=build_move_to_sector_prompt(sector_id=sell_sector),
            retries=retries,
            max_segments=max_segments,
            timeout=timeout,
        )
        current_status = move_result.get("final_status", current_status)
        current_summary = current_status.get("summary", current_summary) if isinstance(current_status, dict) else current_summary
        if current_summary.get("sector_id") != sell_sector:
            return {
                "commodity": loaded_commodity,
                "quantity": loaded_quantity,
                "goal": goal,
                "selected_route": selected,
                "opportunities": opportunities,
                "initial_status": initial_status,
                "move": move_result,
                "stop_reason": "move_failed",
                "final_status": current_status,
            }

    current_quantity = _cargo_units(current_summary, loaded_commodity)
    if current_quantity <= 0:
        return {
            "commodity": loaded_commodity,
            "quantity": loaded_quantity,
            "goal": goal,
            "selected_route": selected,
            "opportunities": opportunities,
            "initial_status": initial_status,
            "move": move_result,
            "stop_reason": "already_liquidated",
            "final_status": current_status,
        }

    recovery_result = await _recover_with_trade_order(
        bridge,
        summary=current_summary,
        commodity=loaded_commodity,
        timeout=timeout,
    )
    final_status = recovery_result.get("status", current_status)
    final_summary = final_status.get("summary", current_summary) if isinstance(final_status, dict) else current_summary
    stop_reason = "liquidated" if recovery_result.get("success") else "sell_failed"
    return {
        "commodity": loaded_commodity,
        "quantity": loaded_quantity,
        "goal": goal,
        "selected_route": selected,
        "opportunities": opportunities,
        "initial_status": initial_status,
        "move": move_result,
        "sell": recovery_result,
        "stop_reason": stop_reason,
        "final_status": final_status,
        "final_summary": final_summary,
    }


async def _run_corporation_move_to_sector(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str,
    sector_id: int,
    max_segments: int,
    timeout: float,
) -> dict[str, Any]:
    if sector_id <= 0:
        raise HeadlessBridgeError("session-corp-move-to-sector", "--sector-id must be > 0")
    if max_segments <= 0:
        raise HeadlessBridgeError("session-corp-move-to-sector", "--max-segments must be > 0")

    prompt = build_corporation_ship_task_prompt(
        ship_name=ship_name,
        ship_id=ship_id,
        task_description=build_corporation_ship_move_to_sector_task_description(sector_id=sector_id),
    )
    initial_ship_snapshot = await _fetch_owned_ship_snapshot(
        bridge,
        ship_id=ship_id,
        ship_name=ship_name,
        timeout=min(timeout, 30.0),
    )
    current_ship = initial_ship_snapshot["ship"]
    segments: list[dict[str, Any]] = []

    if current_ship.get("sector") == sector_id:
        return {
            "prompt": prompt,
            "target_sector": sector_id,
            "stop_reason": "already_there",
            "initial_ship": initial_ship_snapshot,
            "segments": segments,
            "final_ship": current_ship,
        }

    stop_reason = "max_segments_reached"
    for _ in range(max_segments):
        start_ship = current_ship
        action_result = await bridge.user_text_input(prompt, wait_seconds=0.0)
        watch_result = await _watch_corporation_task(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            wait_for_finish=True,
            timeout=timeout,
        )
        post_ship_snapshot = await _fetch_owned_ship_snapshot(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            timeout=min(timeout, 30.0),
        )
        post_ship = post_ship_snapshot["ship"]
        ship_polls: list[dict[str, Any]] = []
        poll_deadline = asyncio.get_running_loop().time() + min(timeout, 30.0)

        while (
            post_ship.get("current_task_id")
            and post_ship.get("sector") != sector_id
            and post_ship.get("destroyed_at") is None
        ):
            remaining = poll_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(2.0, remaining))
            next_snapshot = await _fetch_owned_ship_snapshot(
                bridge,
                ship_id=ship_id,
                ship_name=ship_name,
                timeout=min(remaining, 15.0),
            )
            ship_polls.append(next_snapshot)
            post_ship_snapshot = next_snapshot
            post_ship = next_snapshot["ship"]

        progress_observed = post_ship.get("sector") != start_ship.get("sector")
        segment = {
            "prompt": prompt,
            "result": action_result,
            "watch": watch_result,
            "ship": post_ship_snapshot,
            "ship_polls": ship_polls,
            "start_sector": start_ship.get("sector"),
            "end_sector": post_ship.get("sector"),
            "start_warp": start_ship.get("warp_power"),
            "end_warp": post_ship.get("warp_power"),
            "progress_observed": progress_observed,
            "task_completion_inferred": bool(progress_observed and not watch_result.get("task_finished")),
        }
        segments.append(segment)
        current_ship = post_ship

        if current_ship.get("sector") == sector_id:
            stop_reason = "arrived"
            break
        if current_ship.get("destroyed_at") is not None:
            stop_reason = "ship_destroyed"
            break
        if not progress_observed:
            stop_reason = watch_result.get("stop_reason") or "no_progress"
            break

    return {
        "prompt": prompt,
        "target_sector": sector_id,
        "stop_reason": stop_reason,
        "initial_ship": initial_ship_snapshot,
        "segments": segments,
        "final_ship": current_ship,
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
        status_result = await _fetch_status_snapshot_with_retries(
            bridge,
            timeout=min(timeout, 30.0),
            context="session-move-to-sector",
        )
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
            status_result = await _fetch_status_snapshot_with_retries(
                bridge,
                timeout=min(remaining, 30.0),
                context="session-move-to-sector",
            )
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


def _port_trade_marker(port_code: str | None, commodity: str) -> str | None:
    if commodity not in RESOURCE_PORT_CODE_ORDER:
        return None
    normalized_code = (port_code or "").strip().upper()
    index = RESOURCE_PORT_CODE_ORDER.index(commodity)
    if index >= len(normalized_code):
        return None
    marker = normalized_code[index]
    return marker if marker in {"B", "S"} else None


def _port_allows_buy(port_code: str | None, commodity: str) -> bool:
    return _port_trade_marker(port_code, commodity) == "S"


def _port_allows_sell(port_code: str | None, commodity: str) -> bool:
    return _port_trade_marker(port_code, commodity) == "B"


def _map_graph_from_payload(payload: dict[str, Any]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = {}
    if not isinstance(payload, dict):
        return graph
    sectors = payload.get("sectors")
    if not isinstance(sectors, list):
        return graph
    for sector in sectors:
        if not isinstance(sector, dict):
            continue
        sector_id = _coerce_int(sector.get("id"))
        if sector_id <= 0:
            continue
        graph.setdefault(sector_id, set())
        lanes = sector.get("lanes")
        if not isinstance(lanes, list):
            continue
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            neighbor = _coerce_int(lane.get("to"))
            if neighbor <= 0:
                continue
            graph.setdefault(sector_id, set()).add(neighbor)
            if lane.get("two_way") is not False:
                graph.setdefault(neighbor, set()).add(sector_id)
    return graph


def _shortest_path_lengths(graph: dict[int, set[int]], *, start: int) -> dict[int, int]:
    if start <= 0 or start not in graph:
        return {}
    distances: dict[int, int] = {start: 0}
    queue: deque[int] = deque([start])
    while queue:
        sector = queue.popleft()
        base_distance = distances[sector]
        for neighbor in graph.get(sector, set()):
            if neighbor in distances:
                continue
            distances[neighbor] = base_distance + 1
            queue.append(neighbor)
    return distances


def _shortest_path(graph: dict[int, set[int]], *, start: int, target: int) -> list[int]:
    if start <= 0 or target <= 0 or start not in graph or target not in graph:
        return []
    prev: dict[int, int | None] = {start: None}
    queue: deque[int] = deque([start])
    while queue:
        sector = queue.popleft()
        if sector == target:
            break
        for neighbor in graph.get(sector, set()):
            if neighbor in prev:
                continue
            prev[neighbor] = sector
            queue.append(neighbor)
    if target not in prev:
        return []
    path: list[int] = []
    current: int | None = target
    while current is not None:
        path.append(current)
        current = prev[current]
    path.reverse()
    return path


def _rank_nearest_mega_ports(
    *,
    status_result: dict[str, Any],
    map_result: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    if limit <= 0:
        raise HeadlessBridgeError("session-nearest-mega-port", "--limit must be > 0")

    status_payload = _extract_bridge_payload(status_result)
    map_payload = _extract_bridge_payload(map_result)
    current_sector = _coerce_int(status_payload.get("sector", {}).get("id"))
    sectors = map_payload.get("sectors") if isinstance(map_payload, dict) else None
    graph = _map_graph_from_payload(map_payload)

    rows: list[dict[str, Any]] = []
    if not isinstance(sectors, list):
        return {
            "current_sector": current_sector or None,
            "nearest": [],
        }

    for sector in sectors:
        if not isinstance(sector, dict):
            continue
        port = sector.get("port")
        if not isinstance(port, dict) or not port.get("mega"):
            continue
        sector_id = _coerce_int(sector.get("id"))
        if sector_id <= 0:
            continue
        path = _shortest_path(graph, start=current_sector, target=sector_id)
        if not path:
            continue
        rows.append(
            {
                "sector_id": sector_id,
                "distance": len(path) - 1,
                "path": path,
                "port_code": port.get("code"),
                "position": sector.get("position"),
                "region": sector.get("region"),
            }
        )

    rows.sort(key=lambda row: (row["distance"], row["sector_id"]))
    return {
        "current_sector": current_sector or None,
        "nearest": rows[:limit],
    }


def _map_neighbor_ids(sector: dict[str, Any]) -> set[int]:
    neighbor_ids: set[int] = set()
    lanes = sector.get("lanes")
    if isinstance(lanes, list):
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            neighbor = _coerce_int(lane.get("to"))
            if neighbor > 0:
                neighbor_ids.add(neighbor)
    adjacent_sectors = sector.get("adjacent_sectors")
    if isinstance(adjacent_sectors, dict):
        for sector_id in adjacent_sectors.keys():
            neighbor = _coerce_int(sector_id)
            if neighbor > 0:
                neighbor_ids.add(neighbor)
    return neighbor_ids


def _two_hop_unvisited_count(
    *,
    sector_id: int,
    sectors_by_id: dict[int, dict[str, Any]],
    graph: dict[int, set[int]],
) -> int:
    if sector_id <= 0:
        return 0
    seen: set[int] = {sector_id}
    queue: deque[tuple[int, int]] = deque([(sector_id, 0)])
    unvisited: set[int] = set()
    while queue:
        current_sector, depth = queue.popleft()
        if depth >= 2:
            continue
        for neighbor in graph.get(current_sector, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            neighbor_sector = sectors_by_id.get(neighbor)
            if isinstance(neighbor_sector, dict) and neighbor_sector.get("visited") is not True:
                unvisited.add(neighbor)
            queue.append((neighbor, depth + 1))
    return len(unvisited)


def _rank_frontier_candidates(
    *,
    origin_sector: int,
    map_result: dict[str, Any],
    focus_ship: dict[str, Any] | None,
    limit: int,
) -> dict[str, Any]:
    if limit <= 0:
        raise HeadlessBridgeError("session-frontier-candidates", "--limit must be > 0")

    map_payload = _extract_bridge_payload(map_result)
    sectors = map_payload.get("sectors") if isinstance(map_payload, dict) else None
    if not isinstance(sectors, list):
        return {
            "origin_sector": origin_sector or None,
            "focus_ship": None,
            "map_sector_count": 0,
            "visited_sector_count": 0,
            "unvisited_sector_count": 0,
            "frontier_sector_count": 0,
            "recommended": None,
            "candidates": [],
        }

    sectors_by_id: dict[int, dict[str, Any]] = {}
    for sector in sectors:
        if not isinstance(sector, dict):
            continue
        sector_id = _coerce_int(sector.get("id"))
        if sector_id > 0:
            sectors_by_id[sector_id] = sector

    graph = _map_graph_from_payload(map_payload)
    distances = _shortest_path_lengths(graph, start=origin_sector)
    rows: list[dict[str, Any]] = []

    for sector_id, sector in sectors_by_id.items():
        distance = distances.get(sector_id)
        if distance is None:
            continue
        visited = sector.get("visited") is True
        neighbor_ids = _map_neighbor_ids(sector)
        known_neighbor_ids = sorted(neighbor for neighbor in neighbor_ids if neighbor in sectors_by_id)
        visited_neighbor_ids = [
            neighbor
            for neighbor in known_neighbor_ids
            if sectors_by_id.get(neighbor, {}).get("visited") is True
        ]
        unvisited_neighbor_ids = [
            neighbor
            for neighbor in known_neighbor_ids
            if sectors_by_id.get(neighbor, {}).get("visited") is not True
        ]
        stub_neighbor_ids = sorted(neighbor for neighbor in neighbor_ids if neighbor not in sectors_by_id)
        two_hop_unvisited = _two_hop_unvisited_count(
            sector_id=sector_id,
            sectors_by_id=sectors_by_id,
            graph=graph,
        )
        immediate_discovery = 0 if visited else 1
        frontier_neighbors = len(unvisited_neighbor_ids) + len(stub_neighbor_ids)
        frontier_score = immediate_discovery * 20 + frontier_neighbors * 8 + two_hop_unvisited * 2 - distance
        if immediate_discovery == 0 and frontier_neighbors == 0 and two_hop_unvisited == 0:
            continue
        rows.append(
            {
                "sector_id": sector_id,
                "visited": visited,
                "candidate_type": "unvisited_target" if immediate_discovery else "visited_anchor",
                "distance": distance,
                "path": _shortest_path(graph, start=origin_sector, target=sector_id),
                "frontier_score": frontier_score,
                "immediate_discovery": immediate_discovery,
                "frontier_neighbors": frontier_neighbors,
                "unvisited_neighbor_count": len(unvisited_neighbor_ids),
                "stub_neighbor_count": len(stub_neighbor_ids),
                "two_hop_unvisited": two_hop_unvisited,
                "visited_neighbor_count": len(visited_neighbor_ids),
                "neighbor_count": len(neighbor_ids),
                "unvisited_neighbors": unvisited_neighbor_ids[:8],
                "stub_neighbors": stub_neighbor_ids[:8],
                "port_code": (
                    sector.get("port", {}).get("code")
                    if isinstance(sector.get("port"), dict)
                    else None
                ),
                "region": sector.get("region"),
                "source": sector.get("source"),
                "hops_from_center": _coerce_int(sector.get("hops_from_center")) or None,
            }
        )

    rows.sort(
        key=lambda row: (
            -row["frontier_score"],
            -row["immediate_discovery"],
            -row["frontier_neighbors"],
            -row["two_hop_unvisited"],
            row["distance"],
            row["sector_id"],
        )
    )

    visited_sector_count = sum(1 for sector in sectors_by_id.values() if sector.get("visited") is True)
    unvisited_sector_count = sum(1 for sector in sectors_by_id.values() if sector.get("visited") is not True)
    focus_ship_summary = None
    if isinstance(focus_ship, dict):
        focus_ship_summary = {
            "ship_id": focus_ship.get("ship_id"),
            "ship_name": focus_ship.get("ship_name") or focus_ship.get("name"),
            "sector": _coerce_int(focus_ship.get("sector")) or _coerce_int(focus_ship.get("sector_id")) or None,
            "warp_power": _coerce_int(focus_ship.get("warp_power")) or None,
            "ship_type": focus_ship.get("ship_type"),
        }

    return {
        "origin_sector": origin_sector or None,
        "focus_ship": focus_ship_summary,
        "map_sector_count": len(sectors_by_id),
        "visited_sector_count": visited_sector_count,
        "unvisited_sector_count": unvisited_sector_count,
        "frontier_sector_count": len(rows),
        "recommended": rows[0] if rows else None,
        "candidates": rows[:limit],
    }


def _frontier_candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    score = row.get("validated_frontier_score", row.get("frontier_score", 0))
    return (
        -int(score) if isinstance(score, int) else 0,
        -_coerce_int(row.get("immediate_discovery")),
        -_coerce_int(row.get("frontier_neighbors")),
        -_coerce_int(row.get("two_hop_unvisited")),
        _coerce_int(row.get("distance")),
        _coerce_int(row.get("sector_id")),
    )


async def _validate_frontier_candidates(
    bridge: HeadlessBridgeProcess,
    *,
    summary: dict[str, Any],
    validate_limit: int,
    timeout: float,
) -> dict[str, Any]:
    if validate_limit <= 0:
        return summary
    candidates = summary.get("candidates")
    if not isinstance(candidates, list):
        return summary

    validated_candidates = 0
    validated_stub_sectors = 0
    for candidate in candidates:
        if validated_candidates >= validate_limit:
            break
        if not isinstance(candidate, dict):
            continue
        stub_neighbors = candidate.get("stub_neighbors")
        if not isinstance(stub_neighbors, list) or not stub_neighbors:
            continue

        validations: list[dict[str, Any]] = []
        for sector_id in stub_neighbors:
            neighbor = _coerce_int(sector_id)
            if neighbor <= 0:
                continue
            validated_stub_sectors += 1
            try:
                probe_result = await bridge.get_my_map(
                    center_sector=neighbor,
                    max_hops=1,
                    max_sectors=20,
                    timeout=min(timeout, 15.0),
                )
            except HeadlessBridgeError as exc:
                message = exc.message or str(exc)
                if "Center sector" in message and "visited" in message:
                    validations.append(
                        {
                            "sector_id": neighbor,
                            "status": "unvisited",
                        }
                    )
                else:
                    validations.append(
                        {
                            "sector_id": neighbor,
                            "status": "error",
                            "error": message,
                        }
                    )
            else:
                payload = _extract_bridge_payload(probe_result)
                sectors = payload.get("sectors") if isinstance(payload, dict) else None
                validations.append(
                    {
                        "sector_id": neighbor,
                        "status": "centerable",
                        "sector_count": len(sectors) if isinstance(sectors, list) else None,
                    }
                )

        validated_candidates += 1
        candidate["validated_stub_neighbors"] = validations
        validated_unvisited = sum(1 for item in validations if item.get("status") == "unvisited")
        validated_centerable = sum(1 for item in validations if item.get("status") == "centerable")
        candidate["validated_unvisited_stub_count"] = validated_unvisited
        candidate["validated_centerable_stub_count"] = validated_centerable
        candidate["validated_frontier_score"] = (
            _coerce_int(candidate.get("frontier_score"))
            + validated_unvisited * 25
            - validated_centerable * 15
        )

    candidates.sort(key=_frontier_candidate_sort_key)
    summary["recommended"] = candidates[0] if candidates else None
    summary["validation"] = {
        "validated_candidate_count": validated_candidates,
        "validated_stub_sector_count": validated_stub_sectors,
        "method": "probe stub sectors with local_map_region; a center-sector error implies the stub is not yet visited",
    }
    return summary


def _actionable_frontier_candidates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = summary.get("candidates")
    if not isinstance(candidates, list):
        return []
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if (
            _coerce_int(candidate.get("validated_unvisited_stub_count")) <= 0
            and _coerce_int(candidate.get("unvisited_neighbor_count")) <= 0
            and _coerce_int(candidate.get("immediate_discovery")) <= 0
        ):
            continue
        rows.append(candidate)
    return rows


def _probe_ship_summary(ship: dict[str, Any]) -> dict[str, Any]:
    return {
        "ship_id": ship.get("ship_id"),
        "ship_name": ship.get("ship_name"),
        "ship_type": ship.get("ship_type"),
        "owner_type": ship.get("owner_type"),
        "sector": _coerce_int(ship.get("sector")),
        "warp_power": _coerce_int(ship.get("warp_power")),
        "current_task_id": ship.get("current_task_id"),
        "destroyed_at": ship.get("destroyed_at"),
    }


def _ship_matches_probe_filters(
    ship: dict[str, Any],
    *,
    ship_ids: list[str],
    ship_names: list[str],
) -> bool:
    if not ship_ids and not ship_names:
        return True
    for ship_id in ship_ids:
        if ship_id and _matches_identifier(ship.get("ship_id"), ship_id):
            return True
    for ship_name in ship_names:
        if ship_name and _normalize_compare_text(ship.get("ship_name")) == _normalize_compare_text(ship_name):
            return True
    return False


def _classify_probe_fleet(
    ships_result: dict[str, Any],
    *,
    ship_ids: list[str],
    ship_names: list[str],
    min_probe_warp: int,
) -> dict[str, Any]:
    payload = _extract_bridge_payload(ships_result)
    ships = payload.get("ships")
    if not isinstance(ships, list):
        return {
            "eligible_probes": [],
            "skipped": [],
        }

    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw_ship in ships:
        if not isinstance(raw_ship, dict):
            continue
        ship = _probe_ship_summary(raw_ship)
        reason = None
        if ship.get("destroyed_at") is not None:
            reason = "destroyed"
        elif ship.get("owner_type") != "corporation":
            reason = "not_corporation_owned"
        elif ship.get("ship_type") != "autonomous_probe":
            reason = "not_probe"
        elif not _ship_matches_probe_filters(raw_ship, ship_ids=ship_ids, ship_names=ship_names):
            reason = "filtered_out"
        elif ship.get("current_task_id"):
            reason = "busy"
        elif _coerce_int(ship.get("warp_power")) < min_probe_warp:
            reason = "insufficient_warp"

        if reason is None:
            eligible.append(ship)
        else:
            skipped.append({**ship, "reason": reason})

    eligible.sort(
        key=lambda ship: (
            -_coerce_int(ship.get("warp_power")),
            _normalize_compare_text(ship.get("ship_name")),
        )
    )
    return {
        "eligible_probes": eligible,
        "skipped": skipped,
    }


def _probe_fleet_worker_env(args: argparse.Namespace, config: HeadlessConfig) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(repo_root() / "src")
    current_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [part for part in current_pythonpath.split(os.pathsep) if part]
    if src_path not in pythonpath_parts:
        pythonpath_parts.insert(0, src_path)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["GB_FUNCTIONS_URL"] = config.functions_url
    access_token = getattr(args, "access_token", None) or config.access_token
    if isinstance(access_token, str) and access_token:
        env["GB_ACCESS_TOKEN"] = access_token
    character_id = getattr(args, "character_id", None) or config.character_id
    if isinstance(character_id, str) and character_id:
        env["GB_CHARACTER_ID"] = character_id
    if isinstance(config.node_binary, str) and config.node_binary:
        env["GB_NODE_BINARY"] = config.node_binary
    if isinstance(config.bridge_dir, str) and config.bridge_dir:
        env["GB_BRIDGE_DIR"] = config.bridge_dir
    return env


def _probe_frontier_worker_command(
    args: argparse.Namespace,
    *,
    ship: dict[str, Any],
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gradient_bang_headless.cli",
        "session-probe-frontier-loop",
        "--transport",
        args.transport,
        "--ship-name",
        str(ship.get("ship_name") or ""),
        "--ship-id",
        str(ship.get("ship_id") or ""),
        "--connect-timeout-ms",
        str(args.connect_timeout_ms),
        "--request-timeout-ms",
        str(args.request_timeout_ms),
        "--bridge-log-level",
        args.bridge_log_level,
        "--candidate-limit",
        str(args.candidate_limit),
        "--max-hops",
        str(args.max_hops),
        "--max-sectors",
        str(args.max_sectors),
        "--validate-limit",
        str(args.validate_limit),
        "--max-frontiers",
        str(args.max_frontiers),
        "--new-sectors-per-run",
        str(args.new_sectors_per_run),
        "--event-timeout-seconds",
        str(args.event_timeout_seconds),
    ]
    if getattr(args, "access_token", None):
        command.extend(["--access-token", args.access_token])
    if getattr(args, "character_id", None):
        command.extend(["--character-id", args.character_id])
    if getattr(args, "functions_url", None):
        command.extend(["--functions-url", args.functions_url])
    if getattr(args, "search_center_sector", None):
        command.extend(["--search-center-sector", str(args.search_center_sector)])
    if getattr(args, "bypass_tutorial", False):
        command.append("--bypass-tutorial")
    if getattr(args, "voice_id", None):
        command.extend(["--voice-id", args.voice_id])
    if getattr(args, "personality_tone", None):
        command.extend(["--personality-tone", args.personality_tone])
    if getattr(args, "character_name", None):
        command.extend(["--character-name", args.character_name])
    return command


def _summarize_probe_frontier_worker_output(result: dict[str, Any]) -> dict[str, Any]:
    worker_result = result.get("result")
    if not isinstance(worker_result, dict):
        return {}
    attempts = worker_result.get("attempts")
    total_known = 0
    total_corp = 0
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            total_known += _coerce_int(attempt.get("delta_known_sectors_total"))
            total_corp += _coerce_int(attempt.get("delta_corp_sectors_total"))
    final_ship = worker_result.get("final_ship") if isinstance(worker_result.get("final_ship"), dict) else {}
    final_status = worker_result.get("final_status") if isinstance(worker_result.get("final_status"), dict) else {}
    final_summary = final_status.get("summary") if isinstance(final_status.get("summary"), dict) else {}
    return {
        "stop_reason": worker_result.get("stop_reason"),
        "delta_known_sectors_total": total_known,
        "delta_corp_sectors_total": total_corp,
        "final_probe_sector": _coerce_int(final_ship.get("sector")),
        "final_probe_warp": _coerce_int(final_ship.get("warp_power")),
        "known_sectors": _coerce_int(final_summary.get("known_sectors")),
        "corp_sectors_visited": _coerce_int(final_summary.get("corp_sectors_visited")),
    }


async def _run_probe_frontier_worker_subprocess(
    *,
    ship: dict[str, Any],
    command: list[str],
    env: dict[str, str],
) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(repo_root()),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    parsed = None
    parse_error = None
    if stdout_text.strip():
        try:
            parsed = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    result = {
        "ship": ship,
        "command": command,
        "returncode": process.returncode,
        "ok": process.returncode == 0 and isinstance(parsed, dict),
        "stderr_tail": stderr_text.splitlines()[-40:],
    }
    if parse_error is not None:
        result["stdout_parse_error"] = parse_error
        result["stdout_tail"] = stdout_text.splitlines()[-40:]
        return result
    if isinstance(parsed, dict):
        result["summary"] = _summarize_probe_frontier_worker_output(parsed)
    return result


async def _run_probe_fleet_loop(
    args: argparse.Namespace,
    config: HeadlessConfig,
) -> dict[str, Any]:
    if getattr(args, "session_id", None):
        raise HeadlessBridgeError(
            "session-probe-fleet-loop",
            "--session-id is not supported; fleet workers start their own sessions",
        )
    if args.parallelism <= 0:
        raise HeadlessBridgeError("session-probe-fleet-loop", "--parallelism must be > 0")
    if args.max_probes is not None and args.max_probes <= 0:
        raise HeadlessBridgeError("session-probe-fleet-loop", "--max-probes must be > 0")
    if args.min_probe_warp < 0:
        raise HeadlessBridgeError("session-probe-fleet-loop", "--min-probe-warp must be >= 0")

    async with HeadlessBridgeProcess(config) as bridge:
        await bridge.set_log_level(args.bridge_log_level)
        connect_result = await _connect_session_bridge(bridge, args, config)
        status_result = await _fetch_status_snapshot(bridge, timeout=min(args.event_timeout_seconds, 30.0))
        ships_result = await bridge.get_my_ships(timeout=min(args.event_timeout_seconds, 30.0))
        events = await bridge.drain_events()

    classification = _classify_probe_fleet(
        ships_result,
        ship_ids=list(getattr(args, "ship_ids", [])),
        ship_names=list(getattr(args, "ship_names", [])),
        min_probe_warp=args.min_probe_warp,
    )
    eligible = list(classification["eligible_probes"])
    selected = eligible[: args.max_probes] if args.max_probes is not None else eligible
    selection = {
        "eligible_probes": eligible,
        "selected_probes": selected,
        "skipped": classification["skipped"],
    }
    if not selected:
        return {
            "connect": connect_result,
            "status": status_result,
            "ships": ships_result,
            "selection": selection,
            "parallelism": min(args.parallelism, 0 if not eligible else len(eligible)),
            "workers": [],
            "events": events,
            "stop_reason": "no_eligible_probes",
        }

    env = _probe_fleet_worker_env(args, config)
    semaphore = asyncio.Semaphore(min(args.parallelism, len(selected)))

    async def _run_selected_probe(ship: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            command = _probe_frontier_worker_command(args, ship=ship)
            return await _run_probe_frontier_worker_subprocess(
                ship=ship,
                command=command,
                env=env,
            )

    worker_results = await asyncio.gather(*(_run_selected_probe(ship) for ship in selected))
    return {
        "connect": connect_result,
        "status": status_result,
        "ships": ships_result,
        "selection": selection,
        "parallelism": min(args.parallelism, len(selected)),
        "workers": worker_results,
        "events": events,
        "stop_reason": "workers_completed",
    }


async def _run_probe_frontier_loop(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str,
    search_center_sector: int | None,
    candidate_limit: int,
    max_hops: int,
    max_sectors: int,
    validate_limit: int,
    max_frontiers: int,
    new_sectors_per_run: int,
    timeout: float,
) -> dict[str, Any]:
    if candidate_limit <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--candidate-limit must be > 0")
    if max_hops <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--max-hops must be > 0")
    if max_sectors <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--max-sectors must be > 0")
    if validate_limit < 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--validate-limit must be >= 0")
    if max_frontiers <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--max-frontiers must be > 0")
    if new_sectors_per_run <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--new-sectors-per-run must be > 0")
    if timeout <= 0:
        raise HeadlessBridgeError("session-probe-frontier-loop", "--event-timeout-seconds must be > 0")

    initial_status = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
    focus_ship_result = await _fetch_owned_ship_snapshot(
        bridge,
        ship_id=ship_id,
        ship_name=ship_name,
        timeout=min(timeout, 30.0),
    )
    focus_ship = focus_ship_result["ship"]

    origin_sector = search_center_sector or 0
    if origin_sector <= 0:
        origin_sector = _coerce_int(initial_status["summary"].get("sector_id"))
    if origin_sector <= 0:
        raise HeadlessBridgeError(
            "session-probe-frontier-loop",
            "could not determine a search center sector",
        )

    ship_sector = _coerce_int(focus_ship.get("sector")) or _coerce_int(focus_ship.get("sector_id"))
    search_centers: list[int] = []
    for center in (ship_sector, origin_sector):
        if center > 0 and center not in search_centers:
            search_centers.append(center)

    frontier_summary = None
    frontier_candidates: list[dict[str, Any]] = []
    search_attempts: list[dict[str, Any]] = []
    for center_sector in search_centers:
        map_result = await bridge.get_my_map(
            center_sector=center_sector,
            max_hops=max_hops,
            max_sectors=max_sectors,
            timeout=min(timeout, 60.0),
        )
        candidate_summary = _rank_frontier_candidates(
            origin_sector=center_sector,
            map_result=map_result,
            focus_ship=focus_ship,
            limit=candidate_limit,
        )
        if validate_limit > 0:
            candidate_summary = await _validate_frontier_candidates(
                bridge,
                summary=candidate_summary,
                validate_limit=validate_limit,
                timeout=timeout,
            )
        actionable = _actionable_frontier_candidates(candidate_summary)
        search_attempts.append(
            {
                "center_sector": center_sector,
                "map_sector_count": candidate_summary.get("map_sector_count"),
                "frontier_sector_count": candidate_summary.get("frontier_sector_count"),
                "actionable_candidate_count": len(actionable),
                "recommended": candidate_summary.get("recommended"),
            }
        )
        if actionable:
            frontier_summary = candidate_summary
            frontier_candidates = actionable
            origin_sector = center_sector
            break

    if frontier_summary is None:
        frontier_summary = {
            "origin_sector": origin_sector,
            "candidates": [],
        }
    attempts: list[dict[str, Any]] = []
    final_status = {"summary": initial_status["summary"]}
    final_ship = focus_ship

    if not frontier_candidates:
        return {
            "stop_reason": "no_actionable_frontier",
            "search_center_sector": origin_sector,
            "search_attempts": search_attempts,
            "initial_status": initial_status,
            "initial_ship": focus_ship_result,
            "frontier_summary": frontier_summary,
            "attempts": attempts,
            "final_status": final_status,
            "final_ship": final_ship,
        }

    stop_reason = "max_frontiers_exhausted"
    selected_frontiers = frontier_candidates[:max_frontiers]
    for frontier_candidate in selected_frontiers:
        explore_result = await _run_corporation_explore_loop(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            start_sector=_coerce_int(frontier_candidate.get("sector_id")) or None,
            new_sectors_per_run=new_sectors_per_run,
            max_runs=1,
            target_known_sectors=None,
            target_corp_sectors=None,
            timeout=timeout,
        )
        attempt_final_status = explore_result.get("final_status")
        attempt_final_summary = (
            attempt_final_status.get("summary")
            if isinstance(attempt_final_status, dict) and isinstance(attempt_final_status.get("summary"), dict)
            else {}
        )
        final_status = {"summary": attempt_final_summary} if attempt_final_summary else final_status
        attempt_final_ship = explore_result.get("final_ship")
        if isinstance(attempt_final_ship, dict):
            final_ship = attempt_final_ship
        delta_known = None
        delta_corp = None
        if isinstance(attempt_final_summary.get("known_sectors"), int) and isinstance(
            initial_status["summary"].get("known_sectors"), int
        ):
            delta_known = attempt_final_summary["known_sectors"] - initial_status["summary"]["known_sectors"]
        if isinstance(attempt_final_summary.get("corp_sectors_visited"), int) and isinstance(
            initial_status["summary"].get("corp_sectors_visited"), int
        ):
            delta_corp = (
                attempt_final_summary["corp_sectors_visited"]
                - initial_status["summary"]["corp_sectors_visited"]
            )
        branch_progress = any(
            (
                isinstance(run, dict)
                and (
                    _coerce_int(run.get("delta_known_sectors")) > 0
                    or _coerce_int(run.get("delta_corp_sectors")) > 0
                )
            )
            for run in (explore_result.get("runs") if isinstance(explore_result.get("runs"), list) else [])
        )
        attempt = {
            "frontier_candidate": frontier_candidate,
            "explore_result": explore_result,
            "delta_known_sectors_total": delta_known,
            "delta_corp_sectors_total": delta_corp,
            "branch_progress": branch_progress or _coerce_int(delta_known) > 0 or _coerce_int(delta_corp) > 0,
        }
        attempts.append(attempt)
        if attempt["branch_progress"]:
            stop_reason = "frontier_progress"
            break

    return {
        "stop_reason": stop_reason,
        "search_center_sector": origin_sector,
        "search_attempts": search_attempts,
        "initial_status": initial_status,
        "initial_ship": focus_ship_result,
        "frontier_summary": frontier_summary,
        "attempts": attempts,
        "final_status": final_status,
        "final_ship": final_ship,
    }


def _rank_trade_opportunities(
    *,
    status_result: dict[str, Any],
    ports_result: dict[str, Any],
    map_result: dict[str, Any] | None,
    commodities: list[str],
    limit: int,
) -> dict[str, Any]:
    if limit <= 0:
        raise HeadlessBridgeError("session-trade-opportunities", "--limit must be > 0")

    status_payload = _extract_bridge_payload(status_result)
    ports_payload = _extract_bridge_payload(ports_result)
    map_payload = _extract_bridge_payload(map_result or {})

    ship = status_payload.get("ship") if isinstance(status_payload, dict) else None
    sector = status_payload.get("sector") if isinstance(status_payload, dict) else None
    ports = ports_payload.get("ports") if isinstance(ports_payload, dict) else None
    graph = _map_graph_from_payload(map_payload)

    cargo_capacity = _coerce_int(ship.get("cargo_capacity")) if isinstance(ship, dict) else 0
    ship_credits = _coerce_int(ship.get("credits")) if isinstance(ship, dict) else 0
    current_sector = _coerce_int(sector.get("id")) if isinstance(sector, dict) else 0
    distances_from_current = _shortest_path_lengths(graph, start=current_sector) if current_sector > 0 else {}

    commodity_list = commodities or ["quantum_foam", "retro_organics", "neuro_symbolics"]
    if not isinstance(ports, list):
        return {
            "current_sector": current_sector or None,
            "ship_credits": ship_credits,
            "cargo_capacity": cargo_capacity,
            "opportunities": [],
        }

    rows: list[dict[str, Any]] = []
    pair_distance_cache: dict[tuple[int, int], int | None] = {}
    for buy_port in ports:
        if not isinstance(buy_port, dict):
            continue
        buy_sector = buy_port.get("sector")
        if not isinstance(buy_sector, dict):
            continue
        buy_port_info = buy_sector.get("port")
        if not isinstance(buy_port_info, dict):
            continue
        buy_prices = buy_port_info.get("prices")
        if not isinstance(buy_prices, dict):
            continue
        buy_stock = buy_port_info.get("stock")
        if not isinstance(buy_stock, dict):
            continue
        buy_port_code = buy_port_info.get("code")
        buy_hops = _coerce_int(buy_port.get("hops_from_start"))

        for sell_port in ports:
            if not isinstance(sell_port, dict):
                continue
            sell_sector = sell_port.get("sector")
            if not isinstance(sell_sector, dict):
                continue
            sell_port_info = sell_sector.get("port")
            if not isinstance(sell_port_info, dict):
                continue
            sell_prices = sell_port_info.get("prices")
            if not isinstance(sell_prices, dict):
                continue
            sell_port_code = sell_port_info.get("code")

            buy_sector_id = _coerce_int(buy_sector.get("id"))
            sell_sector_id = _coerce_int(sell_sector.get("id"))
            if buy_sector_id <= 0 or sell_sector_id <= 0 or buy_sector_id == sell_sector_id:
                continue

            sell_hops = _coerce_int(sell_port.get("hops_from_start"))
            distance_to_buy = distances_from_current.get(buy_sector_id, buy_hops)
            pair_key = (buy_sector_id, sell_sector_id)
            if pair_key not in pair_distance_cache:
                distances_from_buy = _shortest_path_lengths(graph, start=buy_sector_id)
                pair_distance_cache[pair_key] = distances_from_buy.get(sell_sector_id)
            inter_port_hops = pair_distance_cache[pair_key]
            distance_source = "map"
            if inter_port_hops is None:
                inter_port_hops = abs(sell_hops - buy_hops)
                distance_source = "approx_hops_from_start"
            total_hops = distance_to_buy + inter_port_hops

            for commodity in commodity_list:
                if not _port_allows_buy(str(buy_port_code), commodity):
                    continue
                if not _port_allows_sell(str(sell_port_code), commodity):
                    continue
                buy_price = _coerce_int(buy_prices.get(commodity))
                sell_price = _coerce_int(sell_prices.get(commodity))
                spread = sell_price - buy_price
                if buy_price <= 0 or spread <= 0:
                    continue
                available_stock = _coerce_int(buy_stock.get(commodity))
                max_units = min(cargo_capacity, ship_credits // buy_price, available_stock)
                if max_units <= 0:
                    continue
                expected_profit = spread * max_units
                expected_volume = (buy_price + sell_price) * max_units
                rows.append(
                    {
                        "commodity": commodity,
                        "buy_sector": buy_sector_id,
                        "buy_port_code": buy_port_code,
                        "sell_sector": sell_sector_id,
                        "sell_port_code": sell_port_code,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "spread": spread,
                        "max_units": max_units,
                        "expected_profit": expected_profit,
                        "expected_trade_volume": expected_volume,
                        "distance_to_buy": distance_to_buy,
                        "distance_buy_to_sell": inter_port_hops,
                        "distance_total": total_hops,
                        "distance_source": distance_source,
                        "profit_per_total_hop": round(expected_profit / max(total_hops, 1), 2),
                        "volume_per_total_hop": round(expected_volume / max(total_hops, 1), 2),
                    }
                )

    rows.sort(
        key=lambda row: (
            row["profit_per_total_hop"],
            row["expected_profit"],
            row["expected_trade_volume"],
            -row["distance_total"],
        ),
        reverse=True,
    )

    return {
        "current_sector": current_sector or None,
        "ship_credits": ship_credits,
        "cargo_capacity": cargo_capacity,
        "best_by_profit": max(rows, key=lambda row: row["expected_profit"], default=None),
        "best_by_profit_per_hop": max(rows, key=lambda row: row["profit_per_total_hop"], default=None),
        "best_by_volume_per_hop": max(rows, key=lambda row: row["volume_per_total_hop"], default=None),
        "opportunities": rows[:limit],
    }


def _select_trade_opportunity(summary: dict[str, Any], goal: str) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    if goal == "wealth":
        selected = summary.get("best_by_profit_per_hop")
    elif goal == "trading":
        selected = summary.get("best_by_volume_per_hop")
    else:
        selected = summary.get("best_by_profit")
    return selected if isinstance(selected, dict) else None


def _port_price(summary: dict[str, Any], commodity: str) -> int | None:
    port_prices = summary.get("port_prices")
    if not isinstance(port_prices, dict):
        return None
    price = port_prices.get(commodity)
    return int(price) if isinstance(price, int) else None


def _port_stock(summary: dict[str, Any], commodity: str) -> int | None:
    port_stock = summary.get("port_stock")
    if not isinstance(port_stock, dict):
        return None
    stock = port_stock.get(commodity)
    return int(stock) if isinstance(stock, int) else None


def _loaded_route_commodity(summary: dict[str, Any], commodities: tuple[str, ...]) -> str | None:
    loaded = [commodity for commodity in commodities if _cargo_units(summary, commodity) > 0]
    if len(loaded) > 1:
        raise HeadlessBridgeError(
            "session-shuttle-loop",
            "ship is carrying multiple route commodities",
            payload={"loaded": loaded, "summary": summary},
        )
    return loaded[0] if loaded else None


def _build_exact_buy_prompt(summary: dict[str, Any], commodity: str) -> str:
    selection = _select_explicit_loadout(summary, commodity=commodity, quantity=None)
    return build_trade_order_prompt(
        trade_type="BUY",
        quantity=selection["quantity"],
        commodity=commodity,
        price_per_unit=selection["price_per_unit"],
    )


def _build_exact_sell_prompt(summary: dict[str, Any], commodity: str) -> str:
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


def _build_route_buy_prompt(summary: dict[str, Any], commodity: str) -> str:
    try:
        return _build_exact_buy_prompt(summary, commodity)
    except HeadlessBridgeError:
        price = _port_price(summary, commodity)
        empty_holds = summary.get("empty_holds")
        credits = summary.get("ship_credits")
        if (
            isinstance(price, int)
            and price > 0
            and isinstance(empty_holds, int)
            and empty_holds > 0
            and isinstance(credits, int)
        ):
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
    return _build_exact_sell_prompt(summary, commodity)


async def _run_shuttle_loop(
    bridge: HeadlessBridgeProcess,
    *,
    home_sector: int,
    away_sector: int,
    home_commodity: str,
    away_commodity: str,
    max_cycles: int | None,
    target_credits: int | None,
    min_warp: int,
    step_retries: int,
    finish_loaded_home: bool,
    timeout: float,
) -> dict[str, Any]:
    if home_sector <= 0 or away_sector <= 0:
        raise HeadlessBridgeError("session-shuttle-loop", "sector ids must be > 0")
    if home_sector == away_sector:
        raise HeadlessBridgeError("session-shuttle-loop", "home and away sectors must differ")
    if home_commodity == away_commodity:
        raise HeadlessBridgeError("session-shuttle-loop", "home and away commodities must differ")
    if max_cycles is not None and max_cycles <= 0:
        raise HeadlessBridgeError("session-shuttle-loop", "--max-cycles must be > 0")
    if target_credits is not None and target_credits <= 0:
        raise HeadlessBridgeError("session-shuttle-loop", "--target-credits must be > 0")
    if min_warp < 0:
        raise HeadlessBridgeError("session-shuttle-loop", "--min-warp must be >= 0")
    if step_retries < 0:
        raise HeadlessBridgeError("session-shuttle-loop", "--step-retries must be >= 0")

    initial_status = await _fetch_status_snapshot(bridge, timeout=timeout)
    current_summary = initial_status["summary"]
    cycle_results: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    current_cycle_start: dict[str, Any] | None = None
    current_cycle_steps: list[dict[str, Any]] | None = None
    stop_reason = "unknown"

    async def _execute_step(
        *,
        step: str,
        prompt: str,
        validate,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nonlocal current_summary
        outcome = await _run_validated_player_step(
            bridge,
            prompt=prompt,
            timeout=timeout,
            retries=step_retries,
            validate=validate,
        )
        result = outcome["result"]
        after = result["status"]["summary"] if isinstance(result, dict) else current_summary
        entry = {
            "step": step,
            "prompt": prompt,
            "result": result,
            "attempt_count": outcome["attempt_count"],
        }
        if isinstance(payload, dict):
            entry.update(payload)
        steps.append(entry)
        if current_cycle_steps is not None:
            current_cycle_steps.append(entry)
        current_summary = after
        return outcome

    while True:
        current_sector = _coerce_int(current_summary.get("sector_id"))
        current_credits = current_summary.get("ship_credits")
        current_warp = _status_warp(current_summary)
        total_cargo_units = _total_cargo_units(current_summary)
        home_units = _cargo_units(current_summary, home_commodity)
        away_units = _cargo_units(current_summary, away_commodity)

        if total_cargo_units > home_units + away_units:
            stop_reason = "foreign_cargo_present"
            break
        if target_credits is not None and isinstance(current_credits, int) and current_credits >= target_credits:
            stop_reason = "target_credits_reached"
            break
        if max_cycles is not None and len(cycle_results) >= max_cycles:
            stop_reason = "max_cycles_reached"
            break
        if current_warp is not None and current_warp < min_warp:
            stop_reason = "min_warp_reached"
            break

        loaded_commodity = _loaded_route_commodity(current_summary, (home_commodity, away_commodity))

        if current_sector == home_sector:
            if loaded_commodity == away_commodity:
                if not _port_allows_sell(current_summary.get("port_code"), away_commodity):
                    stop_reason = "invalid_home_sell_port"
                    break
                sell_away_outcome = await _execute_step(
                    step="sell_away_at_home",
                    prompt=_build_exact_sell_prompt(current_summary, away_commodity),
                    validate=lambda summary: _cargo_units(summary, away_commodity) == 0,
                    payload={"sector": home_sector, "commodity": away_commodity},
                )
                if not sell_away_outcome["success"]:
                    recovery_result = await _recover_with_trade_order(
                        bridge,
                        summary=current_summary,
                        commodity=away_commodity,
                        timeout=timeout,
                    )
                    recovery_entry = {
                        "step": "sell_away_recovery",
                        "sector": home_sector,
                        "commodity": away_commodity,
                        "result": recovery_result,
                    }
                    steps.append(recovery_entry)
                    if current_cycle_steps is not None:
                        current_cycle_steps.append(recovery_entry)
                    recovery_summary = recovery_result.get("status", {}).get("summary")
                    if isinstance(recovery_summary, dict):
                        current_summary = recovery_summary
                    if _cargo_units(current_summary, away_commodity) > 0:
                        stop_reason = "home_sell_failed"
                        break
                if current_cycle_start is not None:
                    cycle_results.append(
                        {
                            "cycle": len(cycle_results) + 1,
                            "home_sector": home_sector,
                            "away_sector": away_sector,
                            "home_commodity": home_commodity,
                            "away_commodity": away_commodity,
                            "start": current_cycle_start,
                            "end": dict(current_summary),
                            "profit": (
                                current_summary["ship_credits"] - current_cycle_start["ship_credits"]
                                if isinstance(current_summary.get("ship_credits"), int)
                                and isinstance(current_cycle_start.get("ship_credits"), int)
                                else None
                            ),
                            "warp_spent": (
                                current_cycle_start["warp_power"] - current_summary["warp_power"]
                                if isinstance(current_summary.get("warp_power"), int)
                                and isinstance(current_cycle_start.get("warp_power"), int)
                                else None
                            ),
                            "steps": list(current_cycle_steps or []),
                        }
                    )
                    current_cycle_start = None
                    current_cycle_steps = None
                continue

            if loaded_commodity is None:
                if not _port_allows_buy(current_summary.get("port_code"), home_commodity):
                    stop_reason = "invalid_home_buy_port"
                    break
                current_cycle_steps = []
                load_home_outcome = await _execute_step(
                    step="load_home",
                    prompt=_build_exact_buy_prompt(current_summary, home_commodity),
                    validate=lambda summary: _cargo_units(summary, home_commodity) > 0,
                    payload={"sector": home_sector, "commodity": home_commodity},
                )
                if not load_home_outcome["success"]:
                    stop_reason = "home_buy_failed"
                    break
                current_cycle_start = dict(current_summary)
                continue

            if loaded_commodity != home_commodity:
                stop_reason = "unexpected_home_cargo_state"
                break
            if current_cycle_start is None:
                current_cycle_start = dict(current_summary)
                current_cycle_steps = []
            move_to_away_outcome = await _execute_step(
                step="move_to_away_sector",
                prompt=build_move_to_sector_prompt(sector_id=away_sector),
                validate=lambda summary: summary.get("sector_id") == away_sector,
                payload={"sector": away_sector},
            )
            if not move_to_away_outcome["success"]:
                stop_reason = "move_to_away_failed"
                break
            continue

        if current_sector == away_sector:
            if loaded_commodity == home_commodity:
                if not _port_allows_sell(current_summary.get("port_code"), home_commodity):
                    stop_reason = "invalid_away_sell_port"
                    break
                sell_home_outcome = await _execute_step(
                    step="sell_home_at_away",
                    prompt=_build_exact_sell_prompt(current_summary, home_commodity),
                    validate=lambda summary: _cargo_units(summary, home_commodity) == 0,
                    payload={"sector": away_sector, "commodity": home_commodity},
                )
                if not sell_home_outcome["success"]:
                    recovery_result = await _recover_with_trade_order(
                        bridge,
                        summary=current_summary,
                        commodity=home_commodity,
                        timeout=timeout,
                    )
                    recovery_entry = {
                        "step": "sell_home_recovery",
                        "sector": away_sector,
                        "commodity": home_commodity,
                        "result": recovery_result,
                    }
                    steps.append(recovery_entry)
                    if current_cycle_steps is not None:
                        current_cycle_steps.append(recovery_entry)
                    recovery_summary = recovery_result.get("status", {}).get("summary")
                    if isinstance(recovery_summary, dict):
                        current_summary = recovery_summary
                    if _cargo_units(current_summary, home_commodity) > 0:
                        stop_reason = "away_sell_failed"
                        break
                continue

            if loaded_commodity is None:
                if not _port_allows_buy(current_summary.get("port_code"), away_commodity):
                    stop_reason = "invalid_away_buy_port"
                    break
                load_away_outcome = await _execute_step(
                    step="load_away",
                    prompt=_build_exact_buy_prompt(current_summary, away_commodity),
                    validate=lambda summary: _cargo_units(summary, away_commodity) > 0,
                    payload={"sector": away_sector, "commodity": away_commodity},
                )
                if not load_away_outcome["success"]:
                    stop_reason = "away_buy_failed"
                    break
                continue

            if loaded_commodity != away_commodity:
                stop_reason = "unexpected_away_cargo_state"
                break
            move_to_home_outcome = await _execute_step(
                step="move_to_home_sector",
                prompt=build_move_to_sector_prompt(sector_id=home_sector),
                validate=lambda summary: summary.get("sector_id") == home_sector,
                payload={"sector": home_sector},
            )
            if not move_to_home_outcome["success"]:
                stop_reason = "move_to_home_failed"
                break
            continue

        recovery_sector = home_sector
        recovery_step = "move_to_home_sector"
        if loaded_commodity == home_commodity:
            recovery_sector = away_sector
            recovery_step = "move_to_away_sector"
        recovery_outcome = await _execute_step(
            step=recovery_step,
            prompt=build_move_to_sector_prompt(sector_id=recovery_sector),
            validate=lambda summary: summary.get("sector_id") == recovery_sector,
            payload={"sector": recovery_sector},
        )
        if not recovery_outcome["success"]:
            stop_reason = "recovery_move_failed"
            break

    final_loadout = None
    if (
        finish_loaded_home
        and stop_reason in {"target_credits_reached", "max_cycles_reached", "min_warp_reached"}
        and _coerce_int(current_summary.get("sector_id")) == home_sector
        and _total_cargo_units(current_summary) == 0
        and _port_allows_buy(current_summary.get("port_code"), home_commodity)
    ):
        final_loadout_outcome = await _run_validated_player_step(
            bridge,
            prompt=_build_exact_buy_prompt(current_summary, home_commodity),
            timeout=timeout,
            retries=step_retries,
            validate=lambda summary: _cargo_units(summary, home_commodity) > 0,
        )
        final_result = final_loadout_outcome["result"]
        if isinstance(final_result, dict):
            current_summary = final_result["status"]["summary"]
        final_loadout = {
            "step": "final_home_load",
            "result": final_result,
            "attempt_count": final_loadout_outcome["attempt_count"],
            "success": final_loadout_outcome["success"],
        }
        steps.append(final_loadout)
        if not final_loadout_outcome["success"]:
            stop_reason = "final_home_load_failed"

    return {
        "success": stop_reason in {
            "target_credits_reached",
            "max_cycles_reached",
            "min_warp_reached",
        },
        "stop_reason": stop_reason,
        "home_sector": home_sector,
        "away_sector": away_sector,
        "home_commodity": home_commodity,
        "away_commodity": away_commodity,
        "target_credits": target_credits,
        "max_cycles": max_cycles,
        "min_warp": min_warp,
        "step_retries": step_retries,
        "finish_loaded_home": finish_loaded_home,
        "cycles_completed": len(cycle_results),
        "initial_status": initial_status["summary"],
        "final_status": current_summary,
        "final_loadout": final_loadout,
        "cycles": cycle_results,
        "steps": steps,
    }


async def _run_corporation_explore_loop(
    bridge: HeadlessBridgeProcess,
    *,
    ship_id: str | None,
    ship_name: str,
    start_sector: int | None,
    new_sectors_per_run: int,
    max_runs: int | None,
    target_known_sectors: int | None,
    target_corp_sectors: int | None,
    timeout: float,
) -> dict[str, Any]:
    if new_sectors_per_run <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--new-sectors-per-run must be > 0")
    if start_sector is not None and start_sector <= 0:
        raise HeadlessBridgeError("session-corp-explore-loop", "--start-sector must be > 0")
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
    frontier_reset = None
    runs: list[dict[str, Any]] = []
    stop_reason = "not_started"

    if start_sector is not None and current_ship.get("sector") != start_sector:
        frontier_reset = await _run_corporation_move_to_sector(
            bridge,
            ship_id=ship_id,
            ship_name=ship_name,
            sector_id=start_sector,
            max_segments=12,
            timeout=timeout,
        )
        current_ship = frontier_reset["final_ship"]
        if current_ship.get("sector") != start_sector:
            return {
                "stop_reason": "frontier_reset_failed",
                "task_description": task_description,
                "initial_status": initial_status,
                "initial_ship": initial_ship,
                "frontier_reset": frontier_reset,
                "runs": runs,
                "final_status": {
                    "summary": current_summary,
                },
                "final_ship": current_ship,
            }
        refreshed_status = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
        current_summary = refreshed_status["summary"]

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
        "frontier_reset": frontier_reset,
        "runs": runs,
        "final_status": {
            "summary": current_summary,
        },
        "final_ship": current_ship,
    }


async def _run_auto_trade_loop(
    bridge: HeadlessBridgeProcess,
    *,
    goal: str,
    commodities: list[str],
    limit: int,
    map_max_hops: int,
    map_max_sectors: int,
    max_cycles: int | None,
    target_credits: int | None,
    min_warp: int,
    step_retries: int,
    timeout: float,
) -> dict[str, Any]:
    status_result = await bridge.get_my_status(timeout=timeout)
    ports_result = await bridge.get_known_ports(timeout=timeout)
    status_payload = _extract_bridge_payload(status_result)
    current_sector = _coerce_int(status_payload.get("sector", {}).get("id"))
    map_result = await bridge.get_my_map(
        center_sector=current_sector,
        max_hops=map_max_hops,
        max_sectors=map_max_sectors,
        timeout=timeout,
    )
    opportunities = _rank_trade_opportunities(
        status_result=status_result,
        ports_result=ports_result,
        map_result=map_result,
        commodities=commodities,
        limit=limit,
    )
    selected = _select_trade_opportunity(opportunities, goal)
    if not isinstance(selected, dict):
        raise HeadlessBridgeError(
            "session-auto-trade-loop",
            f"no route available for goal {goal!r}",
            payload=opportunities,
        )

    loop_result = await _run_trade_route_loop(
        bridge,
        buy_sector=_coerce_int(selected.get("buy_sector")),
        sell_sector=_coerce_int(selected.get("sell_sector")),
        commodity=str(selected.get("commodity")),
        max_cycles=max_cycles,
        target_credits=target_credits,
        min_warp=min_warp,
        step_retries=step_retries,
        timeout=timeout,
    )
    return {
        "goal": goal,
        "selected_route": selected,
        "opportunities": opportunities,
        "loop": loop_result,
    }


async def _recover_with_trade_order(
    bridge: HeadlessBridgeProcess,
    *,
    summary: dict[str, Any],
    commodity: str,
    timeout: float,
) -> dict[str, Any]:
    trade_order_prompt = _build_route_sell_prompt(summary, commodity)
    action_result = await bridge.user_text_input(trade_order_prompt, wait_seconds=0.0)
    watch_result = await _watch_player_task(
        bridge,
        wait_for_finish=True,
        timeout=timeout,
    )
    status_result = await _fetch_status_snapshot(bridge, timeout=min(timeout, 30.0))
    final_summary = status_result["summary"]
    success = _cargo_units(final_summary, commodity) == 0
    fallback_result = None
    if not success:
        fallback_prompt = build_sell_all_commodity_prompt(commodity=commodity)
        fallback_result = await _run_validated_player_step(
            bridge,
            prompt=fallback_prompt,
            timeout=timeout,
            retries=1,
            validate=lambda current: _cargo_units(current, commodity) == 0,
        )
        fallback_status = (
            fallback_result.get("result", {}).get("status")
            if isinstance(fallback_result.get("result"), dict)
            else None
        )
        if isinstance(fallback_status, dict):
            status_result = fallback_status
            final_summary = fallback_status.get("summary", final_summary)
            success = _cargo_units(final_summary, commodity) == 0
    return {
        "prompt": trade_order_prompt,
        "result": action_result,
        "watch": watch_result,
        "status": status_result,
        "success": success,
        "fallback": fallback_result,
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
    current_cycle_start: dict[str, Any] | None = None
    current_cycle_steps: list[dict[str, Any]] | None = None

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
            if not _port_allows_sell(current_summary.get("port_code"), commodity):
                stop_reason = "invalid_sell_port"
                break
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
        current_cycle_start = cycle_start
        current_cycle_steps = cycle_step_results

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
        if not _port_allows_buy(current_summary.get("port_code"), commodity):
            stop_reason = "invalid_buy_port"
            break

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
        if not _port_allows_sell(current_summary.get("port_code"), commodity):
            stop_reason = "invalid_sell_port"
            break

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
        current_cycle_start = None
        current_cycle_steps = None

    trade_order_recovery = None
    if stop_reason in {"sell_failed", "recovery_sell_failed"} and _cargo_units(current_summary, commodity) > 0:
        trade_order_recovery = await _recover_with_trade_order(
            bridge,
            summary=current_summary,
            commodity=commodity,
            timeout=timeout,
        )
        recovery_steps.append(
            {
                "step": "trade_order_sell_recovery",
                "commodity": commodity,
                "result": trade_order_recovery,
            }
        )
        steps.append(recovery_steps[-1])
        recovery_summary = trade_order_recovery["status"]["summary"]
        if isinstance(recovery_summary, dict):
            current_summary = recovery_summary
        if trade_order_recovery.get("success"):
            if current_cycle_start is not None:
                recovered_cycle_steps = list(current_cycle_steps or [])
                recovered_cycle_steps.append(recovery_steps[-1])
                cycle_results.append(
                    {
                        "cycle": len(cycle_results) + 1,
                        "buy_sector": buy_sector,
                        "sell_sector": sell_sector,
                        "commodity": commodity,
                        "start": current_cycle_start,
                        "end": dict(current_summary),
                        "profit": (
                            current_summary["ship_credits"] - current_cycle_start["ship_credits"]
                            if isinstance(current_summary.get("ship_credits"), int)
                            and isinstance(current_cycle_start.get("ship_credits"), int)
                            else None
                        ),
                        "warp_spent": (
                            current_cycle_start["warp_power"] - current_summary["warp_power"]
                            if isinstance(current_summary.get("warp_power"), int)
                            and isinstance(current_cycle_start.get("warp_power"), int)
                            else None
                        ),
                        "steps": recovered_cycle_steps,
                        "recovered_sell": True,
                    }
                )
                current_cycle_start = None
                current_cycle_steps = None
            stop_reason = "sell_recovered"

    return {
        "success": stop_reason in {
            "target_credits_reached",
            "max_cycles_reached",
            "min_warp_reached",
            "sell_recovered",
        },
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
        "trade_order_recovery": trade_order_recovery,
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


def _leaderboard_neighbors(
    *,
    config: HeadlessConfig,
    leaderboard_result: dict[str, Any],
    status_result: dict[str, Any],
    transport: str,
) -> dict[str, Any]:
    status_payload = _extract_bridge_payload(status_result)
    player = status_payload.get("player") if isinstance(status_payload, dict) else None
    source = status_payload.get("source") if isinstance(status_payload, dict) else None

    player_name = player.get("name") if isinstance(player, dict) else None
    character_id = player.get("id") if isinstance(player, dict) else None
    if not isinstance(player_name, str) or not player_name:
        player_name = config.character_name
    if not isinstance(character_id, str) or not character_id:
        character_id = config.character_id

    return {
        "player_name": player_name,
        "character_id": character_id,
        "transport": transport,
        "leaderboard_cached": bool(leaderboard_result.get("cached")),
        "status_timestamp": source.get("timestamp") if isinstance(source, dict) else None,
        "neighbors": {
            "wealth": _leaderboard_neighbor_summary(
                _human_leaderboard_rows(leaderboard_result.get("wealth"), "total_wealth"),
                stat_key="total_wealth",
                character_id=character_id,
            ),
            "trading": _leaderboard_neighbor_summary(
                _human_leaderboard_rows(leaderboard_result.get("trading"), "total_trade_volume"),
                stat_key="total_trade_volume",
                character_id=character_id,
            ),
            "exploration": _leaderboard_neighbor_summary(
                _human_leaderboard_rows(leaderboard_result.get("exploration"), "sectors_visited"),
                stat_key="sectors_visited",
                character_id=character_id,
            ),
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


def _leaderboard_neighbor_summary(
    rows: list[dict[str, Any]],
    *,
    stat_key: str,
    character_id: str | None,
) -> dict[str, Any]:
    own_entry = _find_leaderboard_entry(rows, character_id)
    if not isinstance(own_entry, dict):
        return {
            "visible_rank": None,
            "self": None,
            "next_up": None,
            "next_down": None,
        }

    try:
        index = rows.index(own_entry)
    except ValueError:
        index = -1
    visible_rank = index + 1 if index >= 0 else None
    next_up = rows[index - 1] if index > 0 else None
    next_down = rows[index + 1] if index >= 0 and index + 1 < len(rows) else None
    own_value = _coerce_int(own_entry.get(stat_key))

    return {
        "visible_rank": visible_rank,
        "self": _leaderboard_neighbor_entry(own_entry, stat_key=stat_key),
        "next_up": _leaderboard_neighbor_entry(
            next_up,
            stat_key=stat_key,
            gap=max(0, _coerce_int(next_up.get(stat_key)) - own_value) if isinstance(next_up, dict) else None,
        ),
        "next_down": _leaderboard_neighbor_entry(
            next_down,
            stat_key=stat_key,
            gap=max(0, own_value - _coerce_int(next_down.get(stat_key))) if isinstance(next_down, dict) else None,
        ),
    }


def _leaderboard_neighbor_entry(
    entry: dict[str, Any] | None,
    *,
    stat_key: str,
    gap: int | None = None,
) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    value = _coerce_int(entry.get(stat_key))
    result = {
        "player_name": entry.get("player_name"),
        "value": value,
    }
    if gap is not None:
        result["gap"] = gap
    if stat_key == "total_wealth":
        result["ships_owned"] = _coerce_int(entry.get("ships_owned"))
    if stat_key == "total_trade_volume":
        result["total_trades"] = _coerce_int(entry.get("total_trades"))
        result["ports_visited"] = _coerce_int(entry.get("ports_visited"))
    return result


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
