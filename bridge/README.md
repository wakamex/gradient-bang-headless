# Bridge Runtimes

This package contains the pure Node WebRTC bridge used by the headless
client for direct Pipecat transport work.

## Node WebRTC Bridge

The bridge is a text-first Node runtime for the production Pipecat transport.

It intentionally skips microphone and camera capture. That keeps the direct
transport path focused on:

- session creation via `POST /start`
- session reconnect via `/start/{sessionId}/api/offer`
- RTVI client messages like `start`, `get-my-status`, and `user-text-input`

It still needs WebRTC primitives, so it installs `@roamhq/wrtc` and maps those
globals into Node before creating the Pipecat client.

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
{"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","characterId":"...","bypassTutorial":true,"connectTimeoutMs":8000,"requestTimeoutMs":8000}
{"id":"2","op":"sendClientMessage","messageType":"start","data":{}}
{"id":"3","op":"sendClientRequest","messageType":"get-my-status","data":{}}
{"id":"4","op":"sendClientMessage","messageType":"user-text-input","data":{"text":"plot a safe course"}}
{"id":"5","op":"disconnect"}
{"id":"6","op":"close"}
```

The bridge also supports direct reconnect by existing bot session:

```json
{"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","sessionId":"..."}
```

## Current Status

- The bridge process, JSON protocol, and Node WebRTC runtime are working.
- Production validation reaches transport `ready` in pure Node.
- The current bootstrap path uses `start(createDailyRoom=true)` and then raw
  `/start/{sessionId}/api/offer`.
- Pipecat app-level frames are still blocked: `bot_ready` and semantic server
  events have not yet been observed on the public path.
