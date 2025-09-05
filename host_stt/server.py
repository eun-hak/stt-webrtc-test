import io
import os
from fastapi import FastAPI, UploadFile, Form
from faster_whisper import WhisperModel
import soundfile as sf
import numpy as np
import uvicorn

MODEL_DIR = os.getenv("MODEL_DIR", "small")
DEVICE = os.getenv("DEVICE", "cpu")  # 맥 호스트: 우선 CPU
COMPUTE = os.getenv("COMPUTE_TYPE", "int8")

app = FastAPI()
model = WhisperModel(MODEL_DIR, device=DEVICE, compute_type=COMPUTE)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/v1/transcribe-window")
async def transcribe_window(
    audio: UploadFile,
    stream_id: str = Form(...),
    start_ts: float = Form(0.0),
    lang: str = Form("auto"),
    initial_prompt: str = Form(""),
    word_timestamps: bool = Form(False),
    vad: bool = Form(True),
):
    data = await audio.read()
    wav, sr = sf.read(io.BytesIO(data))
    # 모노/16k 정규화
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != 16000:
        # 간단 선형 리샘플 (개발용)
        target_sr = 16000
        x = np.linspace(0, 1, num=len(wav), endpoint=False)
        new_len = int(len(wav) * target_sr / sr)
        xp = np.linspace(0, 1, num=new_len, endpoint=False)
        wav = np.interp(xp, x, wav).astype(np.float32)
        sr = target_sr
    else:
        # onnxruntime VAD가 float32를 요구하므로 항상 float32로 변환
        if wav.dtype != np.float32:
            wav = wav.astype(np.float32)
    segments, info = model.transcribe(
        wav,
        language=None if lang == "auto" else lang,
        vad_filter=vad,
        initial_prompt=initial_prompt,
        word_timestamps=word_timestamps,
    )
    out = []
    for s in segments:
        out.append({
            "start": float(s.start) + start_ts,
            "end": float(s.end) + start_ts,
            "text": s.text,
            "conf": getattr(s, "avg_logprob", None)
        })
    return {"stream_id": stream_id, "segments": out, "commit_point": out[-1]["end"] if out else start_ts}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)
