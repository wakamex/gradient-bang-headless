import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
  MessageTooLargeError,
  RTVIMessage,
  Transport,
  logger,
  messageSizeWithinLimit,
} = require("@pipecat-ai/client-js");

const DEFAULT_MAX_MESSAGE_SIZE = 64 * 1024;
const DEFAULT_REQUEST_TIMEOUT_MS = 20_000;
const KEEPALIVE_INTERVAL_MS = 1_000;
const DEFAULT_ICE_SERVERS = [
  {
    urls: ["stun:stun.cloudflare.com:3478"],
  },
];

export class RawWebRtcTransport extends Transport {
  constructor({ functionsUrl, accessToken, emitDiagnostic = null }) {
    super();
    this.functionsUrl = String(functionsUrl ?? "").replace(/\/+$/, "");
    this.accessToken = String(accessToken ?? "");
    this.emitDiagnostic = typeof emitDiagnostic === "function" ? emitDiagnostic : null;
    this._state = "disconnected";
    this._requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS;
    this._iceServers = [...DEFAULT_ICE_SERVERS];
    this._pc = null;
    this._dc = null;
    this._sessionId = null;
    this._botParticipantId = null;
    this._keepAlive = null;
    this._micEnabled = false;
    this._camEnabled = false;
    this._sharingScreen = false;
  }

  initialize(options, messageHandler) {
    this._options = options;
    this._callbacks = options.callbacks ?? {};
    this._onMessage = messageHandler;
    this.state = "disconnected";
    logger.debug("[RTVI Transport] Initialized raw Node transport");
  }

  async initDevices() {
    this.state = "initializing";
    this.state = "initialized";
  }

  _validateConnectionParams(connectParams) {
    if (connectParams == null) {
      return undefined;
    }
    if (typeof connectParams !== "object") {
      throw new Error("Invalid connection parameters");
    }

    const params = connectParams;
    const normalized = {};
    if (typeof params.sessionId === "string" && params.sessionId) {
      normalized.sessionId = params.sessionId;
    } else if (typeof params.session_id === "string" && params.session_id) {
      normalized.sessionId = params.session_id;
    }

    if (params.iceConfig && typeof params.iceConfig === "object") {
      normalized.iceConfig = params.iceConfig;
    } else if (params.ice_config && typeof params.ice_config === "object") {
      normalized.iceConfig = params.ice_config;
    }

    if (params.offerRequestParams && typeof params.offerRequestParams === "object") {
      normalized.offerRequestParams = params.offerRequestParams;
    } else if (params.webrtcRequestParams && typeof params.webrtcRequestParams === "object") {
      normalized.offerRequestParams = params.webrtcRequestParams;
    }

    if (typeof params.requestTimeoutMs === "number" && Number.isFinite(params.requestTimeoutMs)) {
      normalized.requestTimeoutMs = params.requestTimeoutMs;
    }

    if (!normalized.sessionId && !normalized.offerRequestParams) {
      throw new Error("sessionId is required");
    }

    return normalized;
  }

  async _connect(connectParams) {
    this.state = "connecting";
    this._requestTimeoutMs =
      typeof connectParams?.requestTimeoutMs === "number" && connectParams.requestTimeoutMs > 0
        ? connectParams.requestTimeoutMs
        : DEFAULT_REQUEST_TIMEOUT_MS;
    this._iceServers = Array.isArray(connectParams?.iceConfig?.iceServers)
      ? connectParams.iceConfig.iceServers
      : [...DEFAULT_ICE_SERVERS];
    this._sessionId = connectParams?.sessionId ?? this._sessionId;
    this._botParticipantId = this._sessionId;

    try {
      await this._openPeerConnection(connectParams);
      this.state = "connected";
      this._callbacks.onConnected?.();
      this._callbacks.onBotConnected?.(botParticipant(this._botParticipantId));
    } catch (error) {
      this.state = "error";
      await this._cleanupPeerConnection();
      throw error;
    }
  }

