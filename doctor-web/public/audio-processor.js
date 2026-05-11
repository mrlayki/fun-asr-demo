/**
 * PCM Resampler AudioWorklet Processor
 *
 * Resamples audio from the browser's native sample rate (typically 44100/48000 Hz)
 * down to 16000 Hz, converts Float32 → 16-bit signed PCM, and posts chunks
 * to the main thread via MessagePort.
 *
 * Output: Int16Array chunks of 2560 samples (160ms at 16kHz = 5120 bytes)
 *
 * This processor uses linear interpolation for resampling.
 * For production use with critical audio quality requirements,
 * consider replacing with a proper FIR low-pass filter.
 */
class PCMResamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // `sampleRate` is a global variable in AudioWorkletGlobalScope
    // It reflects the AudioContext's sample rate.
    this.inputSampleRate = sampleRate;
    this.outputSampleRate = 16000;
    this.ratio = this.inputSampleRate / this.outputSampleRate;

    // Resampling state
    this.inputBuffer = [];
    this.resamplePointer = 0;

    // Output accumulation — send 160ms chunks (2560 samples at 16kHz)
    this.outputBuffer = [];
    this.chunkThreshold = 2560;

    // Track active state
    this.isActive = true;

    this.port.onmessage = (event) => {
      if (event.data === 'stop') {
        this.isActive = false;
        // Flush remaining output
        if (this.outputBuffer.length > 0) {
          this.port.postMessage(new Int16Array(this.outputBuffer));
          this.outputBuffer = [];
        }
      }
    };
  }

  process(inputs) {
    if (!this.isActive) return false;

    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;

    // Take first channel only (mono)
    const channelData = input[0];

    // Append to input buffer
    for (let i = 0; i < channelData.length; i++) {
      this.inputBuffer.push(channelData[i]);
    }

    // Resample using linear interpolation
    while (this.resamplePointer + this.ratio < this.inputBuffer.length) {
      const left = Math.floor(this.resamplePointer);
      const right = left + 1;
      const weight = this.resamplePointer - left;

      // Linear interpolation between adjacent samples
      let sample;
      if (right < this.inputBuffer.length) {
        sample = (1 - weight) * this.inputBuffer[left] + weight * this.inputBuffer[right];
      } else {
        sample = this.inputBuffer[left];
      }

      // Clamp to [-1, 1] and convert to 16-bit signed PCM
      sample = Math.max(-1, Math.min(1, sample));
      const pcm16 = sample < 0 ? sample * 32768 : sample * 32767;
      this.outputBuffer.push(Math.round(pcm16));

      this.resamplePointer += this.ratio;
    }

    // Remove consumed samples from input buffer
    const consumed = Math.floor(this.resamplePointer);
    if (consumed > 0) {
      this.inputBuffer = this.inputBuffer.slice(consumed);
      this.resamplePointer -= consumed;
    }

    // Send chunk when threshold reached
    while (this.outputBuffer.length >= this.chunkThreshold) {
      const chunkSamples = this.outputBuffer.splice(0, this.chunkThreshold);
      const chunk = new Int16Array(chunkSamples);
      // Transfer the underlying ArrayBuffer for zero-copy performance
      this.port.postMessage(chunk.buffer, [chunk.buffer]);
    }

    return true;
  }
}

registerProcessor('pcm-resampler-processor', PCMResamplerProcessor);
