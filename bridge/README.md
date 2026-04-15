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

Two bridge modes are supported:

- `daily`: the existing raw Node transport around `createDailyRoom=true`
- `smallwebrtc`: the official frontend `@pipecat-ai/small-webrtc-transport`
  with a no-op media manager

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
{"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","sessionId":"...","transport":"daily"}
```

## Current Status

- The bridge process, JSON protocol, and Node WebRTC runtime are working.
- The bridge now uses the same high-level bootstrap shape as the website client:
  `PipecatClient.startBotAndConnect()`.
- Production validation reaches transport `ready` in pure Node on the `daily`
  bridge mode.
- The `daily` path is proven to:
  - call `/start`
  - complete `/start/{sessionId}/api/offer`
  - open the datachannel
  - send `client-ready`
  - send semantic client messages such as `start`
- The `daily` path still does not receive `bot_ready` or gameplay frames from
  the live server.
- The `smallwebrtc` bridge mode now uses the same transport package as the
  browser client.
- The public `smallwebrtc` path still hangs at `/start/{sessionId}/api/offer`
  under pure Node, but now fails on explicit bridge timeouts instead of waiting
  forever.
- The bridge now emits structured HTTP and raw datachannel diagnostics so failed
  connects preserve the exact phase boundary in CLI error output.
- Pipecat app-level frames are still blocked: `bot_ready` and semantic server
  events have not yet been observed on the public path.
