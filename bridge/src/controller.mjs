#!/usr/bin/env node

import { createRequire } from "node:module";
import process from "node:process";
import readline from "node:readline";

import { RawWebRtcTransport } from "./raw_transport.mjs";
import { installNodeWebRtcGlobals } from "./runtime.mjs";

const require = createRequire(import.meta.url);
const { LogLevel, PipecatClient } = require("@pipecat-ai/client-js");

redirectConsoleToStderr();
installNodeWebRtcGlobals();

const HELP_TEXT = `Usage: node src/controller.mjs

Reads newline-delimited JSON commands from stdin and writes newline-delimited
JSON responses/events to stdout.

Supported commands:
  {"id":"1","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","characterId":"...","connectTimeoutMs":20000}
  {"id":"2","op":"connect","functionsUrl":"https://api.gradient-bang.com/functions/v1","accessToken":"...","sessionId":"...","connectTimeoutMs":20000}
  {"id":"3","op":"sendClientMessage","messageType":"start","data":{}}
  {"id":"4","op":"sendClientRequest","messageType":"get-my-status","data":{}}
  {"id":"5","op":"sendText","content":"hello"}
  {"id":"6","op":"disconnectBot"}
  {"id":"7","op":"disconnect"}
  {"id":"8","op":"status"}
  {"id":"9","op":"close"}`;

const LOG_LEVELS = {
  none: LogLevel.NONE,
  error: LogLevel.ERROR,
  warn: LogLevel.WARN,
  info: LogLevel.INFO,
  debug: LogLevel.DEBUG,
};

function normalizeFunctionsUrl(raw) {
  const value = String(raw ?? "").trim().replace(/\/+$/, "");
  if (!value) {
    throw new Error("functionsUrl is required");
  }
  return value;
}

function requireString(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return value;
}

function authHeaders(accessToken) {
  return new Headers({
    Authorization: `Bearer ${requireString(accessToken, "accessToken")}`,
  });
}

function buildStartRequest(command) {
  const body = {
    character_id: requireString(command.characterId, "characterId"),
    bypass_tutorial: Boolean(command.bypassTutorial),
  };

  if (typeof command.voiceId === "string" && command.voiceId) {
    body.voice_id = command.voiceId;
  }
  if (typeof command.personalityTone === "string" && command.personalityTone) {
    body.personality_tone = command.personalityTone;
  }
  if (typeof command.characterName === "string" && command.characterName) {
    body.character_name = command.characterName;
  }

  return {
    endpoint: `${normalizeFunctionsUrl(command.functionsUrl)}/start`,
    headers: authHeaders(command.accessToken),
    timeout: typeof command.requestTimeoutMs === "number" ? command.requestTimeoutMs : undefined,
    requestData: {
      createDailyRoom: true,
      dailyRoomProperties: {
        start_video_off: true,
        eject_at_room_exp: true,
      },
      body,
    },
  };
}

function serialize(value) {
  if (value === undefined) {
    return null;
  }
  return JSON.parse(
    JSON.stringify(value, (_key, current) => {
      if (current instanceof Error) {
        return {
          name: current.name,
          message: current.message,
          stack: current.stack,
        };
      }
      return current;
    }),
  );
}

function serializeError(error) {
  if (error instanceof Error) {
    return serialize({
      name: error.name,
      message: error.message,
      stack: error.stack,
    });
  }
  return { message: String(error) };
}

