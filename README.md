# Gradient Bang Headless

This repo is the home for a headless client and automation tooling for Gradient Bang.

## Layout

- `upstream/`: game core submodule, pinned to `git@github.com:wakamex/gradient-bang.git`
- `src/gradient_bang_headless/`: headless client scaffold
- `bridge/`: session transport runtimes for Pipecat, with browser-backed Daily as the live path

## Current Scope

This scaffold supports:

- public control-plane calls like `register`, `login`, `user_character_create`, and `start`
- public read-only calls like `leaderboard_resources`
- named protected gameplay calls for trusted use
- generic edge-function calls against `https://api.gradient-bang.com/functions/v1`
- `events_since` polling for request/event correlation
- a production-proven browser-backed Daily bridge in [bridge/README.md](/code/gradient/bridge/README.md)
- raw Node `daily` and `smallwebrtc` diagnostic bridge modes
- Python/CLI bridge integration for session connect/request/message/text flows
- first-class live session reads for status, ports, map, chat history, ship lists, ship definitions, corporation data, task events, and quest status
- a first-class `session-trade-opportunities` helper that ranks the current known-port graph
- a first-class `session-auto-trade-loop` that picks a route for `wealth`, `trading`, or raw `profit`
- a first-class `session-move-to-sector` helper for exact move-and-validate execution
- a first-class `session-corp-move-to-sector` helper for repeated partial corporation-ship moves toward a target sector
- a first-class `session-nearest-mega-port` helper for recharge-route discovery
- exact frontend prompt contracts for trade orders and ship purchase requests
- first-class logistics helpers for warp recharge, credit transfer, and bidirectional warp transfer
- a first-class `session-corp-explore-loop` for repeated probe frontier runs
- a deterministic `session-trade-route-loop` for repeatable personal trading
- a reusable `loop` runner for long bot-driven objectives with state polling and reprompts
- a bridge into `upstream/` so trusted tooling can reuse `gradientbang.utils.supabase_client.AsyncGameClient`

## Important Constraint

The live game client uses `https://api.gradient-bang.com/functions/v1/start`.
Most gameplay edge functions are still protected by `X-API-Token`, so a public headless client still needs a scoped gameplay-session/token flow before it can safely call gameplay endpoints directly.

## Setup

```bash
git submodule update --init --recursive
python -m venv .venv
. .venv/bin/activate
pip install -e .

cd bridge
npm install
```

## Environment

The CLI auto-loads a repo-root `.env` if present. Copy `.env.example` or export
values directly:

- `GB_FUNCTIONS_URL`: defaults to `https://api.gradient-bang.com/functions/v1`
- `GB_EMAIL`: default login email for public/bootstrap flows
- `GB_PASSWORD`: default login password for public/bootstrap flows
- `GB_CHARACTER_NAME`: default character name for bootstrap flows
- `GB_API_TOKEN`: trusted gameplay token for protected edge functions
- `GB_ACCESS_TOKEN`: Supabase access token returned by `login`
- `GB_REFRESH_TOKEN`: Supabase refresh token returned by `login`
- `GB_CHARACTER_ID`: default player character for gameplay calls
- `GB_ACTOR_CHARACTER_ID`: optional corp-member actor when driving corp ships

## CLI

