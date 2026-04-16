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
6. Keep the current leaderboard climb strategy explicit:
   - exploration through repeated `session-corp-explore-loop` frontier runs
   - trading through the best visible route from `session-auto-trade-loop --goal trading`
   - wealth through the best visible route from `session-auto-trade-loop --goal wealth` plus existing corp assets
   - medium-term capital target: a better personal trading ship, with extra corp probes as the next exploration multiplier at the next megaport stop
   - short-term operational constraint: the personal ship is now warp-limited, so exploration is the cheapest current lever until the ship reaches a recharge path again

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
- first-class personal-ship tasking with real `task.start`/`task.finish`
  watching through `session-player-task`
- first-class corp-ship tasking with real `task.start`/`task.finish` watching
- a first-class `session-corp-explore-loop` for repeated probe frontier runs
- a first-class `session-trade-opportunities` helper for ranking visible trade routes by profit and travel cost
- map-backed route ranking using the live `session-map` graph instead of hop-delta approximations
- a first-class `session-auto-trade-loop` that chooses a route by goal and runs it
- sell-recovery cycle accounting so successful trade-order cleanups count as real completed cycles
- first-class logistics helpers for warp recharge and credit transfers
- a deterministic `session-trade-route-loop` built from bounded watched tasks,
  with per-step retries after the first long production run exposed transient
  move failures
- first-class location helpers:
  - `session-move-to-sector` for exact move-and-validate execution
  - `session-nearest-mega-port` for recharge-route discovery from the live map
- player-step validation that now polls live `status.snapshot` instead of
  waiting blindly for every `task.finish`
- route-loop trade steps that now prefer exact frontend trade-order prompts
  when live price and quantity data is available
- port-code-aware trade ranking and route safety checks:
  - trade opportunities now respect `B`/`S` directionality by commodity
  - buy-side stock now caps ranked volume
  - the route loop now refuses invalid buy/sell ports before prompting
- session-connect auth hardening:
  - repo-root `.env` now wins for `GB_*` credentials
  - session commands auto-login and retry once when `/start` returns `401`
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
  - some trade prompts look profitable on price alone but are invalid once the
    port code is checked; the client now blocks that class of mistake, but the
    remaining work is keeping every trading helper aligned with legal `B`/`S`
    directionality
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
- personal ship sector: `3124` (latest observed while a long RO trade loop was still running)
- personal ship credits: `6037`
- personal ship warp power: `431`
- corp ship: `gbheadless Auto Hauler 1` (`autonomous_light_hauler`) stranded in sector `2204` with `0/500` warp
- corp ship: `gbheadless Auto Probe 1` (`autonomous_probe`) stranded in sector `3341` with `0/500` warp
- corp ship: `gbheadless Auto Probe I` (`autonomous_probe`) active in sector `4892` with `485/500` warp
- destroyed corp ship: `gbheadless Auto Probe 20260416-0312`
- cargo: `30` Retro Organics
- fighters: `300`
- known sectors: `313`
- corporation sectors visited: `307`
- `tutorial`: completed
- `tutorial_corporations`: completed
- visible exploration board entry: `313` known sectors, currently observed at rank `39`
- visible trading board entry: `239348` total volume, currently observed at rank `28`
- visible wealth board entry: currently observed at rank `78` with visible row value `39877`

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
- added `leaderboard-self-summary` and corrected it so exploration estimates
  use the real production union behavior instead of the underreported
  personal-only field
- added `session-player-task` as a first-class watched surface for short
  personal-ship objectives
- added first-class `session-recharge-warp` and `session-transfer-credits`
  commands after proving both regular-player logistics flows live
- pushed the corporation probe through a 29-sector exploration run that
  entered the visible exploration board at `54` sectors
- mapped the current best live trade ladder by capital band:
  - low capital: `1908 <-> 3358` Retro Organics shuttle
  - mid capital: `674 -> 907 -> 674` NS/QF cycle
  - higher capital: full-hold `472 -> 3358` Neuro Symbolics run
- proved the economic ladder live and grew the personal ship from `31`
  credits to `1205` credits while staying entirely on the regular-player
  session surface
- repeated the higher-capital full-hold `472 <-> 3358` NS loop three more
  times and grew the ship further to `2015` credits before stopping at the
  configured warp floor
- read the production leaderboard definitions directly and confirmed the real
  optimization split:
  - exploration unions personal and corp map knowledge
  - wealth includes the full corporation fleet
  - trading is personal-only and ranked by 7-day `total_trade_volume`
- promoted the live `3786 -> 1009` Neuro Symbolics run into a first-class
  `session-trade-route-loop` after the older freeform trade ladder degraded
- validated the route loop live, then hardened it with per-step retries when
  the first long run completed `9` cycles and stopped on one failed move