function writeMessage(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function redirectConsoleToStderr() {
  for (const level of ["log", "info", "warn", "error", "debug"]) {
    console[level] = (...args) => {
      process.stderr.write(`${args.map(formatConsoleArg).join(" ")}\n`);
    };
  }
}

function formatConsoleArg(value) {
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function emitEvent(event, payload = {}) {
  writeMessage({
    type: "event",
    event,
    ...serialize(payload),
  });
}

function withTimeout(promise, timeoutMs, label) {
  if (!(timeoutMs > 0)) {
    return promise;
  }
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error(`${label} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
    }),
  ]);
}

class SmallWebRtcBridge {
  constructor() {
    this.client = null;
    this.accessToken = null;
    this.logLevel = LogLevel.INFO;
  }

  _buildClient(functionsUrl) {
    const client = new PipecatClient({
      transport: new RawWebRtcTransport({
        functionsUrl,
        accessToken: this.accessToken,
      }),
      enableMic: false,
      enableCam: false,
      callbacks: {
        onConnected: () => emitEvent("connected"),
        onDisconnected: () => emitEvent("disconnected"),
        onTransportStateChanged: (state) => emitEvent("transport_state_changed", { state }),
        onBotStarted: (response) => emitEvent("bot_started", { response }),
        onBotReady: (data) => emitEvent("bot_ready", { data }),
        onBotDisconnected: (participant) =>
          emitEvent("bot_disconnected", { participant: serialize(participant) }),
        onServerMessage: (data) => emitEvent("server_message", { data: serialize(data) }),
        onMessageError: (message) => emitEvent("message_error", { message: serialize(message) }),
        onError: (message) => emitEvent("error", { message: serialize(message) }),
        onUserTranscript: (data) => emitEvent("user_transcript", { data }),
        onBotOutput: (data) => emitEvent("bot_output", { data }),
        onBotLlmText: (data) => emitEvent("bot_llm_text", { data }),
        onBotTtsText: (data) => emitEvent("bot_tts_text", { data }),
        onLLMFunctionCallStarted: (data) =>
          emitEvent("llm_function_call_started", { data }),
        onLLMFunctionCallInProgress: (data) =>
          emitEvent("llm_function_call_in_progress", { data }),
        onLLMFunctionCallStopped: (data) =>
          emitEvent("llm_function_call_stopped", { data }),
      },
    });

    client.setLogLevel(this.logLevel);
    return client;
  }

  async _replaceClient(functionsUrl) {
    if (this.client) {
      try {
        await this.client.disconnect();
      } catch (error) {
        emitEvent("bridge_warning", {
          message: "disconnect before reconnect failed",
          error: serializeError(error),
        });
      }
    }
    this.client = this._buildClient(functionsUrl);
    return this.client;
  }

  async connect(command) {
    const functionsUrl = normalizeFunctionsUrl(command.functionsUrl);
    this.accessToken = requireString(command.accessToken, "accessToken");
    const client = await this._replaceClient(functionsUrl);
    const connectTimeoutMs =
      typeof command.connectTimeoutMs === "number" ? command.connectTimeoutMs : 20000;

    try {
      if (command.sessionId) {
        const connectPromise = client.connect({
            sessionId: requireString(command.sessionId, "sessionId"),
            requestTimeoutMs:
              typeof command.requestTimeoutMs === "number"
                ? command.requestTimeoutMs
                : undefined,
          });
        const ready = await this._awaitConnectReady(client, connectPromise, connectTimeoutMs);
        return {
          mode: "session",
          ready: serialize(ready),
        };
      }

      const started = await withTimeout(
        client.startBot(buildStartRequest(command)),
        connectTimeoutMs,
        "start",
      );
      const ready = await withTimeout(
        this._awaitConnectReady(
          client,
          client.connect({
          ...started,
          requestTimeoutMs:
            typeof command.requestTimeoutMs === "number"
              ? command.requestTimeoutMs
              : undefined,
          }),
          connectTimeoutMs,
        ),
        connectTimeoutMs + 1000,
        "connect",
      );
      return {
        mode: "start",
        started: serialize(started),
        ready: serialize(ready),
      };
    } catch (error) {
      try {
        await client.disconnect();
      } catch (disconnectError) {
        emitEvent("bridge_warning", {
          message: "disconnect after connect failure failed",
          error: serializeError(disconnectError),
        });
      }
      throw error;
    }
  }

  async _awaitConnectReady(client, connectPromise, connectTimeoutMs) {
    try {
      return await Promise.race([
        withTimeout(connectPromise, connectTimeoutMs, "connect"),
        waitForClientState(client, "ready", connectTimeoutMs).then(() => ({
          bot_ready_timeout: true,
          transport_state: client.state,
        })),
      ]);
    } catch (error) {
      if (client.state === "ready") {
        emitEvent("bridge_warning", {
          message: "bot_ready did not arrive before timeout; continuing with ready transport",
          error: serializeError(error),
        });
        return {
          bot_ready_timeout: true,
          transport_state: client.state,
        };
      }
      throw error;
    }
  }

  async sendClientMessage(command) {
    this._requireClient();
    this.client.sendClientMessage(
      requireString(command.messageType, "messageType"),
      command.data ?? {},
    );
    return { sent: true };
  }

  async sendClientRequest(command) {
    this._requireClient();
    const result = await this.client.sendClientRequest(
      requireString(command.messageType, "messageType"),
      command.data ?? {},
      typeof command.timeoutMs === "number" ? command.timeoutMs : undefined,
    );
    return serialize(result);
  }

  async sendText(command) {
    this._requireClient();
    await this.client.sendText(requireString(command.content, "content"), command.options ?? {});
    return { sent: true };
  }

  async disconnectBot() {
    this._requireClient();
    this.client.disconnectBot();
    return { sent: true };
  }

  async disconnect() {
    if (!this.client) {
      return { disconnected: false };
    }
    await this.client.disconnect();
    return { disconnected: true };
  }

  async status() {
    return {
      hasClient: Boolean(this.client),
      connected: Boolean(this.client?.connected),
      state: this.client?.state ?? "disconnected",
    };
  }

  async setLogLevel(command) {
    const rawLevel = String(command.level ?? "").toLowerCase();
    if (!(rawLevel in LOG_LEVELS)) {
      throw new Error(`unsupported log level ${rawLevel}`);
    }
    this.logLevel = LOG_LEVELS[rawLevel];
    if (this.client) {
      this.client.setLogLevel(this.logLevel);
    }
    return { level: rawLevel };
  }

  _requireClient() {
    if (!this.client) {
      throw new Error("bridge is not connected");
    }
  }

  async close() {
    await this.disconnect();
    return { closed: true };
  }
}

async function waitForClientState(client, expectedState, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (client.state === expectedState) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`state ${expectedState} not reached before timeout`);
}

async function main(argv) {
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(`${HELP_TEXT}\n`);
    return 0;
  }

  const bridge = new SmallWebRtcBridge();
  emitEvent("bridge_ready", {
    protocol_version: 1,
    transport: "webrtc",
  });

  const rl = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

  let pending = Promise.resolve();

  const processCommand = async (line) => {
    const raw = line.trim();
    if (!raw) {
      return;
    }

    let command;
    try {
      command = JSON.parse(raw);
    } catch (error) {
      writeMessage({
        type: "response",
        id: null,
        ok: false,
        error: serializeError(error),
      });
      return;
    }

    const id = command.id ?? null;

    try {
      let result;
      switch (command.op) {
        case "connect":
          result = await bridge.connect(command);
          break;
        case "sendClientMessage":
          result = await bridge.sendClientMessage(command);
          break;
        case "sendClientRequest":
          result = await bridge.sendClientRequest(command);
          break;
        case "sendText":
          result = await bridge.sendText(command);
          break;
        case "disconnectBot":
          result = await bridge.disconnectBot();
          break;
        case "disconnect":
          result = await bridge.disconnect();
          break;
        case "status":
          result = await bridge.status();
          break;
        case "setLogLevel":
          result = await bridge.setLogLevel(command);
          break;
        case "close":
          result = await bridge.close();
          writeMessage({ type: "response", id, ok: true, result });
          process.exit(0);
          return;
        default:
          throw new Error(`unsupported op ${String(command.op)}`);
      }

      writeMessage({
        type: "response",
        id,
        ok: true,
        result,
      });
    } catch (error) {
      writeMessage({
        type: "response",
        id,
        ok: false,
        error: serializeError(error),
      });
    }
  };

  rl.on("line", (line) => {
    pending = pending.then(() => processCommand(line)).catch((error) => {
      emitEvent("bridge_warning", {
        message: "unexpected line handler failure",
        error: serializeError(error),
      });
    });
  });

  rl.on("close", () => {
    pending = pending.finally(async () => {
      try {
        await bridge.close();
      } catch (error) {
        emitEvent("bridge_warning", {
          message: "close on stdin shutdown failed",
          error: serializeError(error),
        });
      }
    });
  });

  process.on("SIGINT", async () => {
    await bridge.close();
    process.exit(130);
  });

  process.on("SIGTERM", async () => {
    await bridge.close();
    process.exit(143);
  });

  return 0;
}

main(process.argv.slice(2)).catch((error) => {
  writeMessage({
    type: "fatal",
    error: serializeError(error),
  });
  process.exit(1);
});