  async _disconnect() {
    this.state = "disconnecting";
    await this._cleanupPeerConnection();
    this._sessionId = null;
    this._botParticipantId = null;
    this.state = "disconnected";
    this._callbacks.onDisconnected?.();
  }

  sendReadyMessage() {
    this.state = "ready";
    this.sendMessage(RTVIMessage.clientReady());
  }

  get state() {
    return this._state;
  }

  set state(nextState) {
    if (this._state === nextState) {
      return;
    }
    this._state = nextState;
    this._callbacks?.onTransportStateChanged?.(nextState);
  }

  async getAllMics() {
    return [];
  }

  async getAllCams() {
    return [];
  }

  async getAllSpeakers() {
    return [];
  }

  updateMic(_micId) {}

  updateCam(_camId) {}

  updateSpeaker(_speakerId) {}

  get selectedMic() {
    return {};
  }

  get selectedCam() {
    return {};
  }

  get selectedSpeaker() {
    return {};
  }

  enableMic(enable) {
    this._micEnabled = Boolean(enable);
    this._syncTrackStatus();
  }

  enableCam(enable) {
    this._camEnabled = Boolean(enable);
    this._syncTrackStatus();
  }

  enableScreenShare(enable) {
    this._sharingScreen = Boolean(enable);
    this._syncTrackStatus();
  }

  get isCamEnabled() {
    return this._camEnabled;
  }

  get isMicEnabled() {
    return this._micEnabled;
  }

  get isSharingScreen() {
    return this._sharingScreen;
  }

  sendMessage(message) {
    if (!this._dc || this._dc.readyState !== "open") {
      throw new Error("datachannel is not ready");
    }
    if (!messageSizeWithinLimit(message, this._maxMessageSize ?? DEFAULT_MAX_MESSAGE_SIZE)) {
      throw new MessageTooLargeError(
        `Message data too large. Max size is ${this._maxMessageSize ?? DEFAULT_MAX_MESSAGE_SIZE}`,
      );
    }
    this._emitDiagnostic("raw_send_message", { message });
    this._dc.send(JSON.stringify(message));
  }

  tracks() {
    return {
      local: {
        audio: null,
        video: null,
        screenAudio: null,
        screenVideo: null,
      },
      bot: {
        audio: null,
        video: null,
        screenAudio: null,
        screenVideo: null,
      },
    };
  }

  async _openPeerConnection(connectParams) {
    await this._cleanupPeerConnection();

    this._pc = new RTCPeerConnection({
      iceServers: this._iceServers,
    });
    this._pc.addEventListener("connectionstatechange", () => {
      logger.debug(`[RawWebRTC] connectionState=${this._pc?.connectionState}`);
    });
    this._pc.addEventListener("iceconnectionstatechange", () => {
      logger.debug(`[RawWebRTC] iceConnectionState=${this._pc?.iceConnectionState}`);
    });
    this._pc.addEventListener("signalingstatechange", () => {
      logger.debug(`[RawWebRTC] signalingState=${this._pc?.signalingState}`);
    });

    this._pc.addTransceiver("audio", { direction: "recvonly" });
    this._pc.addTransceiver("video", { direction: "recvonly" });
    this._pc.addTransceiver("video", { direction: "recvonly" });

    this._dc = this._pc.createDataChannel("chat", { ordered: true });
    this._dc.addEventListener("message", (event) => {
      this._handleDataChannelMessage(event.data);
    });
    this._dc.addEventListener("open", () => {
      this._emitDiagnostic("raw_datachannel_open", {});
    });
    this._dc.addEventListener("close", () => {
      logger.debug("[RawWebRTC] datachannel closed");
      this._emitDiagnostic("raw_datachannel_closed", {});
      this._clearKeepAlive();
    });

    const openPromise = new Promise((resolve, reject) => {
      const onOpen = () => {
        cleanup();
        this._maxMessageSize = this._pc?.sctp?.maxMessageSize ?? DEFAULT_MAX_MESSAGE_SIZE;
        this._startKeepAlive();
        this._syncTrackStatus();
        resolve();
      };
      const onError = (event) => {
        cleanup();
        reject(
          new Error(
            event?.error?.message || "datachannel failed before reaching open state",
          ),
        );
      };
      const onStateChange = () => {
        const state = this._pc?.connectionState;
        if (state === "failed" || state === "closed") {
          cleanup();
          reject(new Error(`peer connection entered ${state} before datachannel open`));
        }
      };
      const cleanup = () => {
        this._dc?.removeEventListener("open", onOpen);
        this._dc?.removeEventListener("error", onError);
        this._pc?.removeEventListener("connectionstatechange", onStateChange);
      };

      this._dc.addEventListener("open", onOpen, { once: true });
      this._dc.addEventListener("error", onError, { once: true });
      this._pc.addEventListener("connectionstatechange", onStateChange);
    });

    const offer = await this._pc.createOffer();
    await this._pc.setLocalDescription(offer);
    await waitForInitialIce(this._pc, this._requestTimeoutMs);

    const answer = await this._requestOfferAnswer(
      connectParams,
      this._pc.localDescription ?? offer,
    );
    if (!answer || typeof answer !== "object") {
      throw new Error("offer endpoint returned an invalid answer payload");
    }
    if (typeof answer.pc_id === "string" && answer.pc_id) {
      this._botParticipantId = answer.pc_id;
    }
    await this._pc.setRemoteDescription(answer);
    await withTimeout(openPromise, this._requestTimeoutMs, "datachannel open");
  }

