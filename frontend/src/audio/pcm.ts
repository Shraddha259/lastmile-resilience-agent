// PCM helpers shared by the recorder, the player and tests (PRD §16.7).
// public/audio-worklet.js mirrors floatToInt16 + downsample (worklets can't import modules).

export const MIC_RATE = 16000; // Live API input
export const SPEAKER_RATE = 24000; // Live API output
export const FRAME_SAMPLES = 640; // 40 ms at 16 kHz

/** Float32 [-1, 1] -> Int16 little-endian samples (clamped). */
export function floatToInt16(input: Float32Array): Int16Array<ArrayBuffer> {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Int16 samples -> Float32 [-1, 1). */
export function int16ToFloat(input: Int16Array): Float32Array<ArrayBuffer> {
  const out = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) out[i] = input[i] / 0x8000;
  return out;
}

/** Linear-interpolation resample from inRate to outRate (PRD: linear is fine). */
export function downsample(input: Float32Array, inRate: number, outRate: number): Float32Array {
  if (outRate >= inRate) return input;
  const ratio = inRate / outRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}