- pushed the corporation probe through two more post-tutorial exploration runs:
  - `10` new sectors to sector `4633`
  - `15` new sectors to sector `446`
- used the route loop for two more production pushes:
  - `9` completed cycles to `4177` credits
  - `6` retried cycles to `4807` credits
  - `2` more cycles to `4987` credits
- reached visible-board entry in all three regular-player leaderboard
  categories using only the headless public/session path:
  - exploration rank `77`
  - trading rank `49`
  - wealth rank `92`
- traced the live `/start` `401` issue to stale inherited env winning over
  repo `.env`, then fixed the client so `GB_*` values from `.env` are
  authoritative and session connects auto-login/retry once on `401`
- verified the auth hardening by resuming default-path session commands without
  manual token injection
- added `session-corp-explore-loop`, then hardened it twice:
  - first by fixing corp-ship matching through the `server_message` wrapper
  - then by accepting observed ship/map progress when a probe task advanced
    successfully without a timely `task.finish`
- used that loop for three live frontier pushes:
  - `2864 -> 2071 -> 852`
  - `852 -> 72`
  - `72 -> 2554`
- turned those probe runs into real leaderboard movement:
  - exploration rank `67 -> 54 -> 48 -> 46`
  - known sectors `105 -> 147 -> 167 -> 189`
- hardened `session-trade-route-loop` so player-step validation now polls live
  `status.snapshot` instead of waiting blindly for every `task.finish`
- switched the route loop to exact frontend trade-order prompts when live
  port-price data is available
- proved the stronger trading contract directly:
  - an exact `SELL 9 Neuro Symbolics @ 40` order moved the Kestrel from sector
    `1009` to sector `3246`
  - it sold the full remainder at `45` with a real `task.finish`
- added `session-trade-opportunities` to rank the current known-port graph by:
  - raw profit
  - profit per hop
  - trade volume per hop
- upgraded `session-trade-opportunities` to use the live map graph for real
  shortest-path distances between ports
- added `session-auto-trade-loop` so route choice can be goal-driven instead
  of manually transcribed
- used that helper to split the live trading strategy by leaderboard goal:
  - best raw profit from the visible graph: `3236 -> 907` Neuro Symbolics
  - best current wealth route after graph correction: `3786 -> 3236` Quantum Foam
  - best current trading-volume route after graph correction: `3236 -> 318` Neuro Symbolics
- proved the new goal-driven surface live:
  - `session-auto-trade-loop --goal wealth --max-cycles 2` selected `3786 -> 3236`
    Quantum Foam and pushed wealth rank `84 -> 83`
  - `session-auto-trade-loop --goal trading --max-cycles 2` selected
    `3236 -> 318` Neuro Symbolics and exposed the remaining sell edge case
- hardened the route loop again by adding a final exact trade-order sell
  recovery step when the loop would otherwise stop with a loaded hold
- used that recovery path live to unwind the stuck NS hold and improve cash
  plus visible trading volume instead of leaving the ship dirty
- fixed the loop accounting so a recovered sell now counts as a completed cycle
- revalidated `session-auto-trade-loop --goal wealth` live after that fix:
  - one clean counted cycle on `3786 -> 3236` Quantum Foam
  - wealth rank `83 -> 79`
  - trading volume `204638 -> 208658`
- pushed exploration further with two more probe runs:
  - `2554 -> 1399`
  - `1399 -> 2695`
- plus one more run after the transport retry:
  - `2695 -> 3792`
- plus two more later frontier runs:
  - `3792 -> 699`
  - and another run whose loop result and later standalone `ships.list` read
    disagreed on final sector, reinforcing that post-task probe location is
    still eventually consistent across surfaces
- added `session-nearest-mega-port` and `session-move-to-sector` so recharge
  routing and exact relocation are first-class instead of ad hoc
- used `session-nearest-mega-port` live from sector `3236` and confirmed the
  nearest known megaport remains sector `472`, `9` hops away
- found and fixed the most important remaining trade bug:
  - the route ranker had been ignoring port `B`/`S` directionality and buy-side stock
  - this made `3236 -> 318` Neuro Symbolics look profitable even though `318`
    is `SSS` and cannot buy NS from the player
- hardened the trade helpers after that discovery:
  - `session-trade-opportunities` now ranks only legal routes
  - `session-trade-route-loop` now stops on invalid buy/sell ports before issuing prompts
- used the corrected market view to recover the live dirty hold:
  - moved `318 -> 3246`
  - sold `30` Neuro Symbolics at a valid `BBB` buyer for `1290` credits
