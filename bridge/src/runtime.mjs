import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const wrtc = require("@roamhq/wrtc");

const NODE_USER_AGENT = `gradient-bang-headless-bridge/${process.versions.node}`;

export function installNodeWebRtcGlobals() {
  const {
    MediaStream,
    MediaStreamTrack,
    RTCDataChannel,
    RTCIceCandidate,
    RTCPeerConnection,
    RTCPeerConnectionIceEvent,
    RTCSessionDescription,
    mediaDevices,
  } = wrtc;

  const navigatorValue = globalThis.navigator ?? {};

  if (!navigatorValue.userAgent) {
    navigatorValue.userAgent = NODE_USER_AGENT;
  }
  if (!navigatorValue.mediaDevices) {
    navigatorValue.mediaDevices = mediaDevices;
  }
  if (!navigatorValue.permissions) {
    navigatorValue.permissions = {
      query: async () => ({ state: "denied" }),
    };
  }

  defineGlobal("navigator", navigatorValue);
  defineGlobal("window", globalThis);
  defineGlobal("self", globalThis);

  if (!globalThis.MediaStream) {
    defineGlobal("MediaStream", MediaStream);
  }
  if (!globalThis.MediaStreamTrack) {
    defineGlobal("MediaStreamTrack", MediaStreamTrack);
  }
  if (!globalThis.RTCDataChannel) {
    defineGlobal("RTCDataChannel", RTCDataChannel);
  }
  if (!globalThis.RTCIceCandidate) {
    defineGlobal("RTCIceCandidate", RTCIceCandidate);
  }
  if (!globalThis.RTCPeerConnection) {
    defineGlobal("RTCPeerConnection", RTCPeerConnection);
  }
  if (!globalThis.RTCPeerConnectionIceEvent) {
    defineGlobal("RTCPeerConnectionIceEvent", RTCPeerConnectionIceEvent);
  }
  if (!globalThis.RTCSessionDescription) {
    defineGlobal("RTCSessionDescription", RTCSessionDescription);
  }
}

function defineGlobal(name, value) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
}
