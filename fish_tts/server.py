"""Fish TTS: a Wyoming TTS server for Fish Audio voices.

Why it exists: HA's core fish_audio integration (2026.8) only offers the paid backends. Fish's
`s2.1-pro-free` model is free under fair use, so this server calls the Fish API directly with
whatever model is configured, and exposes each configured Fish voice as a Wyoming voice. One
Wyoming TTS entity in HA, voice picked per pipeline.

Supports Wyoming streaming synthesis: HA streams the LLM reply in, we synthesize sentence by
sentence, so speech starts after the first sentence instead of after the whole reply.

If the free model is refused (402 no credit / 429 fair-use limit) and `fallback_model` is set,
the sentence is retried on that (paid) model.
"""
import argparse
import asyncio
import json
import logging
import os
import re
import socket
import urllib.error
import urllib.request
from functools import partial

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import (Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop,
                         SynthesizeStopped)

_LOG = logging.getLogger("fish_tts")
WIDTH, CHANNELS = 2, 1
FISH_URL = "https://api.fish.audio/v1/tts"
# A sentence ends at . ! ? (or newline) followed by whitespace; keeps the punctuation.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")


class Settings:
    def __init__(self, opts: dict):
        self.api_key = opts["api_key"]
        self.model = opts.get("model") or "s2.1-pro-free"
        self.fallback_model = opts.get("fallback_model") or ""
        self.latency = opts.get("latency") or "balanced"
        self.speed = float(opts.get("speed") or 1.0)
        self.rate = int(opts.get("sample_rate") or 24000)
        self.languages = opts.get("languages") or ["en"]
        self.voices = {v["name"]: v["voice_id"] for v in opts.get("voices", [])}
        self.default_voice = next(iter(self.voices), None)


def fish_stream(s: Settings, model: str, text: str, voice_id: str, push) -> None:
    """Blocking: POST to Fish and push raw PCM blocks as they arrive. Raises HTTPError."""
    body = {"text": text, "reference_id": voice_id, "format": "pcm", "sample_rate": s.rate,
            "latency": s.latency, "normalize": True, "prosody": {"speed": s.speed}}
    req = urllib.request.Request(FISH_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {s.api_key}", "Content-Type": "application/json", "model": model})
    with urllib.request.urlopen(req, timeout=60) as r:
        while block := r.read(4096):
            push(block)


class Handler(AsyncEventHandler):
    def __init__(self, info: Info, s: Settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.info, self.s = info, s
        self.streaming = False
        self.stream_voice = None
        self.text_buf = ""
        self.audio_started = False

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.info.event())
            return True
        try:
            if SynthesizeStart.is_type(event.type):
                start = SynthesizeStart.from_event(event)
                self.streaming, self.text_buf, self.audio_started = True, "", False
                self.stream_voice = start.voice.name if start.voice else None
                return True
            if SynthesizeChunk.is_type(event.type) and self.streaming:
                self.text_buf += SynthesizeChunk.from_event(event).text
                parts = _SENTENCE_END.split(self.text_buf)
                self.text_buf = parts.pop()  # unfinished tail
                for sentence in parts:
                    await self.speak(sentence, self.stream_voice)
                return True
            if SynthesizeStop.is_type(event.type) and self.streaming:
                await self.speak(self.text_buf, self.stream_voice)
                await self.finish()
                self.streaming = False
                await self.write_event(SynthesizeStopped().event())
                return True
            if Synthesize.is_type(event.type):
                if self.streaming:
                    return True  # sent alongside a stream for older servers; ignore
                syn = Synthesize.from_event(event)
                self.audio_started = False
                await self.speak(syn.text, syn.voice.name if syn.voice else None)
                await self.finish()
                return True
        except Exception as err:  # noqa: BLE001
            _LOG.exception("synthesis failed")
            await self.write_event(Error(text=str(err), code=type(err).__name__).event())
            self.streaming = False
        return True

    async def finish(self) -> None:
        if not self.audio_started:  # nothing spoken: still hand back a valid, empty stream
            await self.write_event(AudioStart(rate=self.s.rate, width=WIDTH, channels=CHANNELS).event())
        await self.write_event(AudioStop().event())

    async def speak(self, text: str, voice: str | None) -> None:
        text = text.strip()
        if not text:
            return
        voice = voice if voice in self.s.voices else self.s.default_voice
        voice_id = self.s.voices[voice]
        models = [self.s.model] + ([self.s.fallback_model] if self.s.fallback_model else [])
        for i, model in enumerate(models):
            try:
                await self._stream_one(model, text, voice_id)
                _LOG.debug("spoke %d chars with %s/%s", len(text), voice, model)
                return
            except urllib.error.HTTPError as err:
                detail = err.read()[:200].decode(errors="replace")
                if i + 1 < len(models) and err.code in (402, 429):
                    _LOG.warning("%s refused (%s %s), falling back to %s", model, err.code, detail,
                                 models[i + 1])
                    continue
                raise RuntimeError(f"Fish {err.code}: {detail}") from err

    async def _stream_one(self, model: str, text: str, voice_id: str) -> None:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        push = lambda b: loop.call_soon_threadsafe(q.put_nowait, b)  # noqa: E731
        fut = loop.run_in_executor(None, fish_stream, self.s, model, text, voice_id, push)
        fut.add_done_callback(lambda _f: loop.call_soon_threadsafe(q.put_nowait, None))
        carry = b""
        while (block := await q.get()) is not None:
            if not self.audio_started:
                await self.write_event(AudioStart(rate=self.s.rate, width=WIDTH, channels=CHANNELS).event())
                self.audio_started = True
            block = carry + block
            cut = len(block) - len(block) % WIDTH  # keep whole samples
            carry = block[cut:]
            if cut:
                await self.write_event(AudioChunk(audio=block[:cut], rate=self.s.rate, width=WIDTH,
                                                  channels=CHANNELS).event())
        await fut  # re-raises HTTPError etc.


def announce(port: int) -> None:
    """Tell the Supervisor we exist, so HA offers the Wyoming integration automatically."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    body = {"service": "wyoming", "config": {"uri": f"tcp://{socket.gethostname()}:{port}"}}
    req = urllib.request.Request("http://supervisor/discovery", data=json.dumps(body).encode(),
                                 method="POST", headers={"Authorization": f"Bearer {token}",
                                                         "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        _LOG.info("announced to Supervisor discovery")
    except Exception as err:  # noqa: BLE001
        _LOG.warning("discovery announce failed: %s", err)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--options", default="/data/options.json")
    ap.add_argument("--port", type=int, default=10220)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    with open(a.options) as f:
        opts = json.load(f)
    logging.basicConfig(level=logging.DEBUG if a.debug or opts.get("debug") else logging.INFO)
    s = Settings(opts)
    if not s.voices:
        raise SystemExit("no voices configured")
    attribution = Attribution(name="Fish Audio", url="https://fish.audio")
    info = Info(tts=[TtsProgram(
        name="fish-tts", description="Fish Audio voices", attribution=attribution, installed=True,
        version="1.0.1", supports_synthesize_streaming=True,
        voices=[TtsVoice(name=n, description=n.replace("_", " ").title(), attribution=attribution,
                         installed=True, version=None, languages=s.languages)
                for n, vid in s.voices.items()])])
    _LOG.info("model %s (fallback %s), voices %s", s.model, s.fallback_model or "none", list(s.voices))
    announce(a.port)
    server = AsyncServer.from_uri(f"tcp://0.0.0.0:{a.port}")
    await server.run(partial(Handler, info, s))


if __name__ == "__main__":
    asyncio.run(main())
