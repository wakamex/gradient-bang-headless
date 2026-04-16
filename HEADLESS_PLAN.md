# Headless Client Plan

This file tracks the execution plan for pushing the Gradient Bang headless
client as far into live gameplay as possible.

The intent is not just to scaffold code, but to keep a running record of:

- what the client can do now,
- what has been proven against production,
- what the next feature commit is,
- what is currently blocked,
- and what fallback path to take when a transport or API path stalls.

## Active Tasklist

1. Keep browser-backed `daily` as the default live transport and treat
   `rawdaily` and `smallwebrtc` as diagnostics only.
2. Convert every frontend-proven session action into a first-class headless
   command before using it in further discovery.
3. Encode frontend-derived prompt contracts, not ad hoc prose, whenever the
   website itself uses fixed prompt strings.
4. Improve the long-objective loop so it can recover from bot drift and
   distinguish real progress from chatter.
5. Keep extending post-tutorial live-player surfaces from the website:
   corporation growth, unowned-ship collection, salvage, rename, and combat.

## Current Milestones

These are the explicit post-tutorial live-player goals that were set for the
current push. Status is updated against production, not against local mocks.

1. `[x]` Discover and accept any new live contracts visible to a normal player
   after the two checked-in tutorial quest lines.
   Current result: no new normal-player contract was exposed; the live bot now
   consistently reports the tutorial lines as complete and no new contract path
   has surfaced through the regular player UI.
2. `[x]` Grow the corporation past the tutorial floor with at least one more
   ship and a more useful fleet mix than "Kestrel plus two probes".
   Current result: the corporation now has one `autonomous_light_hauler` and
   one active `autonomous_probe`.
3. `[x]` Reach one successful non-tutorial asset-acquisition loop end to end:
   unowned ship collection or salvage collection.
   Current result: salvage collection is proven live; unowned-ship collection
   remains a live mismatch and is now tracked separately as a broken surface.
4. `[x]` Reach first real combat and then first post-combat salvage collection.
   Current result: live combat and live salvage collection are both proven.
5. `[x]` Reach one complete garrison cycle: deploy, inspect/update mode, and
   collect.
6. `[x]` Upgrade the loop runner so it can stop on real post-tutorial business
   goals such as fleet growth instead of only timing out after success.
   Current result: the loop runner now stops successfully on corp-fleet targets
   like `autonomous_light_hauler` count.

## Local Vs Live Constraint

There are two different environments, but only one product target:

- live production player parity
- a fully local stack

Current proven constraint:

- running transport or bot code locally does not, by itself, unlock live gameplay
- if the bot still talks to the live production Supabase edge functions, secret-backed gameplay requires credentials a regular player does not have
- the upstream bot path uses `AsyncGameClient` in Supabase mode, and that client expects a trusted gameplay token for protected calls

Implication:

- a plain local session-control API is useful, but only in one of these two cases:
  - it is deployed on the live service we do not control
  - or it is used against a fully local stack that we do control
- for this repo, the second case is diagnostic only; it is not the success condition

Scope rule:

- the headless client is only useful if it improves access to the live game using the same capabilities available to a normal website player
- local-only features are out of scope unless they reduce uncertainty or implementation risk for the live path
- when local work is proposed, it should be framed as a diagnostic harness for the live target, not as an alternate product goal
- secret-backed production endpoints are not a success path for the shipped client, even if they are useful for reverse-mapping server behavior

## Goal

Reach the deepest playable headless path available to a normal website player
from the public production surface at
`https://api.gradient-bang.com/functions/v1`, while committing each
incremental capability along the way.

## Proven Production Surface

These flows have already been proven live:

- `register`
- email confirmation through Supabase verify URLs
- `login`
- `auth-sync`
- `user_character_create`
- `user_character_list`
- `start`

That means the public control plane is real and usable today.

## Current Capability Map

### Control Plane

Implemented and production-proven:

- account registration
- email verification URL resolution
- login
- `.env` runtime auth sync through `auth-sync`
- character creation
- character visibility polling
- session creation through `/start`
- public leaderboard reads through `leaderboard_resources`

### Protected Edge Functions

Implemented for trusted use only:

- generic gameplay function calls with `X-API-Token`
- `events_since` polling

These are diagnostic tools for understanding the backend. They are not the
target product surface for a player-distributed headless client.

### Session Transport

Implemented:

