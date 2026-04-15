import { LogLevel, PipecatClient } from "@pipecat-ai/client-js";
import { DailyTransport } from "@pipecat-ai/daily-transport";

const LOG_LEVELS = {
  none: LogLevel.NONE,
  error: LogLevel.ERROR,
  warn: LogLevel.WARN,
  info: LogLevel.INFO,
  debug: LogLevel.DEBUG,
};

let client = null;
let logLevel = LogLevel.INFO;
let lastBotStarted = null;

installFetchDiagnostics();

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
    return serialize(error);
  }
  return { message: String(error) };
}

function emit(event, payload = {}) {
  const binding = globalThis.__gradientBridgeEmit;
  if (typeof binding !== "function") {
    return;
  }
  void binding({
    event,
    ...serialize(payload),
  });
}

function installFetchDiagnostics() {
  const originalFetch = globalThis.fetch?.bind(globalThis);
  if (typeof originalFetch !== "function") {
    return;
  }
  if (globalThis.__gradientBrowserFetchWrapped) {
    return;
  }

  globalThis.fetch = async (input, init) => {
    const url = resolveFetchUrl(input);
    const method = resolveFetchMethod(input, init);
    const shouldTrace = typeof url === "string" && url.includes("/functions/v1/start");
    const startedAt = Date.now();

    if (shouldTrace) {
      emit("http_request_started", {
        method,
        url,
        body: await summarizeRequestBody(input, init),
      });
    }

    try {
      const response = await originalFetch(input, init);
      if (shouldTrace) {
        emit("http_request_completed", {
          method,
          url,
          status: response.status,
          ok: response.ok,
          duration_ms: Date.now() - startedAt,
          body: await summarizeResponseBody(response),
        });
      }
      return response;
    } catch (error) {
      if (shouldTrace) {
        emit("http_request_failed", {
          method,
          url,
          duration_ms: Date.now() - startedAt,
          error: serializeError(error),
        });
      }
      throw error;
    }
  };
  globalThis.__gradientBrowserFetchWrapped = true;
}

function resolveFetchUrl(input) {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  if (typeof Request !== "undefined" && input instanceof Request) {
    return input.url;
  }
  return null;
}

function resolveFetchMethod(input, init) {
  if (init?.method) {
    return String(init.method).toUpperCase();
  }
  if (typeof Request !== "undefined" && input instanceof Request && input.method) {
    return String(input.method).toUpperCase();
  }
  return "GET";
}

async function summarizeRequestBody(input, init) {
  if (typeof init?.body === "string") {
    return summarizeBodyText(init.body);
  }
  if (typeof Request !== "undefined" && input instanceof Request) {
    try {
      return summarizeBodyText(await input.clone().text());
    } catch {
      return null;
    }
  }
  return null;
}

async function summarizeResponseBody(response) {
  try {
    return summarizeBodyText(await response.clone().text());
  } catch {
    return null;
  }
}

function summarizeBodyText(text) {
  if (typeof text !== "string" || !text.trim()) {
    return null;
  }
  try {
    return summarizeJsonPayload(JSON.parse(text));
  } catch {
    return {
      text_length: text.length,
    };
  }
}

function summarizeJsonPayload(value) {
  if (!value || typeof value !== "object") {
    return { type: typeof value };
  }

  const summary = {
    keys: Object.keys(value).sort(),
  };

  if (typeof value.type === "string") {
    summary.type = value.type;
  }
  if (typeof value.sessionId === "string") {
    summary.sessionId = value.sessionId;
  }
  if (typeof value.dailyRoom === "string") {
    summary.dailyRoom = true;
  }
  if (typeof value.dailyToken === "string") {
    summary.dailyToken = true;
  }

  return summary;
}

function waitForClientState(expectedState, timeoutMs) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();

    const tick = () => {
      if (client?.state === expectedState) {
        resolve();
        return;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        reject(new Error(`state ${expectedState} not reached before timeout`));
        return;
      }
      setTimeout(tick, 100);
    };

    tick();
  });
}

