# Headless Client Plan

This file tracks the execution plan for pushing the Gradient Bang headless
client as far into live gameplay as possible.

The intent is not just to scaffold code, but to keep a running record of:

- what the client can do now,
- what has been proven against production,
- what the next feature commit is,
- what is currently blocked,
- and what fallback path to take when a transport or API path stalls.

## Goal

Reach the deepest playable headless path available from the public production
surface at `https://api.gradient-bang.com/functions/v1`, while committing each
incremental capability along the way.

## Proven Production Surface

These flows have already been proven live:

- `register`
- email confirmation through Supabase verify URLs
- `login`
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
- character creation
- character visibility polling
- session creation through `/start`

### Protected Edge Functions

Implemented for trusted use only:

- generic gameplay function calls with `X-API-Token`
- `events_since` polling

These are not the public path for a player-distributed headless client.

### Session Transport

In progress:

- `smallwebrtc` bridge process in Node
- JSON-lines bridge protocol
- Node WebRTC globals via `@roamhq/wrtc`
- Python wrapper for the bridge process
- CLI session commands for bridge-driven connect/request/message/text flows
- production path reaches:
  `start -> /start/{sessionId}/api/offer -> connecting`

Not yet proven:

- Pipecat `bot_ready`
- transport-level command exchange after WebRTC connect

Latest narrowing:

- `start` succeeds live
- the Node bridge receives a real `sessionId` and ICE config
- the pure Node path hangs specifically on `POST /start/{sessionId}/api/offer`
- browser-hosted production traffic is using Daily websocket signaling, not the pure Node path

### Hosted Browser Runtime

Proven live against production:

- headless Chromium can load `https://game.gradient-bang.com/`
- UI login works with a real account
- character selection works through the hosted client
- the live hosted client reaches in-game state and Pipecat `bot_ready`
- the command input is present in the rendered game shell
- live command submission through the hosted client works

Reclassification after audit:

- browser login and character selection remain acceptable bootstrap steps
- browser command typing and DOM button clicking are now fallback-only tooling
- the real target is semantic transport injection:
  - direct edge-function calls when possible
  - direct Pipecat/RTVI messages when gameplay is session-mediated
  - browser UI only when no backend or transport path exists yet

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

### 4. Semantic Browser Transport Fallback

Commit scope:

- keep the browser only as a transport host for production
- inject typed RTVI messages into the live transport instead of clicking UI
- capture typed responses/events for request/response flows

Success condition:

- the hosted client can be driven by semantic actions without DOM clicks or prompt text

### 5. Node Transport Investigation

Commit scope:

- keep pushing pure Node `smallwebrtc`
- instrument `api/offer` behavior
- tighten timeout and failure reporting around the offer phase
- compare request shape against the successful browser transport when needed

Success condition:

- either reach `bot_ready`, or reduce the remaining gap to one concrete incompatibility

### 6. Progression Loop

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

### Pure Node `smallwebrtc` Stall

Observed production behavior:

- `start` succeeds
- `/start/{sessionId}/api/offer` request is issued
- transport reaches `connecting`
- `bot_ready` never arrives under the pure Node path

Current mitigation:

- bridge-level `connectTimeoutMs`
- bridge-level `requestTimeoutMs`
- clean disconnect on timeout

Current next diagnostic:

- compare the pure Node `api/offer` request shape with the successful browser-hosted production session
- prefer semantic browser transport injection over UI clicks while the Node gap remains unresolved

### Public Gameplay API Access

Most direct gameplay edge functions still require `X-API-Token`.

That means the public player path should continue to prioritize the bot/session
surface over direct edge-function gameplay calls.

## Immediate Next Step

1. replace generic gameplay calls with named edge-function methods and CLI commands
2. replace browser UI actions with typed session actions wherever the frontend proves them
3. use browser runtime only as a semantic transport fallback while Node `api/offer` is unresolved
4. keep pushing the live character forward and record each newly proven capability
