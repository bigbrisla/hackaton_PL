/**
 * Pulse audio: the match rendered as sound for fans who cannot see it.
 * - every touch is a short tick panned to the ball's position (left = home goal, right = away goal);
 *   home and away have different pitches, so possession is audible
 * - a heartbeat whose tempo and weight follow the Chaos Index
 * - a synthesized crowd swell on goals (no recorded audio is used)
 * - narration (Azure Speech via /api/tts, browser speech as fallback) panned to where the moment happened
 */

const VOICE_LANG: Record<string, string> = { en: "en-GB", it: "it-IT", es: "es-ES", ja: "ja-JP", fr: "fr-FR", de: "de-DE", pt: "pt-BR", ar: "ar-SA", ko: "ko-KR" };

export class PulseAudio {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private chaos = 50;
  private heartTimer: number | null = null;
  private speaking = false;
  private queue: { text: string; lang: string; pan: number }[] = [];
  enabledTicks = true;

  get enabled() {
    return this.ctx !== null;
  }

  enable() {
    if (this.ctx) return;
    this.ctx = new AudioContext();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.9;
    this.master.connect(this.ctx.destination);
    this.scheduleHeart();
  }

  disable() {
    if (this.heartTimer) clearTimeout(this.heartTimer);
    this.ctx?.close();
    this.ctx = null;
    this.queue = [];
    speechSynthesis?.cancel();
  }

  private panner(pan: number) {
    const p = this.ctx!.createStereoPanner();
    p.pan.value = Math.max(-1, Math.min(1, pan));
    p.connect(this.master);
    return p;
  }

  /** x in home frame (0..105): home team attacks to the right. */
  tick(x: number, home: boolean, strong = false) {
    if (!this.ctx || !this.enabledTicks) return;
    const t = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = home ? "triangle" : "sine";
    osc.frequency.value = (home ? 880 : 520) * (strong ? 1.5 : 1);
    const vol = (this.speaking ? 0.04 : 0.12) * (strong ? 1.6 : 1);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    osc.connect(g).connect(this.panner(x / 52.5 - 1));
    osc.start(t);
    osc.stop(t + 0.1);
  }

  setChaos(c: number) {
    this.chaos = c;
  }

  private scheduleHeart() {
    if (!this.ctx) return;
    const bpm = 50 + this.chaos * 0.8;
    this.beat();
    this.heartTimer = window.setTimeout(() => this.scheduleHeart(), 60000 / bpm);
  }

  private beat() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    const vol = (this.speaking ? 0.08 : 0.18) + (this.chaos / 100) * 0.25;
    for (const [offset, f] of [[0, 62], [0.16, 52]] as const) {
      const osc = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      osc.frequency.setValueAtTime(f * 1.6, t + offset);
      osc.frequency.exponentialRampToValueAtTime(f, t + offset + 0.08);
      g.gain.setValueAtTime(0, t + offset);
      g.gain.linearRampToValueAtTime(vol, t + offset + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + offset + 0.22);
      osc.connect(g).connect(this.master);
      osc.start(t + offset);
      osc.stop(t + offset + 0.25);
    }
  }

  crowd(pan: number) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime, dur = 3.2;
    const buf = this.ctx.createBuffer(2, this.ctx.sampleRate * dur, this.ctx.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (0.6 + 0.4 * Math.sin(i / 900));
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const bp = this.ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = 900;
    bp.Q.value = 0.6;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.55, t + 0.35);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    src.connect(bp).connect(g).connect(this.panner(pan * 0.6));
    src.start(t);
  }

  say(text: string, lang: string, pan = 0) {
    this.queue.push({ text, lang, pan });
    if (!this.speaking) void this.next();
  }

  private async next() {
    const item = this.queue.shift();
    if (!item || !this.ctx) {
      this.speaking = false;
      return;
    }
    this.speaking = true;
    try {
      const res = await fetch(`/api/tts?lang=${item.lang}&text=${encodeURIComponent(item.text)}`);
      if (!res.ok) throw new Error(`tts ${res.status}`);
      const audio = await this.ctx.decodeAudioData(await res.arrayBuffer());
      const src = this.ctx.createBufferSource();
      src.buffer = audio;
      const g = this.ctx.createGain();
      g.gain.value = 1.4;
      src.connect(g).connect(this.panner(item.pan * 0.7));
      src.onended = () => void this.next();
      src.start();
    } catch {
      // browser speech fallback (not spatial)
      const u = new SpeechSynthesisUtterance(item.text);
      u.lang = VOICE_LANG[item.lang] ?? item.lang;
      u.rate = 1.05;
      u.onend = () => void this.next();
      u.onerror = () => void this.next();
      speechSynthesis.speak(u);
    }
  }
}
