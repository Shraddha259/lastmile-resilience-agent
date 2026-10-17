// 24 kHz PCM16 agent audio, scheduled back to back; flush() on barge-in (PRD §16.7).
import { SPEAKER_RATE, int16ToFloat } from "./pcm";

export class Player {
  private ctx = new AudioContext({ sampleRate: SPEAKER_RATE });
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();

  /** Call from a user gesture (Answer button) to satisfy autoplay rules. */
  async resume(): Promise<void> {
    await this.ctx.resume();
  }

  enqueue(data: ArrayBuffer): void {
    const samples = int16ToFloat(new Int16Array(data));
    if (!samples.length) return;
    const buffer = this.ctx.createBuffer(1, samples.length, SPEAKER_RATE);
    buffer.copyToChannel(samples, 0);
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.ctx.destination);
    this.nextStart = Math.max(this.ctx.currentTime, this.nextStart);
    src.start(this.nextStart);
    this.nextStart += buffer.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  flush(): void {
    this.sources.forEach((s) => {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    });
    this.sources.clear();
    this.nextStart = 0;
  }

  close(): void {
    this.flush();
    void this.ctx.close();
  }
}
