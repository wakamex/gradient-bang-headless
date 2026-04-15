import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { nonstandard } = require("@roamhq/wrtc");

const SAMPLE_RATE = 48000;
const FRAME_COUNT = SAMPLE_RATE / 100;

export class NoopMediaManager {
  constructor() {
    this._callbacks = {};
    this._micEnabled = false;
    this._camEnabled = false;
    this._audioSource = null;
    this._audioTrack = null;
    this._silenceInterval = null;
  }

  setUserAudioCallback(_userAudioCallback) {}

  setClientOptions(options, override = false) {
    if (this._options && !override) {
      return;
    }
    this._options = options;
    this._callbacks = options.callbacks ?? {};
    this._micEnabled = options.enableMic ?? false;
    this._camEnabled = options.enableCam ?? false;
  }

  async initialize() {
    if (!this._audioSource) {
      this._audioSource = new nonstandard.RTCAudioSource();
      this._audioTrack = this._audioSource.createTrack();
      this._audioTrack.enabled = this._micEnabled;
    }
  }

  async connect() {
    await this.initialize();
    if (this._silenceInterval) {
      return;
    }
    const data = {
      samples: new Int16Array(FRAME_COUNT),
      sampleRate: SAMPLE_RATE,
      bitsPerSample: 16,
      channelCount: 1,
      numberOfFrames: FRAME_COUNT,
    };
    this._silenceInterval = setInterval(() => {
      this._audioSource.onData(data);
    }, 10);
  }

  async disconnect() {
    if (this._silenceInterval) {
      clearInterval(this._silenceInterval);
      this._silenceInterval = null;
    }
    if (this._audioTrack) {
      this._audioTrack.stop();
      this._audioTrack = null;
      this._audioSource = null;
    }
  }

  async userStartedSpeaking() {}

  bufferBotAudio(_data, _id) {
    return undefined;
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

  async updateMic(_micId) {}

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
    if (this._audioTrack) {
      this._audioTrack.enabled = this._micEnabled;
    }
  }

  enableCam(enable) {
    this._camEnabled = Boolean(enable);
  }

  enableScreenShare(_enable) {}

  get isCamEnabled() {
    return this._camEnabled;
  }

  get isMicEnabled() {
    return this._micEnabled;
  }

  get isSharingScreen() {
    return false;
  }

  tracks() {
    return {
      local: {
        audio: this._audioTrack ?? undefined,
      },
      bot: {},
    };
  }

  get supportsScreenShare() {
    return false;
  }
}