  async _requestOfferAnswer(connectParams, localDescription) {
    const requestInfo = this._resolveOfferRequest(connectParams);
    logger.debug("[RawWebRTC] posting offer");
    const response = await fetchJson(
      requestInfo,
      {
        sdp: localDescription.sdp,
        type: localDescription.type,
      },
      this._requestTimeoutMs,
    );
    logger.debug("[RawWebRTC] received offer answer");
    return response;
  }

  _resolveOfferRequest(connectParams) {
    if (connectParams?.offerRequestParams) {
      return connectParams.offerRequestParams;
    }

    const sessionId = connectParams?.sessionId ?? this._sessionId;
    if (!sessionId) {
      throw new Error("sessionId is required for /api/offer");
    }
    return {
      endpoint: `${this.functionsUrl}/start/${sessionId}/api/offer`,
      headers: this._authHeaders(),
      timeout: this._requestTimeoutMs,
    };
  }

  _authHeaders() {
    if (!this.accessToken) {
      return this.startBotParams?.headers ?? {};
    }
    return {
      Authorization: `Bearer ${this.accessToken}`,
    };
  }

  _syncTrackStatus() {
    this._sendSignallingMessage({ type: "trackStatus", receiver_index: 0, enabled: this._micEnabled });
    this._sendSignallingMessage({ type: "trackStatus", receiver_index: 1, enabled: this._camEnabled });
    this._sendSignallingMessage({
      type: "trackStatus",
      receiver_index: 2,
      enabled: this._sharingScreen,
    });
  }

  _sendSignallingMessage(message) {
    if (!this._dc || this._dc.readyState !== "open") {
      return;
    }
    this._emitDiagnostic("raw_send_signalling", { message });
    this._dc.send(JSON.stringify({ type: "signalling", message }));
  }

  _handleDataChannelMessage(rawMessage) {
    if (typeof rawMessage !== "string") {
      return;
    }

    this._emitDiagnostic("raw_receive_datachannel", { raw: rawMessage });

    if (rawMessage.startsWith("ping:")) {
      return;
    }

    let message;
    try {
      message = JSON.parse(rawMessage);
    } catch (error) {
      logger.warn("[RawWebRTC] failed to parse message", error);
      return;
    }

    if (message?.type === "signalling") {
      this._handleSignallingMessage(message.message);
      return;
    }

    if (message?.label === "rtvi-ai" && typeof this._onMessage === "function") {
      this._emitDiagnostic("raw_receive_rtvi", {
        message: {
          id: message.id,
          type: message.type,
          data: message.data,
        },
      });
      this._onMessage({
        id: message.id,
        type: message.type,
        data: message.data,
      });
    }
  }

