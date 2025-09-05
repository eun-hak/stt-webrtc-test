> 오키, 오디오 입력은 채널별 분리할 거다.

좋아요. **채널별 분리(최대 16ch)** 라면 화자분리는 패스하고 훨씬 깔끔하게 갑니다.
아래는 **“맥 개발 → 리눅스(GPU) 운영”을 같은 API로** 돌릴 수 있게 만든 **미니 템플릿**입니다. 그대로 복붙해서 시작하면 됩니다.

---

# 0) 결정 요약

* **입력**: 참가자별 1채널(모노) 스트림 또는 멀티채널 WAV/Opus
* **STT 엔진**:

  * 맥(M1) 개발: 호스트에서 whisper.cpp(또는 faster-whisper CPU) 실행 → HTTP 엔드포인트로 노출
  * 리눅스 5090 운영: 컨테이너로 faster-whisper(CUDA) 실행
* **파이프라인**: `ingest → broker(옵션) → stt-engine(HTTP) → postprocess → 저장/자막`

---

# 1) 리포 구조(권장)

```
stt-stack/
├─ docker/
│  ├─ docker-compose.dev.yml         # 맥 개발용(호스트 STT 사용)
│  ├─ docker-compose.gpu.yml         # 리눅스 운영용(GPU STT 컨테이너)
│  ├─ stt-gpu.Dockerfile             # CUDA + faster-whisper
│  └─ api.Dockerfile                 # API 게이트웨이/오케스트레이터
├─ services/
│  ├─ api/
│  │  ├─ main.py                     # /sessions, /push, /finalize 등
│  │  └─ requirements.txt            # fastapi, uvicorn, httpx, pydantic, redis(옵션)
│  ├─ stt_server/                    # GPU용 STT 서버(컨테이너)
│  │  ├─ server.py                   # /v1/transcribe-window
│  │  └─ requirements.txt            # faster-whisper, ctranslate2, fastapi, uvicorn, ffmpeg
│  └─ postprocess/
│     └─ normalize.py                # 용어/콜사인 정규화, JSONL→SRT 등
├─ tools/
│  ├─ channel_simulator.py           # 16채널 샘플을 5~10초 창으로 흘려보냄
│  └─ mux_split.py                   # 멀티채널 wav → 단일채널 파일들
├─ config/
│  ├─ session.yaml                   # 세션/채널/콜사인 매핑
│  └─ glossary.yaml                  # 용어 사전(알파1→Alpha-1 등)
└─ storage/                          # 오디오/자막/로그(볼륨 마운트)
```

---

# 2) API 계약(엔진 공통)

### `POST /v1/transcribe-window`

* **Body (multipart/form-data)**

  * `audio` (bytes, wav/opus/pcm, **16000 Hz mono** 권장)
  * `stream_id` (string, 예: `S2025-09-04_C07`)
  * `start_ts` (float, 초) – 창 시작 시각
  * `lang` (string, 옵션) – `ko`, `en`, `auto` 등
  * `initial_prompt` (string, 옵션) – 콜사인/지명/약어
  * `word_timestamps` (bool, 옵션, 기본 false)
  * `vad` (bool, 옵션, 기본 true)
* **Response (JSON)**

```json
{
  "stream_id": "S2025-09-04_C07",
  "segments": [
    {"start": 12.10, "end": 14.00, "text": "목표물 확인.", "conf": 0.87}
  ],
  "commit_point": 20.00   // 엔진이 “확정”한 시점(오버랩 보정)
}
```

> 포인트: 맥/리눅스 모두 **이 API만 동일**하면, 엔진을 바꿔도 나머지 서비스는 손댈 게 없습니다.

---

# 3) 맥 개발용 Compose (호스트 STT 사용)

`docker/docker-compose.dev.yml`

```yaml
services:
  api:
    build:
      context: ../services/api
      dockerfile: ../../docker/api.Dockerfile
    environment:
      STT_ENDPOINT: "http://host.docker.internal:8081"   # 맥 호스트에서 띄운 STT
      GLOSSARY_PATH: "/app/config/glossary.yaml"
    volumes:
      - ../config:/app/config:ro
      - ../storage:/app/storage
    ports: ["8080:8080"]

  postprocess:
    image: python:3.11-slim
    volumes:
      - ../services/postprocess:/app
      - ../storage:/data
    command: ["python", "/app/normalize.py", "/data/output.jsonl", "/data/output.srt"]
```

> 맥에서는 **STT 컨테이너가 없습니다.** 호스트에서 whisper.cpp(또는 faster-whisper CPU)를 8081 포트로 띄우세요. (간단히는 `stt_server/server.py`를 CPU로 실행해도 됩니다.)

---

# 4) 리눅스(GPU) 운영 Compose

