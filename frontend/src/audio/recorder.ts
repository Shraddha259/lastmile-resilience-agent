// Microphone -> 16 kHz PCM16 frames via an AudioWorklet (PRD §16.7).
export type Recorder = { stop: () => void };

export async function startRecorder(
  onFrame: (frame: ArrayBuffer) => void,
  onLevel: (level: number) => void,
): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("/audio-worklet.js");
  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm16-downsampler");
  node.port.onmessage = (e: MessageEvent<{ frame?: ArrayBuffer; level?: number }>) => {
    if (e.data.frame) onFrame(e.data.frame);
    if (e.data.level !== undefined) onLevel(e.data.level);
  };
  source.connect(node);
  await ctx.resume();
  return {
    stop: () => {
      node.port.onmessage = null;
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