  _handleSignallingMessage(message) {
    if (!message || typeof message !== "object") {
      return;
    }
    if (message.type === "peerLeft") {
      this._callbacks.onBotDisconnected?.(botParticipant(this._botParticipantId));
      return;
    }
    if (message.type === "renegotiate") {
      logger.warn("[RawWebRTC] ignoring renegotiate message");
    }
  }

  _startKeepAlive() {
    this._clearKeepAlive();
    this._keepAlive = setInterval(() => {
      if (this._dc?.readyState === "open") {
        this._dc.send(`ping: ${Date.now()}`);
      }
    }, KEEPALIVE_INTERVAL_MS);
  }

  _clearKeepAlive() {
    if (this._keepAlive) {
      clearInterval(this._keepAlive);
      this._keepAlive = null;
    }
  }

  async _cleanupPeerConnection() {
    this._clearKeepAlive();

    if (this._dc) {
      try {
        this._dc.close();
      } catch {}
      this._dc = null;
    }

    if (this._pc) {
      try {
        for (const transceiver of this._pc.getTransceivers()) {
          if (typeof transceiver.stop === "function") {
            transceiver.stop();
          }
        }
        this._pc.close();
      } catch {}
      this._pc = null;
    }
  }

  _emitDiagnostic(event, payload) {
    this.emitDiagnostic?.(event, payload);
  }
}

async function fetchJson(requestInfo, body, defaultTimeoutMs) {
  const request = buildFetchRequest(requestInfo, body, defaultTimeoutMs);
  try {
    const response = await fetch(request.url, request.init);
    if (!response.ok) {
      throw new Error(`offer request failed with status ${response.status}`);
    }
    return response.json();
  } finally {
    request.clearTimeout();
  }
}

function buildFetchRequest(requestInfo, body, defaultTimeoutMs) {
  const timeoutMs =
    typeof requestInfo?.timeout === "number" && requestInfo.timeout > 0
      ? requestInfo.timeout
      : defaultTimeoutMs;
  const controller = new AbortController();
  let timeoutId = null;
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  let endpoint = requestInfo?.endpoint;
  let url;
  let baseInit = {};
  if (endpoint instanceof Request) {
    url = endpoint.url;
    baseInit = {
      method: endpoint.method,
      headers: endpoint.headers,
    };
  } else if (endpoint instanceof URL) {
    url = endpoint.toString();
  } else if (typeof endpoint === "string" && endpoint) {
    url = endpoint;
  } else {
    throw new Error("offer request endpoint is required");
  }

  const headers = new Headers(baseInit.headers ?? requestInfo?.headers ?? {});
  headers.set("Content-Type", "application/json");

  return {
    url,
    init: {
      ...baseInit,
      method: requestInfo?.method ?? baseInit.method ?? "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    },
    clearTimeout() {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    },
  };
}

async function waitForInitialIce(pc, timeoutMs) {
  if (pc.iceGatheringState === "complete") {
    return;
  }

  const waitMs = Math.min(Math.max(timeoutMs, 0), 3_000);
  await withTimeout(
    new Promise((resolve) => {
      const onStateChange = () => {
        if (pc.iceGatheringState === "complete") {
          cleanup();
          resolve();
        }
      };
      const timer = setTimeout(() => {
        cleanup();
        resolve();
      }, waitMs);
      const cleanup = () => {
        clearTimeout(timer);
        pc.removeEventListener("icegatheringstatechange", onStateChange);
      };

      pc.addEventListener("icegatheringstatechange", onStateChange);
    }),
    waitMs + 250,
    "initial ice",
  );
}

async function withTimeout(promise, timeoutMs, label) {
  if (!(timeoutMs > 0)) {
    return promise;
  }
  let timeoutId = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error(`${label} timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

function botParticipant(id) {
  return {
    id: id || "bot",
    local: false,
    name: "bot",
  };
}
