"""
ASR Service — Real-time Speech Recognition with FunASR

Models:
  - paraformer-zh-streaming: Streaming ASR (chunk-based inference)
  - fsmn-vad: Voice Activity Detection (speech endpoint detection)
  - ct-punc: Punctuation restoration

Protocol (WebSocket /ws/asr):
  Client → Server: 16kHz/16-bit/mono PCM binary frames
  Client → Server: "STOP" text message to finalize
  Server → Client: {"type": "partial"|"final", "text": "..."}
"""

import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Configuration — fail-fast on missing critical dependencies
# ──────────────────────────────────────────────────────────────
ASR_MODEL = os.getenv("ASR_MODEL", "paraformer-zh-streaming")
VAD_MODEL = os.getenv("VAD_MODEL", "fsmn-vad")
PUNC_MODEL = os.getenv("PUNC_MODEL", "ct-punc")
ASR_PORT = int(os.getenv("ASR_PORT", "8001"))

logger = logging.getLogger("asr-service")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Thread pool for blocking FunASR inference calls.
# NOTE: FunASR model.generate() is synchronous. We offload it to a thread pool
# to avoid blocking the asyncio event loop. Each session uses its own cache dict,
# so concurrent calls with different caches should be safe.
executor = ThreadPoolExecutor(max_workers=4)

# Global model references — set during lifespan startup
asr_model = None
vad_model = None
punc_model = None


# ──────────────────────────────────────────────────────────────
# FastAPI Lifespan — real model loading (NO mock)
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global asr_model, vad_model, punc_model

    logger.info("=" * 60)
    logger.info("ASR Service starting — loading FunASR models...")
    logger.info("=" * 60)

    try:
        from funasr import AutoModel
    except ImportError:
        logger.critical(
            "FATAL: funasr package not installed. "
            "Run: uv sync  (dependencies are in pyproject.toml)"
        )
        sys.exit(1)

    logger.info(f"Loading ASR model: {ASR_MODEL}")
    asr_model = AutoModel(model=ASR_MODEL)
    logger.info("✓ ASR model loaded.")

    logger.info(f"Loading VAD model: {VAD_MODEL}")
    vad_model = AutoModel(model=VAD_MODEL)
    logger.info("✓ VAD model loaded.")

    logger.info(f"Loading PUNC model: {PUNC_MODEL}")
    punc_model = AutoModel(model=PUNC_MODEL)
    logger.info("✓ PUNC model loaded.")

    logger.info("=" * 60)
    logger.info("All models loaded. Service ready on port %d", ASR_PORT)
    logger.info("=" * 60)

    yield

    logger.info("ASR Service shutting down.")