- re-ranked the corrected local graph from sector `3246`:
  - best wealth route: `318 -> 3246` Quantum Foam
  - best trading-volume route: `318 -> 3246` Neuro Symbolics
  - best raw-profit route still visible: `3236 -> 907` Neuro Symbolics
- proved the corrected wealth route live with one full `318 -> 3246` QF cycle:
  - credits `6979 -> 7129`
  - warp `17 -> 11`
  - profit `+150`
- pushed exploration again immediately after the trade correction:
  - known sectors `285 -> 295`
  - corporation sectors visited `279 -> 289`
  - the visible exploration rank improved `39 -> 37`
- current confirmed live board state:
  - exploration rank `37`
  - trading rank `29`
  - wealth rank `79`
- added and proved bidirectional warp-transfer surfaces:
  - `session-corp-transfer-warp` moved `200` warp from the hauler to the Kestrel
  - `session-transfer-warp` moved `100` warp from the Kestrel back to the hauler
- added `leaderboard-neighbors` so the next visible gaps are explicit in one command instead of inferred from raw leaderboard dumps
- read the live wealth view closely enough to confirm a flat cargo valuation rule:
  - every cargo unit counts as `100` credits on the wealth board
  - so cheap cargo is the strongest wealth lever, not expensive cargo
- added `session-corp-move-to-sector` after live corp moves kept making partial progress that `session-corp-task` did not summarize clearly
- used that new helper live and got a clean rescue-path diagnosis:
  - hauler moved `1413 -> 3139 -> 2204`
  - then stranded with `0/500` warp before reaching the probe in sector `3341`
- repeated `session-move-to-sector --sector-id 2204` also exposed a remaining player-side gap:
  - the helper timed out, but the Kestrel still advanced `3246 -> 3094 -> 1333 -> 867`
  - so long player moves still need the same kind of progressive wrapper that now exists for corp ships
- used the exact `session-trade-order` sell surface to clear a dirty `30`-unit NS hold at sector `3246`
  - sold `30` units at `43` for `1,290` credits
  - pushed visible trading to rank `28`
- hardened `session-move-to-sector` into a segmented mover with status retry recovery, then used it live to get the Kestrel back to mega-port sector `1413`
- recharged at `1413` to full and used forced leaderboard refreshes to validate the wealth exploit against live data:
  - `30` Retro Organics at `8` credits each pushed visible wealth `79 -> 71`
  - live wealth promotion depends on forcing a fresh leaderboard rebuild, not reading cached rows
- fixed `session-collect-unowned-ship` so it includes sector context and can infer the current sector automatically
- retested that surface live and narrowed the remaining failure:
  - the prompt contract is now correct
  - live collection still fails because the bot falls back to `salvage_collect` and gets `404 'Salvage not available'`
- read live `ship.definitions` from the session path and confirmed a better exploration lever:
  - fresh `Autonomous Probe` purchase price is only `1000`
  - this is materially better than spending the Kestrel on a long warp rescue first
- bought a new corp probe, `gbheadless Auto Probe I`, at sector `1413`
- sent that new probe on a frontier task and proved immediate exploration progress:
  - known sectors `309 -> 313`
  - corp sectors visited `303 -> 307`
  - latest observed probe sector `4892`
  - next visible exploration row is now only `2` sectors away
- re-ranked trading from the new `1413` hub:
  - best raw profit: `Quantum Foam` `1413 -> 2891`
  - best trading volume per hop: `Retro Organics` `1413 -> 3124`
- launched a long RO route loop on `1413 <-> 3124` and confirmed it is productive but still too opaque in large batches:
  - trading volume `233468 -> 239348`
  - personal trades `239 -> 260`
  - the loop still did not return a prompt bounded final result cleanly enough to count as a dependable unattended surface

Interpretation:

- the live player path is working
- the next bottleneck is no longer tutorial progression
- the next highest-value client hardening is no longer basic movement
- player movement is now good enough to relocate deliberately back to a mega-port
- the next weak surfaces are:
  - long corp-task watching, because exploration progress can continue after the bounded wrapper gives up
  - large trade-route batches, because they are productive but too opaque to trust as a clean unattended loop
- the remaining work is expanding reliable post-tutorial surfaces and
  documenting which website actions still degrade when driven headlessly
- the next concrete live-game push is now:
  - keep using fresh `1000`-credit probes from a mega-port when the goal is exploration rank
  - keep using cheap RO holds intentionally when the goal is wealth rank
  - keep the `1413 <-> 3124` RO route as the current best live trading-volume grind
  - harden corp-task watching and large-batch trade looping so the productive live paths are also operationally clean
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
- `session-player-task`
- `session-corp-task`
- `session-move-to-sector`
- `session-nearest-mega-port`
- `session-recharge-warp`
- `session-transfer-credits`
- `session-trade-route-loop`

Not first-class yet:

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