`docker/docker-compose.gpu.yml`

```yaml
services:
  stt:
    build:
      context: ../services/stt_server
      dockerfile: ../../docker/stt-gpu.Dockerfile
    environment:
      MODEL_DIR: "/models/whisper-large-v3-ct2"
      DEVICE: "cuda"
      COMPUTE_TYPE: "float16"   # int8_float16로 VRAM 절약 가능
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
    volumes:
      - ../models:/models:ro
      - ../storage:/data
    ports: ["8081:8081"]

  api:
    build:
      context: ../services/api
      dockerfile: ../../docker/api.Dockerfile
    environment:
      STT_ENDPOINT: "http://stt:8081"
      GLOSSARY_PATH: "/app/config/glossary.yaml"
    depends_on: [stt]
    volumes:
      - ../config:/app/config:ro
      - ../storage:/app/storage
    ports: ["8080:8080"]
```

`docker/stt-gpu.Dockerfile`

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3-pip ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/stt_server/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY services/stt_server /app
EXPOSE 8081
CMD ["python3", "server.py"]
```

`services/stt_server/requirements.txt`

```
faster-whisper==1.0.0
ctranslate2==4.5.0
fastapi==0.115.0
uvicorn==0.30.0
pydantic==2.8.2
soundfile==0.12.1
```

`services/stt_server/server.py` (요지)

```python
from fastapi import FastAPI, UploadFile, Form
from faster_whisper import WhisperModel
import soundfile as sf
import io, os

MODEL_DIR   = os.getenv("MODEL_DIR", "/models/whisper-large-v3-ct2")
DEVICE      = os.getenv("DEVICE", "cuda")
COMPUTE     = os.getenv("COMPUTE_TYPE", "float16")

app = FastAPI()
model = WhisperModel(MODEL_DIR, device=DEVICE, compute_type=COMPUTE)

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
    if sr != 16000:
        # 간단 예시: ffmpeg로 16k 변환을 권장(실코드에서는 호출)
        pass

    segments, info = model.transcribe(
        io.BytesIO(data),
        language=None if lang == "auto" else lang,
        vad_filter=vad,
        initial_prompt=initial_prompt,
        word_timestamps=word_timestamps,
    )
    out = []
    for s in segments:
        out.append({"start": float(s.start)+start_ts, "end": float(s.end)+start_ts,
                    "text": s.text, "conf": getattr(s, "avg_logprob", None)})
    return {"stream_id": stream_id, "segments": out, "commit_point": out[-1]["end"] if out else start_ts}
```

> 운영에서는 **모델 디렉토리**를 컨테이너에 포함하거나 볼륨으로 **오프라인 반입**하세요.

---

# 5) API 게이트웨이(채널 스케줄러)

`docker/api.Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api /app
COPY config /app/config
EXPOSE 8080
CMD ["python", "main.py"]
```

`services/api/requirements.txt`

```
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
pydantic==2.8.2
pyyaml==6.0.2
```

`services/api/main.py` (요지)

```python
from fastapi import FastAPI, UploadFile, Form
import httpx, os, yaml, uuid

STT_ENDPOINT = os.getenv("STT_ENDPOINT", "http://stt:8081")
GLOSSARY = yaml.safe_load(open(os.getenv("GLOSSARY_PATH","/app/config/glossary.yaml")))

app = FastAPI()
sessions = {}  # stream_id -> state(필요 시)

@app.post("/sessions/create")
def create_session(name: str = Form(...)):
    sid = f"S{uuid.uuid4().hex[:8]}"
    sessions[sid] = {"name": name}
    return {"session_id": sid}

@app.post("/push")
async def push_audio(
    session_id: str = Form(...),
    channel_id: str = Form(...),  # 예: C01~C16
    start_ts: float = Form(...),
    audio: UploadFile = Form(...),
    initial_prompt: str = Form(""),
    lang: str = Form("auto")
):
    stream_id = f"{session_id}_{channel_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"audio": (audio.filename, await audio.read(), audio.content_type or "application/octet-stream")}
        data = {
            "stream_id": stream_id, "start_ts": str(start_ts),
            "lang": lang, "initial_prompt": initial_prompt, "word_timestamps": "false", "vad": "true"
        }
        r = await client.post(f"{STT_ENDPOINT}/v1/transcribe-window", data=data, files=files)
    res = r.json()
    # ▼ 후처리: 용어/콜사인 정규화(예시)
    for seg in res.get("segments", []):
        for k, v in GLOSSARY.get("map", {}).items():
            seg["text"] = seg["text"].replace(k, v)
    return res

@app.post("/finalize")
def finalize(session_id: str):
    # 저장/JSONL/SRT 생성 등(실장 시 파일 I/O 추가)
    return {"ok": True}