app = FastAPI(title="ASR Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check endpoint — confirms models are loaded."""
    if asr_model is None or vad_model is None or punc_model is None:
        return {"status": "error", "detail": "Models not loaded"}, 503
    return {
        "status": "ok",
        "models": {
            "asr": ASR_MODEL,
            "vad": VAD_MODEL,
            "punc": PUNC_MODEL,
        },
    }


# ──────────────────────────────────────────────────────────────
# Streaming ASR Session — per-connection state machine
# ──────────────────────────────────────────────────────────────
class StreamingASRSession:
    """
    Manages per-connection state for streaming ASR.

    Architecture:
      1. Incoming PCM bytes are converted to float32 and buffered.
      2. VAD runs on 200ms chunks to detect speech start/end.
      3. Streaming ASR runs on 600ms chunks to produce partial text.
      4. When VAD detects speech end, ASR is finalized and ct-punc is applied.
      5. ASR cache is reset for the next utterance.

    All FunASR API calls follow the official AutoModel streaming interface:
      - chunk_size=[0, 10, 5] for ASR (600ms chunks)
      - chunk_size=200 (ms) for VAD
      - cache={} dict persisted across chunks, reset per utterance
      - is_final=True only on the last chunk of an utterance
    """

    # ASR streaming parameters (per FunASR docs)
    ASR_CHUNK_SIZE = [0, 10, 5]  # [look_back, current, look_ahead] in frames
    ENCODER_CHUNK_LOOK_BACK = 4
    DECODER_CHUNK_LOOK_BACK = 1
    # Each frame = 60ms → current chunk = 10 * 60ms = 600ms
    # At 16kHz: 600ms = 9600 samples
    ASR_CHUNK_STRIDE = ASR_CHUNK_SIZE[1] * 960  # 9600 samples

    # VAD streaming parameters
    VAD_CHUNK_MS = 200  # milliseconds
    VAD_CHUNK_STRIDE = int(16000 * VAD_CHUNK_MS / 1000)  # 3200 samples

    def __init__(self):
        self.asr_cache: dict = {}
        self.vad_cache: dict = {}
        self.asr_buffer = np.array([], dtype=np.float32)
        self.vad_buffer = np.array([], dtype=np.float32)
        self.accumulated_text: str = ""
        self.speech_ended: bool = False

    def process_audio(self, pcm_bytes: bytes) -> list[dict]:
        """
        Process incoming 16kHz/16-bit/mono PCM bytes.

        Returns a list of messages: [{"type": "partial"|"final", "text": "..."}]
        This method is called from a thread executor (blocking).
        """
        # Convert 16-bit signed PCM → float32 in [-1.0, 1.0]
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        self.vad_buffer = np.concatenate([self.vad_buffer, audio])
        self.asr_buffer = np.concatenate([self.asr_buffer, audio])

        messages: list[dict] = []

        # ── Step 1: Process VAD in 200ms chunks ──
        while len(self.vad_buffer) >= self.VAD_CHUNK_STRIDE:
            vad_chunk = self.vad_buffer[: self.VAD_CHUNK_STRIDE]
            self.vad_buffer = self.vad_buffer[self.VAD_CHUNK_STRIDE :]

            vad_res = vad_model.generate(
                input=vad_chunk,
                cache=self.vad_cache,
                is_final=False,
                chunk_size=self.VAD_CHUNK_MS,
            )

            # VAD output format (streaming):
            #   [[beg, -1]]    → speech started, ongoing
            #   [[-1, end]]    → speech ended
            #   [[beg, end]]   → complete speech segment
            #   []             → no change
            if vad_res and len(vad_res[0]["value"]):
                segments = vad_res[0]["value"]
                for seg in segments:
                    if len(seg) == 2:
                        if seg[0] != -1 and seg[1] == -1:
                            # Speech started, ongoing — keep streaming ASR
                            pass
                        elif seg[1] != -1:
                            # Speech ended ([-1, end] or [beg, end])
                            self.speech_ended = True

        # ── Step 2: Process ASR in 600ms chunks ──
        while len(self.asr_buffer) >= self.ASR_CHUNK_STRIDE:
            asr_chunk = self.asr_buffer[: self.ASR_CHUNK_STRIDE]
            self.asr_buffer = self.asr_buffer[self.ASR_CHUNK_STRIDE :]

            asr_res = asr_model.generate(
                input=asr_chunk,
                cache=self.asr_cache,
                is_final=False,
                chunk_size=self.ASR_CHUNK_SIZE,
                encoder_chunk_look_back=self.ENCODER_CHUNK_LOOK_BACK,
                decoder_chunk_look_back=self.DECODER_CHUNK_LOOK_BACK,
            )

            if asr_res and asr_res[0]["text"]:
                new_text = asr_res[0]["text"]
                self.accumulated_text += new_text
                messages.append({"type": "partial", "text": self.accumulated_text})

        # ── Step 3: Finalize if VAD detected speech end ──
        if self.speech_ended and self.accumulated_text.strip():
            messages.extend(self._finalize_utterance())

        return messages

    def _finalize_utterance(self) -> list[dict]:
        """Finalize current utterance: flush ASR, apply punctuation, reset state."""
        messages: list[dict] = []

        # Flush remaining ASR buffer with is_final=True
        if len(self.asr_buffer) > 0:
            asr_res = asr_model.generate(
                input=self.asr_buffer,
                cache=self.asr_cache,
                is_final=True,
                chunk_size=self.ASR_CHUNK_SIZE,
                encoder_chunk_look_back=self.ENCODER_CHUNK_LOOK_BACK,
                decoder_chunk_look_back=self.DECODER_CHUNK_LOOK_BACK,
            )
            if asr_res and asr_res[0]["text"]:
                self.accumulated_text += asr_res[0]["text"]
            self.asr_buffer = np.array([], dtype=np.float32)

        # Apply punctuation restoration
        if self.accumulated_text.strip():
            punc_res = punc_model.generate(input=self.accumulated_text)
            final_text = (
                punc_res[0]["text"]
                if punc_res and punc_res[0]["text"]
                else self.accumulated_text
            )
            messages.append({"type": "final", "text": final_text})

        # Reset state for next utterance
        self.accumulated_text = ""
        self.asr_cache = {}
        self.speech_ended = False

        return messages

    def finalize_session(self) -> list[dict]:
        """Called when client stops recording. Flush everything."""
        messages: list[dict] = []

        # Flush remaining ASR buffer
        if len(self.asr_buffer) > 0:
            asr_res = asr_model.generate(
                input=self.asr_buffer,
                cache=self.asr_cache,
                is_final=True,
                chunk_size=self.ASR_CHUNK_SIZE,
                encoder_chunk_look_back=self.ENCODER_CHUNK_LOOK_BACK,
                decoder_chunk_look_back=self.DECODER_CHUNK_LOOK_BACK,
            )
            if asr_res and asr_res[0]["text"]:
                self.accumulated_text += asr_res[0]["text"]
            self.asr_buffer = np.array([], dtype=np.float32)

        # Flush remaining VAD buffer
        if len(self.vad_buffer) > 0:
            vad_model.generate(
                input=self.vad_buffer,
                cache=self.vad_cache,
                is_final=True,
                chunk_size=self.VAD_CHUNK_MS,
            )
            self.vad_buffer = np.array([], dtype=np.float32)

        # Apply punctuation to any remaining text
        if self.accumulated_text.strip():
            punc_res = punc_model.generate(input=self.accumulated_text)
            final_text = (
                punc_res[0]["text"]
                if punc_res and punc_res[0]["text"]
                else self.accumulated_text
            )
            messages.append({"type": "final", "text": final_text})

        return messages


# ──────────────────────────────────────────────────────────────
# WebSocket endpoint — real-time ASR
# ──────────────────────────────────────────────────────────────
@app.websocket("/ws/asr")
async def websocket_asr(ws: WebSocket):
    """
    Real-time ASR WebSocket endpoint.

    Accepts 16kHz/16-bit/mono PCM binary frames from the client.
    Returns JSON messages with partial/final transcription results.
    Send text message "STOP" to finalize the session.
    """
    await ws.accept()
    session = StreamingASRSession()
    logger.info("WebSocket ASR session started.")

    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await ws.receive()

            if data.get("type") == "websocket.disconnect":
                break

            if "bytes" in data and data["bytes"]:
                # Real PCM audio binary data
                pcm_bytes = data["bytes"]
                messages = await loop.run_in_executor(
                    executor, session.process_audio, pcm_bytes
                )
                for msg in messages:
                    await ws.send_json(msg)

            elif "text" in data and data["text"]:
                text_msg = data["text"]
                if text_msg == "STOP":
                    logger.info("Client sent STOP — finalizing session.")
                    messages = await loop.run_in_executor(
                        executor, session.finalize_session
                    )
                    for msg in messages:
                        await ws.send_json(msg)
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
        try:
            await loop.run_in_executor(executor, session.finalize_session)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass

    finally:
        logger.info("WebSocket ASR session ended.")


# ──────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ASR_PORT)