- browser-backed official Daily bridge via Playwright Chromium
- raw WebRTC bridge process in Node
- JSON-lines bridge protocol
- Node WebRTC globals via `@roamhq/wrtc`
- official `smallwebrtc` bridge mode via the frontend transport package
- Python wrapper for the bridge process
- CLI session commands for bridge-driven connect/request/message/text flows
- CLI raw event watching through `session-watch`
- first-class session commands for status, ports, map, chat history, ships,
  ship definitions, corporation data, task events, and quest status
- exact frontend prompt contracts for trade orders and ship purchase requests
- first-class corp-ship tasking with real `task.start`/`task.finish` watching
- exact frontend prompt contract for collecting an unowned ship in the sector
- a reusable `loop` runner for long bot-driven objectives

Production-proven on `daily`:

- `/start`
- `bot_ready`
- `status.snapshot`
- `quest.status`
- `ports.list`
- `map.local` and `map.region`
- `chat.history`
- `ships.list`
- `ship.definitions`
- semantic client messages such as `start`, `get-my-status`,
  `get-known-ports`, `assign-quest`, `claim-step-reward`, and `user-text-input`

Diagnostic-only today:

- `rawdaily`: useful for comparing browser-backed Daily against raw Node Daily
- `smallwebrtc`: still stalls at `/start/{sessionId}/api/offer` in pure Node

Current blocker:

- the live player path is healthy through bootstrap, tutorials, corp setup,
  corp ship purchase, corp ship tasking, garrison work, combat, and salvage
- the next blockers are surface-specific:
  - some bot-driven actions still need task-aware waiting, not fire-and-close prompts
  - the exact unowned-ship collect prompt currently routes to `salvage_collect`
    and fails with `404 Salvage not available` even when `status.snapshot`
    reports `unowned_ships` in the current sector
  - `corporation.data` can lag behind `ships.list` after a successful
    corporation-ship task, so post-task verification should prefer `ships.list`
    when sector freshness matters

### Current Live State

Latest live state observed through the session surface:

- character: `gbheadless6039`
- corporation: `gbheadless6039 corp`
- personal ship: `gbheadless Kestrel` (`kestrel_courier`)
- personal ship sector: `472`
- personal ship credits: `31`
- corp ship: `gbheadless Auto Hauler 1` (`autonomous_light_hauler`) in sector `472`
- corp ship: `gbheadless Auto Probe 1` (`autonomous_probe`) in sector `692`
- destroyed corp ship: `gbheadless Auto Probe 20260416-0312`
- cargo: empty
- fighters: `300`
- warp power: `290`
- `tutorial`: completed
- `tutorial_corporations`: completed

Latest live progression proved:

- created a fresh live account and completed the public bootstrap flow
- completed the full starter tutorial and claimed all rewards
- bought the first personal `Kestrel Courier`
- proved a repeatable personal-ship NS trade route between sectors `472` and
  `3358`
- fixed player-task waiting so trade and purchase prompts bind to the correct
  `task.start`/`task.finish` pair
- accepted and completed the corporation tutorial contract
- created a live corporation and purchased the first corporation probe
- sent a first-class corp task to `gbheadless Auto Probe 1 [eab4cd]`
- observed real `task.start` and `task.finish` for the corp probe
- claimed the final corporation tutorial reward
- collected live salvage through a first-class headless command
- engaged live combat and submitted a real `combat-action`
- completed a full live garrison cycle: deploy, update, collect
- purchased a first non-probe corporation ship, `gbheadless Auto Hauler 1`
- proved the loop runner can stop on a real corp-fleet target
- sent a first-class corp task to `gbheadless Auto Probe 1 [eab4cd]` and moved
  it onward to sector `692`
- verified that `ships.list` reflected the new probe sector immediately after
  task finish, while `corporation.data` lagged
- implemented the exact frontend unowned-ship prompt surface and reproduced a
  current live failure mode against real unowned-ship IDs at sector `472`

Interpretation:

- the live player path is working
- the next bottleneck is no longer tutorial progression
- the remaining work is expanding reliable post-tutorial surfaces and
  documenting which website actions still degrade when driven headlessly
- the next concrete live-game push is now:
  - fund and task the new auto hauler
  - keep probing for new live contract surfaces through exploration and the
    regular player session
  - either make unowned-ship collection work or document it as a live bot/path
    bug with clear reproduction

