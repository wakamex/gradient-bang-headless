# Headless Client Plan

This file tracks the execution plan for pushing the Gradient Bang headless
client as far into live gameplay as possible.

The intent is not just to scaffold code, but to keep a running record of:

- what the client can do now,
- what has been proven against production,
- what the next feature commit is,
- what is currently blocked,
- and what fallback path to take when a transport or API path stalls.

## Local Vs Live Constraint

There are two different targets, and they should not be conflated:

- live production gameplay
- a fully local stack

Current proven constraint:

- running transport or bot code locally does not, by itself, unlock live gameplay
- if the bot still talks to the live production Supabase edge functions, protected gameplay requires a trusted `X-API-Token`
- the upstream bot path uses `AsyncGameClient` in Supabase mode, and that client expects a trusted gameplay token for protected calls

Implication:

- a plain local session-control API is useful, but only in one of these two cases:
  - it is deployed on the live service we do not control
  - or it is used against a fully local stack that we do control

Fallback decision rule:

- if trusted live gameplay credentials are available, keep pushing the live character
- if they are not available, the clean path is to run a fully local stack and use the headless client against that stack instead of pretending local transport work alone will cross the live auth boundary

## Goal

Reach the deepest playable headless path available from the public production
surface at `https://api.gradient-bang.com/functions/v1`, while committing each
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

These are not the public path for a player-distributed headless client.

### Session Transport

In progress:

- raw WebRTC bridge process in Node
- JSON-lines bridge protocol
- Node WebRTC globals via `@roamhq/wrtc`
- official `smallwebrtc` bridge mode via the frontend transport package
- Python wrapper for the bridge process
- CLI session commands for bridge-driven connect/request/message/text flows
- CLI raw event watching through `session-watch`
- production path reaches:
  `start -> /start/{sessionId}/api/offer -> ready`

Not yet proven:

- Pipecat `bot_ready`
- transport-level command exchange after WebRTC connect

Latest narrowing:

- `start` succeeds live
- the raw Node bridge reaches transport `ready`
- `start --transport smallwebrtc` returns a real `sessionId` plus `iceConfig`
- official pure-Node `smallwebrtc` still hangs on `/api/offer`
- `createDailyRoom=true` sessions answer `/api/offer` and open a datachannel
- Pipecat app-level frames are still missing on the public path
- `session-watch` confirms that even explicit `start` messages currently produce no server events

### Current Live State

Latest live read from `user_character_list`:

- character: `gbheadless19873`
- ship: `sparrow_scout`
- sector: `1413`
- ship credits: `12,865`
- cargo: `retro_organics=20`
- fighters: `200`
- warp power: `386`

That confirms the live character still exists and can be inspected through the
public JWT surface, but gameplay progression remains blocked on the public
session transport rather than account/bootstrap state.

## Endpoint Coverage

Canonical source of truth: [upstream/API.md](/code/gradient/upstream/API.md)

- total documented edge-function endpoints: `60`
- first-class canonical endpoints currently covered in the headless client: `20`
- direct first-class coverage: about `33%`

Covered today:

- public control plane:
  - `register`
  - `login`
  - `user_character_list`
  - `user_character_create`
  - `start`
  - `leaderboard_resources`
- trusted gameplay edge functions:
  - `my_status`
  - `move`
  - `plot_course`
  - `local_map_region`
  - `list_known_ports`
  - `trade`
  - `recharge_warp_power`
  - `purchase_fighters`
  - `ship_definitions`
  - `ship_purchase`
  - `quest_assign`
  - `quest_status`
  - `quest_claim_reward`
  - `events_since`

Covered indirectly, but not counted in the `20`:

- generic raw edge-function calls through `call` and `game-call`
- session-semantic commands such as `session-start`, `session-status`,
  `session-known-ports`, `session-map`, `session-assign-quest`,
  `session-claim-reward`, `session-cancel-task`, `session-skip-tutorial`,
  and `session-user-text`
- Supabase verify-link confirmation through `confirm-url`

Interpretation:

- the headless client already covers the public bootstrap path cleanly
- it also covers a small but useful slice of protected gameplay RPCs
- the biggest remaining gap is not scaffolding, but access: most gameplay
  endpoints still require trusted `X-API-Token` auth or a working public
  session transport

## Planned Commit Sequence

### 1. Plan And Feature Ledger

Commit scope:

- add this file
- document what is proven, what is blocked, and what comes next

Success condition:

- repo contains a concrete execution plan and feature ledger

### 2. First-Class Edge Gameplay Methods

Commit scope:

- replace generic protected gameplay calls with named client methods
- expose named CLI commands for the proven edge-function surface
- remove pressure to use browser prompts for actions that already have direct RPCs

Success condition:

- trusted users can call common gameplay endpoints without hand-writing JSON or endpoint names

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

### Local Server Scope Limit

Observed architectural limit:

- a local bot or session server still needs trusted gameplay credentials if it is pointed at the live production edge functions
- therefore local server work does not automatically let the headless client advance a live character on the public site

What local server work can still do:

- remove browser and WebRTC complexity for local testing
- provide a clean HTTP control plane for a fully local stack
- serve as the right long-term interface if a deployable server path ever becomes available

Current next diagnostic:

- identify why the daily-bootstrapped `/api/offer` path opens a datachannel but stays silent
- identify why the official `smallwebrtc` Node path still never gets an offer
  response from `/api/offer`
- determine whether a pure Node Daily transport is practical with additional runtime shims

### Public Gameplay API Access

Most direct gameplay edge functions still require `X-API-Token`.

That means the public player path should continue to prioritize the bot/session
surface over direct edge-function gameplay calls.

## Immediate Next Step

1. replace generic gameplay calls with named edge-function methods and CLI commands
2. keep the supported client surface browser-free
3. keep pushing the pure Node public transport until it emits real Pipecat frames
4. keep pushing the live character forward and record each newly proven capability
