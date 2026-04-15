# SmallWebRTC Bridge

This package is a text-first Node bridge for the production Pipecat
`smallwebrtc` transport.

It intentionally skips microphone and camera capture by using a no-op media
manager. That keeps the first headless transport path focused on:

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
- Production validation reaches:
  `start -> /start/{sessionId}/api/offer -> connecting`
- The pure Node transport does not yet reach Pipecat `bot_ready`; use
  `connectTimeoutMs` so callers fail cleanly instead of hanging forever.
