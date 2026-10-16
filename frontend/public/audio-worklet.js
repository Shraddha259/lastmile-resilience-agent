// Mic capture worklet (PRD §16.7): device rate -> 16 kHz PCM16, posted as 40 ms frames.
// Mirrors src/audio/pcm.ts (floatToInt16, downsample).
const OUT_RATE = 16000;
const FRAME = 640;

class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(FRAME);
    this.len = 0;
    this.carry = new Float32Array(0);
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let input = ch;
    if (this.carry.length) {
      input = new Float32Array(this.carry.length + ch.length);
      input.set(this.carry);
      input.set(ch, this.carry.length);
    }
    const ratio = sampleRate / OUT_RATE;
    const outLen = Math.floor(input.length / ratio);
    let peak = 0;
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio;
      const i0 = Math.floor(pos);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const f = pos - i0;
      const s = Math.max(-1, Math.min(1, input[i0] * (1 - f) + input[i1] * f));
      peak = Math.max(peak, Math.abs(s));
      this.buf[this.len++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.len === FRAME) {
        const frame = this.buf.slice(0);
        this.port.postMessage({ frame: frame.buffer }, [frame.buffer]);
        this.len = 0;
      }
    }
    this.carry = input.slice(Math.floor(outLen * ratio));
    this.port.postMessage({ level: peak });
    return true;
  }
}

registerProcessor("pcm16-downsampler", Pcm16Downsampler);
