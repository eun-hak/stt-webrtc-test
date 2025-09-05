# 05) 1주기 실행 계획 — 맥북(M1) 개발 단계

2025.09.04 오전

> 목표: 로컬(M1)에서 엔드투엔드 파이프라인을 검증하고, 리눅스(GPU) 이전 전까지 반복 속도를 극대화.

---

## 1. 완료 기준(DoD)

- [ ] 멀티채널 샘플을 창 단위(5–10초)로 API에 푸시 가능
- [ ] 호스트 STT(whisper.cpp 또는 faster-whisper CPU)가 `/v1/transcribe-window` 처리
- [ ] API가 JSONL 누적 또는 콘솔 출력으로 세그먼트 확인 가능
- [ ] glossary 기반 텍스트 정규화 동작
- [ ] 최소 10분 길이 샘플에서 RTF≤1.5, 부분 오류 원인 메모

---

## 2. 환경 세팅

- Homebrew: `ffmpeg`, `cmake`, `python@3.11`
- whisper.cpp 빌드(또는 미리 빌드된 바이너리)
- 로컬 가상환경: `pip install -r services/api/requirements.txt`

---

## 3. 호스트 STT 서버(whisper.cpp)

- 모델 다운로드: `ggml-large-v3.bin` (초기에는 `small`도 가능)
- 실행 예시:

```bash
# 16 kHz 단일 파일 테스트
ffmpeg -i input.wav -ar 16000 -ac 1 -f wav input16k.wav
./main -m models/ggml-large-v3.bin -f input16k.wav -otxt -osrt
```

- HTTP 서버가 필요하면 간단 대안: `services/stt_server/server.py`를 CPU 모드로 실행해 8081 노출

```bash
# 예: CPU로 임시 실행 (맥 개발용)
MODEL_DIR=~/models/whisper-large-v3-ct2 \
DEVICE=cpu COMPUTE_TYPE=int8_float16 \
python services/stt_server/server.py
```

---

## 4. API/후처리 컨테이너 기동(dev)

`docker/docker-compose.dev.yml` 사용(상위 서비스는 호스트 STT로 라우팅)

```bash
cd docker
docker compose -f docker-compose.dev.yml up --build
```

- 환경변수: `STT_ENDPOINT=http://host.docker.internal:8081`
- `config/glossary.yaml`을 마운트하여 정규화 반영

---

## 5. 채널 시뮬레이터로 엔드투엔드 확인

```bash
# 세션 생성(필요 시)
curl -X POST -F 'name=TEST' http://localhost:8080/sessions/create
# 예시 세션 ID를 받아둔다: Sxxxx

# 16ch wav를 윈도우로 잘라 /push 호출
python tools/channel_simulator.py --path 16ch.wav --session Sxxxx
```

- 기대: API 로그에 `stream_id=Sxxxx_C07` 같은 세그먼트 출력. 결과는 JSON으로 반환 → 필요 시 파일 누적

---

## 6. 튜닝 포인트(이번 주 범위)

- 윈도우: 5–10초, 오버랩: 20–30%
- VAD: WebRTC/Silero 중 하나 고정 후 임계값 조절(현장 잡음 샘플 기반)
- initial_prompt: 콜사인·지명·약어 리스트 반영
- 리샘플링: 8 kHz 입력이면 사전 16 kHz로 업샘플 통일

---

## 7. 리스크/대응

- 맥 Docker에서 마이크 직접 캡처는 우회(호스트→네트워크 전달 또는 파일 시뮬레이션)
- whisper.cpp가 HTTP 서버를 직접 제공하지 않으므로, 초기에는 Python STT 서버로 대체
- 모델/가중치 용량이 커서 초기 다운로드 시간 발생 → 오프라인 캐시 디렉토리 지정

---

## 8. 산출물

- 샘플 10분 전사 JSONL + SRT
- 설정 파일: `config/session.yaml`, `config/glossary.yaml`
- 기록: RTF/지연, 오류 사례, 개선 제안 목록

