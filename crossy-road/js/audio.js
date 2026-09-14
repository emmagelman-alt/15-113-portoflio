// audio.js — tiny synthesised sound effects. No files to load, no licences to
// worry about; every sound is a shaped oscillator.

export class Sfx {
  constructor() {
    this.ctx = null;
    this.muted = localStorage.getItem('crossy-muted') === '1';
  }

  // Browsers only allow audio after a user gesture, so the context is created
  // on the first hop rather than at load.
  ensure() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      this.ctx = new Ctx();
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  toggleMute() {
    this.muted = !this.muted;
    localStorage.setItem('crossy-muted', this.muted ? '1' : '0');
    return this.muted;
  }

  tone({ freq, to, dur, type = 'square', gain = 0.08 }) {
    if (this.muted) return;
    const ctx = this.ensure();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const amp = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    if (to) osc.frequency.exponentialRampToValueAtTime(to, ctx.currentTime + dur);
    amp.gain.setValueAtTime(gain, ctx.currentTime);
    amp.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    osc.connect(amp).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + dur);
  }

  hop() { this.tone({ freq: 620, to: 900, dur: 0.08, gain: 0.05 }); }
  bump() { this.tone({ freq: 150, to: 90, dur: 0.08, type: 'sawtooth', gain: 0.05 }); }
  splash() { this.tone({ freq: 400, to: 80, dur: 0.45, type: 'sine', gain: 0.1 }); }
  crash() { this.tone({ freq: 180, to: 50, dur: 0.5, type: 'sawtooth', gain: 0.12 }); }
  screech() { this.tone({ freq: 900, to: 220, dur: 0.6, type: 'sawtooth', gain: 0.08 }); }
  milestone() { this.tone({ freq: 880, to: 1320, dur: 0.16, type: 'triangle', gain: 0.07 }); }
}

export default Sfx;