```

---

# 6) 채널/콜사인 설정 예시

`config/session.yaml`

```yaml
session_name: "MR-TRAIN-2025-09-04"
channels:
  C01: { callsign: "Alpha-1" }
  C02: { callsign: "Alpha-2" }
  # ...
  C16: { callsign: "Blue-8" }
```

`config/glossary.yaml`

```yaml
map:
  "알파원": "Alpha-1"
  "블루투": "Blue-2"
  "씨투": "C2"
```

---

# 7) 멀티채널 파일을 윈도우로 쪼개 전송(시뮬레이터)

`tools/channel_simulator.py` (요지)

```python
import soundfile as sf, numpy as np, io, time, httpx, argparse

# 예: 16ch wav → 10초 창/2초 오버랩으로 API에 푸시
# 실전에서는 RTP/WS 수신을 이와 같은 윈도우로 변환

def chunks(total, win, hop):
    t=0
    while t < total:
        yield t, min(t+win, total)
        t += hop

def main(path, session_id, api="http://localhost:8080/push", win=10.0, hop=8.0):
    wav, sr = sf.read(path)  # shape: (N, CH)
    if wav.ndim == 1: wav = wav[:, None]
    dur = len(wav)/sr
    chs = wav.shape[1]

    for ch in range(chs):
        for s,e in chunks(dur, win, hop):
            segment = wav[int(s*sr):int(e*sr), ch]
            buf = io.BytesIO(); sf.write(buf, segment, sr, format="WAV"); buf.seek(0)
            data = {"session_id": session_id, "channel_id": f"C{ch+1:02d}", "start_ts": str(s)}
            files = {"audio": (f"c{ch+1}_{s:.1f}.wav", buf.getvalue(), "audio/wav")}
            with httpx.Client(timeout=60) as client:
                r = client.post(api, data=data, files=files)
            time.sleep(0.05)
    print("done")

if __name__ == "__main__":
    # python channel_simulator.py --path 16ch.wav --session S123
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True); ap.add_argument("--session", required=True)
    args = ap.parse_args()
    main(args.path, args.session)
```

---

# 8) 성능/튜닝 가이드(16ch 기준)

* **윈도우**: 5–10초, **오버랩** 20–30% → 지연과 안정성 균형
* **모델/정밀도**: `large-v3` + `float16`(정확도↑), 여유 부족 시 `int8_float16`
* **동시성**: GPU 한 개에 **단일 모델 인스턴스** + API 레벨 큐잉(창 단위 순차 처리) → RTF<1 유지 목표
* **VAD**: 훈련장 잡음이 크면 VAD on, 임계값은 현장 샘플로 미세 조정
* **리샘플링**: 입력이 8 kHz 무전이면 **사전 16 kHz 업샘플**(FFmpeg) 일괄화
* **메모리**: 모델은 컨테이너 기동 시 로드(콜드 스타트 제거). 세션 중 모델 재사용

---

# 9) 운영 체크리스트(질문형, 핵심만)

* [ ] 입력이 **정말 1인 1채널**로 잘 들어오고 있나? (현장 라우팅/녹음기 설정 확인?)
* [ ] **16채널 × 2시간** 연속 처리에서 **RTF<1**을 달성했나? (창 길이·오버랩·모델 크기 조정?)
* [ ] 모든 입력이 **16 kHz 모노**로 표준화되나? (샘플레이트 드리프트 없나?)
* [ ] **콜사인/용어**가 원하는 철자로 안정적으로 나오나? (initial\_prompt/용어 사전 적용?)
* [ ] **모델/컨테이너 해시**와 **오프라인 반입 패키지**(docker save, 모델 디렉토리)가 준비되었나?
* [ ] **장애 폴백**(배치 전사) 경로와 로그 보존/익명화 정책이 정의되어 있나?

---

# 10) 바로 다음 액션

1. 위 구조로 **빈 리포** 만들고 `docker-compose.dev.yml`로 맥에서 **API만** 먼저 띄우기
2. 호스트에서 whisper.cpp 또는 `services/stt_server/server.py`(CPU) 실행 → API와 통신 확인
3. **현장 1\~2분 샘플(채널별 모노)** 로 윈도우/오버랩/VAD/용어사전 튜닝
4. 리눅스 서버에서 `docker-compose.gpu.yml`로 **GPU STT** 교체 기동 → 성능 측정
5. 에어갭 번들(tar) 생성 및 **반입 리허설**

필요하면 위 파일들을 **진짜 파일 형태**로 한 번에 뽑아줄게(폴더 채로). 지금 환경에서 바로 쓸 수 있게 **기본값**(포트/모델 경로)도 세팅해서 전달하겠다.
