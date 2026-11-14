import io
import wave
from collections.abc import AsyncIterator

import numpy as np
from agents import Agent, Runner, SQLiteSession
from agents.voice import AudioInput, VoicePipeline
from agents.voice.workflow import VoiceWorkflowBase, VoiceWorkflowHelper


class SessionedVoiceWorkflow(VoiceWorkflowBase):
    """Delegates memory to the same SQLiteSession the text CLI/API use,
    instead of SingleAgentVoiceWorkflow's own in-memory, per-instance
    history list - so a voice turn and a text turn under the same
    session_id share one conversation."""

    def __init__(self, agent: Agent, session: SQLiteSession) -> None:
        self._agent = agent
        self._session = session

    async def run(self, transcription: str) -> AsyncIterator[str]:
        result = Runner.run_streamed(self._agent, transcription, session=self._session)
        async for chunk in VoiceWorkflowHelper.stream_text_from(result):
            yield chunk


def _decode_wav(data: bytes) -> AudioInput:
    with wave.open(io.BytesIO(data), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())
    # st.audio_input always emits 16-bit PCM WAV, matching AudioInput's
    # default sample_width=2 and its int16/float32 buffer contract.
    buffer = np.frombuffer(frames, dtype=np.int16)
    return AudioInput(buffer=buffer, frame_rate=frame_rate, channels=channels)


async def run_voice_turn(audio_bytes: bytes, agent: Agent, session: SQLiteSession) -> bytes:
    audio_input = _decode_wav(audio_bytes)
    pipeline = VoicePipeline(workflow=SessionedVoiceWorkflow(agent, session))
    result = await pipeline.run(audio_input)

    output_buffer = io.BytesIO()
    with wave.open(output_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        async for event in result.stream():
            if event.type == "voice_stream_event_audio" and event.data is not None:
                wav_file.writeframes(event.data.tobytes())
    return output_buffer.getvalue()
