# Bridge Runtimes

This package now contains two headless runtimes:

- a pure Node `smallwebrtc` bridge for direct Pipecat transport work
- a hosted-browser runner for the live `game.gradient-bang.com` client

## SmallWebRTC Bridge

The `smallwebrtc` bridge is a text-first Node runtime for the production
Pipecat transport.

It intentionally skips microphone and camera capture by using a no-op media
manager. That keeps the direct transport path focused on:

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

## Hosted Browser Runner

The hosted-browser runner uses Playwright and Chromium to drive the real live
client at `https://game.gradient-bang.com/`.

Run it with:

```bash
npm run browser
```

Supported JSON commands:

```json
{"id":"1","op":"connect","email":"you@example.com","password":"...","characterName":"Pilot"}
{"id":"2","op":"status"}
{"id":"3","op":"sendCommand","text":"skip tutorial"}
{"id":"4","op":"clickButton","label":"Skip Tutorial"}
{"id":"5","op":"close"}
```

Current status:

- production login works
- character selection works
- the hosted client reaches real in-game state
- `connect` now returns a game-shell snapshot even when the command box is
  still disabled during intro/tutorial narration