async function awaitConnectReady(connectPromise, connectTimeoutMs) {
  try {
    return await Promise.race([
      withTimeout(connectPromise, connectTimeoutMs, "connect"),
      waitForClientState("ready", connectTimeoutMs).then(() => ({
        bot_ready_timeout: true,
        transport_state: client?.state ?? "disconnected",
      })),
    ]);
  } catch (error) {
    if (client?.state === "ready") {
      emit("bridge_warning", {
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

async function replaceClient() {
  if (client) {
    try {
      await client.disconnect();
    } catch (error) {
      emit("bridge_warning", {
        message: "disconnect before reconnect failed",
        error: serializeError(error),
      });
    }
  }

  lastBotStarted = null;
  client = new PipecatClient({
    transport: new DailyTransport(),
    callbacks: {
      onConnected: () => emit("connected"),
      onDisconnected: () => emit("disconnected"),
      onTransportStateChanged: (state) => emit("transport_state_changed", { state }),
      onBotStarted: (response) => {
        lastBotStarted = response;
        emit("bot_started", { response });
      },
      onBotReady: (data) => emit("bot_ready", { data }),
      onBotDisconnected: (participant) =>
        emit("bot_disconnected", { participant: serialize(participant) }),
      onServerMessage: (data) => emit("server_message", { data: serialize(data) }),
      onMessageError: (message) => emit("message_error", { message: serialize(message) }),
      onError: (message) => emit("error", { message: serialize(message) }),
      onUserTranscript: (data) => emit("user_transcript", { data }),
      onBotOutput: (data) => emit("bot_output", { data }),
      onBotLlmText: (data) => emit("bot_llm_text", { data }),
      onBotTtsText: (data) => emit("bot_tts_text", { data }),
      onLLMFunctionCallStarted: (data) => emit("llm_function_call_started", { data }),
      onLLMFunctionCallInProgress: (data) => emit("llm_function_call_in_progress", { data }),
      onLLMFunctionCallStopped: (data) => emit("llm_function_call_stopped", { data }),
    },
  });
  client.setLogLevel(logLevel);
  return client;
}

const runtime = {
  async connect(command) {
    if (command.sessionId) {
      throw new Error("daily browser bridge does not support reconnect by sessionId");
    }

    const activeClient = await replaceClient();
    const connectTimeoutMs =
      typeof command.connectTimeoutMs === "number" ? command.connectTimeoutMs : 20000;
    const startRequest = {
      ...command.startRequest,
      headers: new Headers(command.startRequest?.headers ?? {}),
    };
    const ready = await withTimeout(
      awaitConnectReady(activeClient.startBotAndConnect(startRequest), connectTimeoutMs),
      connectTimeoutMs + 1000,
      "connect",
    );

    return {
      mode: "start",
      transport: "daily",
      started: serialize(lastBotStarted),
      ready: serialize(ready),
    };
  },

  async sendClientMessage(command) {
    requireClient();
    client.sendClientMessage(command.messageType, command.data ?? {});
    return { sent: true };
  },

  async sendClientRequest(command) {
    requireClient();
    const result = await client.sendClientRequest(
      command.messageType,
      command.data ?? {},
      typeof command.timeoutMs === "number" ? command.timeoutMs : undefined,
    );
    return serialize(result);
  },

  async sendText(command) {
    requireClient();
    await client.sendText(command.content, command.options ?? {});
    return { sent: true };
  },

  async disconnectBot() {
    requireClient();
    client.disconnectBot();
    return { sent: true };
  },

  async disconnect() {
    if (!client) {
      return { disconnected: false };
    }
    await client.disconnect();
    return { disconnected: true };
  },

  async status() {
    return {
      hasClient: Boolean(client),
      connected: Boolean(client?.connected),
      state: client?.state ?? "disconnected",
      transport: "daily",
    };
  },

  async setLogLevel(command) {
    const rawLevel = String(command.level ?? "").toLowerCase();
    if (!(rawLevel in LOG_LEVELS)) {
      throw new Error(`unsupported log level ${rawLevel}`);
    }
    logLevel = LOG_LEVELS[rawLevel];
    if (client) {
      client.setLogLevel(logLevel);
    }
    return { level: rawLevel };
  },

  async close() {
    if (client) {
      try {
        await client.disconnect();
      } catch (error) {
        emit("bridge_warning", {
          message: "disconnect during close failed",
          error: serializeError(error),
        });
      }
    }
    return { closed: true };
  },
};

function requireClient() {
  if (!client) {
    throw new Error("bridge is not connected");
  }
}

globalThis.__gradientHeadlessBridge = runtime;
