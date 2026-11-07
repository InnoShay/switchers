// Synthesized Web Audio effects (SPEC §16.3). No audio files. Unlocked on first key/click; M mutes.
export class Sfx {
  constructor() {
    this.ctx = null;
    this.muted = false;
  }

  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  }

  toggleMute() {
    this.muted = !this.muted;
    return this.muted;
  }

  get ok() {
    return this.ctx && this.ctx.state === "running" && !this.muted;
  }

  _tone(freq, t0, dur, { type = "sine", gain = 0.12, to = null } = {}) {
    const c = this.ctx;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(c.destination);
    o.start(t0);
    o.stop(t0 + dur + 0.05);
  }

  _noise(t0, dur, { filter = "bandpass", f0 = 2000, f1 = null, gain = 0.15 } = {}) {
    const c = this.ctx;
    const buf = c.createBuffer(1, Math.max(1, Math.floor(c.sampleRate * dur)), c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = c.createBufferSource();
    src.buffer = buf;
    const f = c.createBiquadFilter();
    f.type = filter;
    f.frequency.setValueAtTime(f0, t0);
    if (f1) f.frequency.exponentialRampToValueAtTime(f1, t0 + dur);
    const g = c.createGain();
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f).connect(g).connect(c.destination);
    src.start(t0);
  }

  ignition() {
    if (!this.ok) return;
    this._tone(220, this.ctx.currentTime, 0.6, { to: 880, gain: 0.16 });
  }

  message() {
    if (!this.ok) return;
    const t = this.ctx.currentTime;
    this._tone(660, t, 0.08, { gain: 0.07 });
    this._tone(880, t + 0.09, 0.1, { gain: 0.07 });
  }

  approval() {
    if (!this.ok) return;
    const t = this.ctx.currentTime;
    this._tone(110, t, 0.22, { gain: 0.2 });
    this._tone(110, t + 0.32, 0.22, { gain: 0.2 });
  }

  shutter() {
    if (!this.ok) return;
    this._noise(this.ctx.currentTime, 0.08, { filter: "bandpass", f0: 3500, gain: 0.25 });
  }

  whoosh() {
    if (!this.ok) return;
    this._noise(this.ctx.currentTime, 0.9, { filter: "lowpass", f0: 200, f1: 4000, gain: 0.3 });
    this._tone(90, this.ctx.currentTime, 0.9, { gain: 0.1 });
  }
}