```bash
gb-headless login
gb-headless auth-sync
gb-headless register
gb-headless login --email you@example.com --password 'secret'
gb-headless auth-sync --character-name "$GB_CHARACTER_NAME"
gb-headless register --email you@example.com --password 'secret'
gb-headless confirm-url --verify-url 'https://api.gradient-bang.com/auth/v1/verify?...'
gb-headless character-list --access-token "$GB_ACCESS_TOKEN"
gb-headless character-create --access-token "$GB_ACCESS_TOKEN"
gb-headless start-session --access-token "$GB_ACCESS_TOKEN"
gb-headless leaderboard-resources
gb-headless leaderboard-self-summary --transport daily
gb-headless leaderboard-neighbors --transport daily
gb-headless signup-and-start \
  --verify-url 'https://api.gradient-bang.com/auth/v1/verify?...'
gb-headless session-connect --character-id "$GB_CHARACTER_ID" --access-token "$GB_ACCESS_TOKEN"
gb-headless session-connect \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --transport rawdaily
gb-headless session-connect \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --transport smallwebrtc \
  --connect-timeout-ms 8000
gb-headless session-request \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --message-type get-my-status
gb-headless session-message \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --message-type start
gb-headless session-send-text \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --content 'plot a safe course'
gb-headless session-status \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-known-ports \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-nearest-mega-port \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-trade-opportunities \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --limit 12
gb-headless session-auto-trade-loop \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --goal wealth \
  --max-cycles 2
gb-headless session-chat-history \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-ships \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-ship-definitions \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-quest-status \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-claim-all-rewards \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-trade-order \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --trade-type buy \
  --commodity neuro_symbolics \
  --quantity 20 \
  --price-per-unit 30
gb-headless session-purchase-ship \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --ship-display-name "Kestrel Courier" \
  --replace-ship-id "<current-ship-id>" \
  --replace-ship-name "Sparrow Scout"
gb-headless session-corp-task \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --ship-name "gbheadless Auto Probe 1" \
  --ship-id eab4cd \
  --task-description 'travel to sector 1908 and stop there.' \
  --wait-for-finish
gb-headless session-corp-explore-loop \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --ship-name "gbheadless Auto Probe 1" \
  --ship-id eab4cd \
  --new-sectors-per-run 20 \
  --max-runs 3
gb-headless session-collect-unowned-ship \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --ship-id "<unowned-ship-uuid>"
gb-headless loop \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --target-sector 1413 \
  --objective 'Proceed directly to sector 1413 and stop.'
gb-headless session-assign-quest \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --quest-code tutorial_corporations
gb-headless session-watch \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --message-type start \
  --duration-seconds 5
gb-headless session-player-task \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --task-description 'Move to sector 1908, buy as much retro organics as possible there, return to sector 3358, sell all retro organics, then stop and report final credits and sector.' \
  --wait-for-finish
gb-headless session-move-to-sector \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --sector-id 3246
gb-headless session-recharge-warp \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --wait-for-finish
gb-headless session-transfer-credits \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --amount 100 \
  --to-ship-name "gbheadless Auto Hauler 1" \
  --to-ship-id c7c348
gb-headless session-transfer-warp \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --units 100 \
  --to-ship-name "gbheadless Auto Hauler 1" \
  --to-ship-id c7c348 \
  --wait-for-finish
gb-headless session-trade-route-loop \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --buy-sector 3786 \
  --sell-sector 1009 \
  --commodity neuro_symbolics \
  --max-cycles 6 \
  --step-retries 2
gb-headless session-corp-move-to-sector \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --ship-name "gbheadless Auto Hauler 1" \
  --ship-id c7c348 \
  --sector-id 3341
gb-headless call leaderboard_resources --method GET
gb-headless status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless plot-course --to-sector 301 --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless known-ports --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless quest-status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless game-call my_status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless events-since --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN" --follow
```

## Notes

- `call` is a generic edge-function wrapper.
- `leaderboard-resources` is the preferred public command for the leaderboard
  read model instead of `call leaderboard_resources --method GET`.
- `leaderboard-self-summary` combines the public leaderboard read with live
  session status and ship state to produce a compact "my stats vs leaders"
  summary for the configured character.
- `leaderboard-neighbors` is the preferred command for planning the next
  visible rank push. It shows the nearest visible row above and below the
  current player in each public category.
- `status`, `move`, `plot-course`, `map-region`, `known-ports`, `trade`,
  `recharge-warp`, `purchase-fighters`, `ship-definitions`, `ship-purchase`,
  `quest-status`, `quest-assign`, and `quest-claim-reward` are the preferred
  trusted gameplay commands over raw `game-call`.
- `session-status`, `session-known-ports`, `session-task-history`,
  `session-nearest-mega-port`, `session-trade-opportunities`,
  `session-task-events`, `session-map`, `session-chat-history`,
  `session-ships`, `session-ship-definitions`, `session-corporation`,
  `session-quest-status`, `session-assign-quest`, `session-claim-reward`,
  `session-claim-all-rewards`, `session-cancel-task`,
  `session-skip-tutorial`, `session-user-text`, `session-trade-order`,
  `session-player-task`, `session-purchase-ship`, and `session-watch`
  follow the frontend's real message -> event pattern and are preferred over hand-written
  `session-message` payloads.
- `session-claim-all-rewards` is a headless convenience wrapper that batches
  currently claimable quest rewards. It is built on the real
  `claim-step-reward` session action and is not counted as a separate website
  parity surface.
- `session-corp-task` is a headless convenience wrapper for live corp-ship
  tasking. It uses regular player text, then waits on real `task.start` and
  `task.finish` events for the named corporation ship.
- `session-corp-explore-loop` is the preferred exploration grinder. It builds
  the proven probe-frontier objective, watches real corp-ship task events, and
  accepts observed sector/map progress even when one lifecycle event is late.
- `session-player-task` does the same for the personal ship. It is the
  preferred surface for short deterministic bot-driven objectives like
  single-route trade loops or move-and-sell steps.
- `session-move-to-sector` is the preferred exact movement wrapper when you
  want a deterministic relocate-and-stop action without writing freeform task text.
- `session-corp-move-to-sector` is the preferred corp-ship movement wrapper
  for long rescue/logistics legs because live corp tasks often make partial
  progress before stopping.
- `session-recharge-warp`, `session-transfer-credits`, and
  `session-transfer-warp` are first-class wrappers around regular-player
  logistics prompts that were proven live.
