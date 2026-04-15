export class NoopMediaManager {
  constructor() {
    this._options = {};
    this._callbacks = {};
    this._micEnabled = false;
    this._camEnabled = false;
    this._sharingScreen = false;
    this._supportsScreenShare = false;
  }

  setUserAudioCallback(_callback) {}

  setClientOptions(options, _override = false) {
    this._options = options ?? {};
    this._callbacks = this._options.callbacks ?? {};
  }

  async initialize() {}

  async connect() {}

  async disconnect() {}

  async userStartedSpeaking() {
    return undefined;
  }

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
  }

  enableCam(enable) {
    this._camEnabled = Boolean(enable);
  }

  enableScreenShare(enable) {
    this._sharingScreen = Boolean(enable);
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

  get supportsScreenShare() {
    return this._supportsScreenShare;
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
}