## User-Facing Surface Tracking

Source of truth for this section:

- the website frontend in `upstream/client/app/src`
- the public bootstrap/session path used by a normal player
- exact prompt contracts that the website itself sends through `user-text-input`

This tracker is intentionally different from the full edge-function count in
[upstream/API.md](/code/gradient/upstream/API.md). We care about regular-player
website parity, not direct coverage of every server endpoint.

Current first-class regular-player coverage:

- tracked user-facing surfaces: `35`
- first-class implemented in this client: `29`
- coverage: about `83%`

### Public Bootstrap And Control Plane (`7/7`)

- `[x]` account registration
- `[x]` email confirmation flow
- `[x]` login
- `[x]` character list
- `[x]` character creation
- `[x]` start session via `/start`
- `[x]` leaderboard resources read

### Frontend Semantic Session Actions (`13/19`)

Implemented:

- `[x]` `start`
- `[x]` `get-my-status`
- `[x]` `get-known-ports`
- `[x]` `get-task-history`
- `[x]` `get-my-map`
- `[x]` `get-my-ships`
- `[x]` `get-my-corporation`
- `[x]` `get-ship-definitions`
- `[x]` `cancel-task`
- `[x]` `get-chat-history`
- `[x]` `assign-quest`
- `[x]` `claim-step-reward`
- `[x]` `combat-action`

Headless convenience wrappers, not counted separately:

- `session-claim-all-rewards`

Not first-class yet:

- `[ ]` `combat-action`
- `[ ]` `say-text`
- `[ ]` `say-text-dismiss`
- `[ ]` `dump-llm-context`
- `[ ]` `dump-task-context`
- `[ ]` `set-voice`
- `[ ]` `set-personality`

### Frontend Prompt-Driven Surfaces (`9/9`)

Implemented:

- `[x]` freeform `user-text-input`
- `[x]` trade order prompt contract from `TradePanel.tsx`
- `[x]` personal ship purchase prompt contract from `ShipDetails.tsx`
- `[x]` corporation ship purchase prompt contract from `ShipDetails.tsx`
- `[x]` collect unowned ship prompt contract from `SectorUnownedSubPanel.tsx`
- `[x]` engage combat with named player
- `[x]` garrison update prompt contract
- `[x]` collect salvage prompt contract
- `[x]` rename ship prompt contract

Interpretation:

- the public bootstrap flow is fully covered
- the typed session surface is mostly covered
- the biggest remaining gap is not prompt coverage anymore; it is the set of
  live prompt paths that still degrade or misroute in production, such as
  unowned-ship collection
- generic `session-user-text` can still reach more of the live game than the
  first-class count shows, but it is not counted as durable surface coverage
  unless the website contract has been written into the client

## Auth-Protected Edge Endpoints

These are tracked separately because the shipped client will not implement them
as direct edge-function surfaces. They remain useful for reverse-mapping server
behavior, but they are out of scope for normal-player parity.

When a regular-player equivalent exists, the correct shipped target is:

- public JWT/bootstrap flow
- direct session message
- exact frontend prompt contract

### App-Token Endpoints (`46`, out of scope as direct client targets)

Core gameplay lifecycle and reads:

- `join`
- `my_status`
- `move`
- `character_info`
- `ship_definitions`
- `list_user_ships`
- `local_map_region`
- `plot_course`
- `path_with_region`
- `list_known_ports`
- `events_since`
- `event_query`

Corporation:

- `corporation_list`
- `corporation_info`
- `my_corporation`
- `corporation_create`
- `corporation_join`
- `corporation_leave`
- `corporation_kick`
- `corporation_rename`
- `corporation_regenerate_invite_code`

Economy, ships, salvage, messaging:

- `trade`
- `transfer_credits`
- `transfer_warp_power`
- `bank_transfer`
- `recharge_warp_power`
- `purchase_fighters`
- `dump_cargo`
- `salvage_collect`
- `ship_purchase`
- `ship_sell`
- `ship_rename`
- `send_message`

Combat and garrison:

- `combat_initiate`
- `combat_action`
- `combat_tick`
- `combat_leave_fighters`
- `combat_collect_fighters`
- `combat_disband_garrison`
- `combat_set_garrison_mode`

Quests and tasks:

- `quest_assign`
- `quest_status`
- `quest_claim_reward`
- `task_lifecycle`
- `task_cancel`

