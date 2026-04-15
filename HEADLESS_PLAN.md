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

### Hosted Browser Runtime

Proven live against production:

- headless Chromium can load `https://game.gradient-bang.com/`
- UI login works with a real account
- character selection works through the hosted client
- the live hosted client reaches in-game state and Pipecat `bot_ready`
- the command input is present in the rendered game shell
- live command submission through the hosted client works

Still being pushed:

- deterministic tutorial skip behavior
- higher-level gameplay automation on top of the hosted client

Newest proven gameplay capability:

- same-session browser action sequences
- live command chaining inside one hosted session
- travel from sector `4658` to adjacent sector `301`
- completion of the first `TAKING FLIGHT` contract step
- completion of the next tutorial steps through mega-port arrival, refuel, and commodity purchase

Newest runner hardening:

- hosted-browser connect now distinguishes initial shell paint from actual interactive readiness
- command submission now targets the enabled command field instead of the first input on the page
- button clicks now fall back to raw DOM text matching when role-based lookup fails

Newest long-task support:

- a watch mode can now keep a session open and poll status while a local task runs
- long-running travel or trading objectives no longer require repeated prompt spam just to observe completion
- failed task plans now stop the watcher immediately instead of waiting out the full timeout

## Planned Commit Sequence

### 1. Plan And Feature Ledger

Commit scope:

- add this file
- document what is proven, what is blocked, and what comes next

Success condition:

- repo contains a concrete execution plan and feature ledger

### 2. Python Bridge Integration

Commit scope:

- add Python wrapper for the `bridge/` process
- add CLI commands to drive bridge operations
- make the bridge usable from the same `gb-headless` entrypoint

Success condition:

- user can start the bridge, connect, send client messages, request status,
  and close it from Python/CLI without hand-writing raw JSON

### 3. Headless Session Actions

Commit scope:

- add first-class actions for RTVI/game control messages:
  - `start`
  - `get-my-status`
  - `get-known-ports`
  - `user-text-input`
  - `skip-tutorial`

Success condition:

- if the transport is connected, these actions are reachable from CLI/Python

### 4. Transport Investigation

Commit scope:

- keep pushing pure Node `smallwebrtc`
- instrument offer/connect phases
- tighten timeouts and error reporting
- test live against production after each meaningful change

Success condition:

- either reach `bot_ready`, or reduce the remaining gap to a single clear issue

### 5. Browser-Hosted Fallback Bridge

Commit scope:

- implement a browser-hosted runner that preserves the same JSON protocol
- drive the live hosted client through login, character selection, and in-game state
- use the browser runtime when pure Node transport stalls

Success condition:

- reach `bot_ready` and begin issuing headless actions through the hosted client

### 6. Same-Session Browser Sequences

Commit scope:

- add a `browser-sequence` CLI action
- allow `command`, `click`, `status`, `wait`, and `screenshot` steps
- keep one hosted browser session alive across the full sequence

Success condition:

- live gameplay can progress across multiple dependent actions without
  reconnecting between them

### 7. Contract Progress Loop

Commit scope:

- add a `browser-contract-loop` CLI action
- repeat the proven advancement prompt inside one hosted browser session
- capture a status snapshot after each iteration

Success condition:

- tutorial or contract progression can be driven for several iterations without
  hand-writing a JSON sequence each time

### 8. Interactive Shell Readiness

Commit scope:

- make hosted-browser connect wait for an enabled command field
- avoid reporting success during `INITIALIZING GAME INSTANCES...`
- make command submission target the actual enabled command field

Success condition:

- browser-driven command loops no longer race the hosted client boot sequence

### 9. Long-Running Task Watch

Commit scope:

- add a `browser-command-watch` CLI action
- send one command, then poll browser status until the local task engine settles
- record intermediate snapshots for inspection

Success condition:

- long contract steps like travel or trading can be observed to completion
  without reissuing the same command every minute

### 10. DOM-Text Button Fallback

Commit scope:

- harden `browser-click` when `getByRole(...button...)` fails
- fall back to matching actual `button` text in the DOM and clicking it directly

Success condition:

- headless automation can drive tab-like controls such as `Contracts` even when
  ARIA-role lookup is unreliable

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

### Public Gameplay API Access

Most direct gameplay edge functions still require `X-API-Token`.

That means the public player path should continue to prioritize the bot/session
surface over direct edge-function gameplay calls.

## Immediate Next Step

Use the contract loop to keep advancing the starter contract line, and only add
more DOM-level or data-extraction features if the assistant stops being able to
complete the next step from text commands alone.
