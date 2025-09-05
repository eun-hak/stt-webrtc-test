import io
import os
from fastapi import FastAPI, UploadFile, Form
from faster_whisper import WhisperModel
import soundfile as sf
import numpy as np
from pydantic import BaseModel

# STT 서버: faster-whisper를 사용한 실제 음성 인식

app = FastAPI()

# faster-whisper 모델 로드 (서버 시작 시 한 번만)
print("Loading faster-whisper model...")
MODEL_DIR = os.getenv("MODEL_DIR", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE = os.getenv("COMPUTE_TYPE", "int8")
whisper_model = WhisperModel(MODEL_DIR, device=DEVICE, compute_type=COMPUTE)
print("faster-whisper model loaded successfully!")

class Segment(BaseModel):
    start: float
    end: float
    text: str
    conf: float | None = None


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
    try:
        # 오디오 데이터 읽기 및 전처리 (host_stt 방식과 동일)
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
        
        # faster-whisper로 음성 인식 실행
        print(f"Transcribing audio: {stream_id}")
        segments, info = whisper_model.transcribe(
            wav,
            language=None if lang == "auto" else lang,
            vad_filter=vad,
            initial_prompt=initial_prompt,
            word_timestamps=word_timestamps,
        )
        
        # 결과 처리
        out = []
        for s in segments:
            out.append({
                "start": float(s.start) + start_ts,
                "end": float(s.end) + start_ts,
                "text": s.text,
                "conf": getattr(s, "avg_logprob", None)
            })
        
        print(f"Transcription result: {len(out)} segments")
        if out:
            print(f"First segment: {out[0]['text']}")
        
        return {"stream_id": stream_id, "segments": out, "commit_point": out[-1]["end"] if out else start_ts}
        
    except Exception as e:
        print(f"Transcription error: {e}")
        # 오류 발생 시 폴백
        seg = {
            "start": float(start_ts),
            "end": float(start_ts) + 5.0,
            "text": f"[인식 오류: {str(e)}]",
            "conf": 0.0,
        }
        return {"stream_id": stream_id, "segments": [seg], "commit_point": seg["end"]}