- `session-trade-route-loop` is the preferred surface for repeatable personal
  trade grinding. It uses bounded watched tasks rather than one broad
  freeform objective, retries transient step failures, and now places exact
  frontend-style trade orders when live price/quantity data is available.
- `session-nearest-mega-port` is the preferred recharge-planning helper. It
  uses the live session map graph and returns real shortest paths to known
  mega-ports.
- `session-trade-opportunities` is the preferred decision surface before
  picking a route. It reads current ship state plus the known-port graph and
  ranks visible routes by raw profit, profit per hop, and trade volume per hop.
  It now uses the session map graph for real shortest-path distances instead of
  estimating inter-port distance from hop deltas alone, and it now respects
  port `B`/`S` directionality plus live buy-side stock so invalid routes do
  not get promoted just because the posted prices look attractive.
- `session-auto-trade-loop` is the preferred execution surface once a goal is
  clear. It uses `session-trade-opportunities` internally, picks the current
  best visible route for `wealth`, `trading`, or raw `profit`, then runs the
  deterministic trade loop on that route.
- the route loop now also refuses invalid buy/sell ports before prompting, so
  bad routes stop early instead of silently stalling on impossible trades.
- the exact trade-order surface is strongest once the ship is already on a
  valid port for that commodity. In live play, exact orders worked reliably at
  valid `BBB` buyers after the ranker stopped sending the ship to illegal `SSS`
  sell targets.
- session commands now also harden auth for long-running play:
  if `/start` returns `401` on the default credential path, the client logs in
  again once and retries the connect automatically.
- `session-trade-order`, `session-purchase-ship`, and
  `session-purchase-corp-ship` send the exact strings the upstream React
  client builds in `TradePanel.tsx` and `ShipDetails.tsx`.
- `session-collect-unowned-ship` sends the exact string the upstream React
  client builds in `SectorUnownedSubPanel.tsx`.
- `loop` is the supported path for bot-driven gameplay. It polls
  `status.snapshot`, tracks quest state, and reprompts on idle instead of
  relying on one-off shell snippets.
- `.env` values are used automatically for login/session defaults, so the
  shortest commands can omit repeated credentials.
- repo-root `.env` is authoritative for `GB_*` values. This avoids stale
  inherited shell credentials shadowing freshly synced tokens.
- `auth-sync` is the shortest way to populate runtime auth state in `.env`:
  it logs in, writes `GB_ACCESS_TOKEN` and `GB_REFRESH_TOKEN`, and writes
  `GB_CHARACTER_ID` when it can select a character by configured name or
  by a single-character account.
- if you explicitly pass `--access-token`, the client respects it and will not
  silently replace it on failure; the auto-relogin path only applies to the
  default credential flow.
- `confirm-url` accepts the raw Supabase verify URL, HTML-escaped links copied from the email body, or a redirecting link that eventually lands on it.
- `game-call` auto-injects `character_id` and `actor_character_id` when configured.
- `events-since` can batch `character_ids`, `ship_ids`, and `corp_id`, and can follow the stream with polling.
- the default `daily` transport is browser-backed official Daily through
  Playwright Chromium. It follows the website bootstrap path exactly and is the
  only public mode proven end-to-end against production.
- `rawdaily` is the old raw Node Daily path and is now diagnostic only.
- `smallwebrtc` still uses the official frontend
  `@pipecat-ai/small-webrtc-transport` in pure Node, but remains diagnostic.
- `session-connect`, `session-request`, `session-message`, `session-send-text`,
  and all named session commands use the same bridge machinery from the
  `gb-headless` CLI.
- `session-watch` is the fastest way to inspect raw bridge events after connect and after one optional client message.
- the preferred order is: direct edge-function method, then direct session message.
- browser-driven gameplay is intentionally not part of the supported client surface in this repo.
- the live `daily` path is now proven to reach `bot_ready` and receive gameplay
  frames such as `status.snapshot`, `quest.status`, `map.local`, `ports.list`,
  `chat.history`, `ships.list`, and `ship.definitions`.
- the remaining blocker is no longer transport reachability. The current work
  is surface-by-surface: make task-driven actions wait on real lifecycle
  events, and document where exact website prompts still degrade when driven
  headlessly.
- the live player path is now proven through both checked-in tutorial quest
  lines, including corporation creation, corporation ship purchase, and a real
  corporation-ship task completion.
- the exact website unowned-ship prompt is implemented, but in current live
  testing it routes to `salvage_collect` and fails with `404 Salvage not
  available` even when `status.snapshot` reports unowned ships in sector `472`.
- `signup-and-start` is the proven public bootstrap flow:
  `register -> confirm -> login -> user_character_create -> user_character_list -> start`.
- `signup-and-start` is a practical two-pass CLI flow:
  first run without `--verify-url` to register, then rerun with the email link to finish.