Test / local utility:

- `test_reset`

### Admin-Secret Endpoints (`5`, out of scope)

- `character_create`
- `character_modify`
- `character_delete`
- `regenerate_ports`
- `reset_ports`

## Planned Commit Sequence

### 1. Plan And Feature Ledger

Commit scope:

- add this file
- document what is proven, what is blocked, and what comes next

Success condition:

- repo contains a concrete execution plan and feature ledger

### 2. First-Class Edge Gameplay Methods

Commit scope:

- replace generic gameplay calls with named client methods where that improves
  tracing, diagnostics, or player-surface parity
- expose named CLI commands for the proven public and diagnostic edge-function
  surface without making trusted-token paths part of the product goal
- remove pressure to use browser prompts for actions that already have direct
  semantic paths

Success condition:

- the repo can reason about gameplay operations without hand-writing JSON or
  endpoint names, while keeping the shipped client biased toward the public
  player path

### 3. Semantic Session Actions

Commit scope:

- add first-class commands for typed session messages and requests
- focus on frontend-proven actions such as:
  - `start`
  - `get-my-status`
  - `get-known-ports`
  - `get-task-history`
  - `get-my-map`
  - `assign-quest`
  - `claim-step-reward`
  - `cancel-task`
  - `skip-tutorial`
  - `user-text-input`

Success condition:

- session-mediated gameplay is reachable from CLI/Python without browser UI gestures

### 4. Node Transport Investigation

Commit scope:

- keep pushing pure Node public WebRTC transport
- instrument `api/offer` behavior
- tighten timeout and failure reporting around the offer phase
- compare request shape against the successful browser transport when needed

Success condition:

- either reach `bot_ready`, or reduce the remaining gap to one concrete incompatibility

### 5. Progression Loop

Commit scope:

- use the strongest available headless path to keep advancing the live character
- write down each proven capability in docs as it lands
- commit each incremental feature before using it to go further

Success condition:

- the repo keeps moving deeper into real gameplay even when one transport path stalls

## Definition Of “As Far As Possible”

For this repo, “as far as possible” means:

1. bootstrap a real user and character
2. create a real bot/session
3. connect transport
4. exchange real client messages
5. retrieve live in-game state
6. submit live in-game actions that the session path allows
7. maintain session continuity long enough to complete multi-step objectives

If a phase is blocked, the next commit should improve one of:

- reachability,
- observability,
- ergonomics,
- or fallback execution path.

## Current Blockers

### Pure Node Public Session Stall

Observed production behavior:

- `start` succeeds
- `createDailyRoom=false` sessions return `sessionId` + `iceConfig`, but pure
  Node still hangs at `/start/{sessionId}/api/offer`
- `createDailyRoom=true` sessions reach transport `ready`
- `bot_ready` and gameplay server events still do not arrive on the public path

Current mitigation:

- bridge-level `connectTimeoutMs`
- bridge-level `requestTimeoutMs`
- transport-ready fallback when `bot_ready` does not arrive

### Local Diagnostics Scope Limit

Observed architectural limit:

- a local bot or session server still needs trusted gameplay credentials if it is pointed at the live production edge functions
- therefore local server work does not automatically let the headless client advance a live character on the public site

What local server work can still do:

- remove browser and WebRTC complexity while reproducing live failures locally
- provide a controlled harness for comparing live and local protocol behavior
- serve as a staging surface for features that would also help if a deployable live-compatible path is found

Current next diagnostic:

- identify why the daily-bootstrapped `/api/offer` path opens a datachannel,
  sends `client-ready`, and still stays silent
- identify why the official `smallwebrtc` Node path posts a fully populated
  offer and still never gets an answer from `/api/offer`
- compare the proven raw `daily` offer/handshake against the browser-facing
  `smallwebrtc` offer/handshake at the server expectation level

### Public Gameplay API Access

Most direct gameplay edge functions still require secret-backed auth.

That means the public player path should continue to prioritize the bot/session
surface over direct edge-function gameplay calls.

## Immediate Next Step

1. keep the supported client surface browser-free
2. keep pushing the pure Node public transport until it emits real Pipecat frames
3. prioritize anything the website itself can do with public player credentials
4. use local tooling and secret-backed traces only when they directly help explain or unblock the live production player path
5. keep pushing the live character forward and record each newly proven capability
