# Bridge Runtimes

This package contains the session transport runtimes used by the headless
client for direct Pipecat work.

## Transport Modes

Three transport modes are currently supported:

- `daily`: browser-backed official Daily transport via Playwright Chromium.
  This is the live player path and the default mode.
- `rawdaily`: the old raw Node Daily transport using Node WebRTC shims.
  This is kept for diagnostics only.
- `smallwebrtc`: the pure Node SmallWebRTC path via the official frontend
  package. This is also diagnostic only today.

All three stay text-first and avoid microphone/camera capture as a gameplay
dependency. The shipped client is biased toward semantic session messages and
frontend-derived prompt contracts, not audio I/O.

The raw Node modes still need WebRTC primitives, so they install
`@roamhq/wrtc` and map those globals into Node before creating the Pipecat
client.

## Setup

```bash
cd bridge
npm install
```

## Run

```bash
npm run bridge
```

The process reads newline-delimited JSON commands from `stdin` and writes
newline-delimited JSON responses/events to `stdout`.

Example session:

```json
{"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","characterId":"...","transport":"daily","bypassTutorial":true,"connectTimeoutMs":8000,"requestTimeoutMs":8000}
{"id":"2","op":"sendClientMessage","messageType":"start","data":{}}
{"id":"3","op":"sendClientRequest","messageType":"get-my-status","data":{}}
{"id":"4","op":"sendClientMessage","messageType":"user-text-input","data":{"text":"plot a safe course"}}
{"id":"5","op":"disconnect"}
{"id":"6","op":"close"}
```

The bridge also supports direct reconnect by existing bot session:

```json
{"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","sessionId":"...","transport":"rawdaily"}
```

## Current Status

- The bridge process, JSON protocol, and browser runtime are working.
- The default `daily` mode now follows the website bootstrap path exactly with
  `PipecatClient.startBotAndConnect()`.
- Production validation on `daily` is proven to:
  - call `/start`
  - reach `bot_ready`
  - receive gameplay frames such as `status.snapshot`, `quest.status`,
    `ports.list`, `map.local`, `chat.history`, `ships.list`,
    and `ship.definitions`
  - send semantic client messages such as `start`, `get-my-status`,
    `assign-quest`, and `user-text-input`
- The remaining problem on `daily` is not connectivity; it is higher-level
  control quality on long bot-driven objectives.
- `rawdaily` still demonstrates the raw Node Daily behavior, but it remains a
  diagnostic path rather than the shipped player path.
- `smallwebrtc` still hangs at `/start/{sessionId}/api/offer` in pure Node and
  is kept for diagnostics.
- The bridge emits structured HTTP, browser-console, and runtime diagnostics so
  failed connects preserve the exact phase boundary in CLI error output.
