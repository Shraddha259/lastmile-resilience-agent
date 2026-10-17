import { describe, expect, it } from "vitest";
import { FRAME_SAMPLES, MIC_RATE, downsample, floatToInt16, int16ToFloat } from "./pcm";

describe("PCM helpers (PRD §16.7)", () => {
  it("converts float to int16 with clamping and back", () => {
    const i16 = floatToInt16(new Float32Array([0, 1, -1, 2, -2, 0.5]));
    expect(Array.from(i16)).toEqual([0, 32767, -32768, 32767, -32768, 16383]);
    const back = int16ToFloat(i16);
    expect(back[1]).toBeCloseTo(1, 3);
    expect(back[2]).toBe(-1);
  });

  it("downsamples 48 kHz to 16 kHz: 40 ms in -> one 640-sample frame out", () => {
    const in48 = new Float32Array(1920).fill(0.25);
    const out = downsample(in48, 48000, MIC_RATE);
    expect(out.length).toBe(FRAME_SAMPLES);
    expect(out[100]).toBeCloseTo(0.25);
  });

  it("interpolates between samples", () => {
    const out = downsample(new Float32Array([0, 1, 0, 1, 0, 1]), 3, 2);
    expect(out.length).toBe(4);
    expect(out[1]).toBeCloseTo(0.5);
  });
});
