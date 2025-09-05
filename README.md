### services/api services/stt_server host_webrtc 3개를 다 돌린 후 ngrok start --all 해서 총 4개의 터미널 돌리면 됨

## ChatBrain STT WebRTC Test

온프레미스·보안 환경의 MR 작전 훈련에서 팀 내 통신을 실시간으로 전사(STT)하기 위한 최소 구현 레퍼런스입니다. 맥북(M1) 개발 환경과 리눅스(5090 GPU) 운영 환경을 동일한 API 계약으로 연결합니다.

### 주요 목표

- 최대 16명, 2시간 세션의 음성을 안정적으로 수집·전사·저장
- 개발(M1)과 운영(GPU) 간 일관된 API(`/v1/transcribe-window`)
- 브라우저 WebRTC 업스트림 + WS/SSE 다운스트림(실시간 파셜/커밋 표시)

### 아키텍처 개요

- 입력: 참가자별 1채널(권장) 또는 멀티채널 WAV/Opus
- VAD: WebRTC VAD(경량) 또는 Silero VAD(정확)
- STT 엔진
  - 개발(M1): 호스트 `whisper.cpp` 또는 CPU 모드 `faster-whisper`
  - 운영(GPU): 컨테이너 `faster-whisper`(CUDA/CT2)
- 후처리: initial_prompt, `config/glossary.yaml` 기반 용어 정규화
- 저장/출력: JSONL, SRT/VTT

구성: ingest → broker(옵션) → stt-engine(HTTP) → postprocess → storage

### API 계약(공통)

`POST /v1/transcribe-window`

- Body (multipart/form-data)
  - `audio`: 16 kHz mono wav/opus/pcm
  - `stream_id`: 예) `S2025-09-04_C07`
  - `start_ts`: 창 시작(초)
  - `lang`: `ko` | `en` | `auto`
  - `initial_prompt`: 콜사인·약어
  - `word_timestamps`: bool
  - `vad`: bool
- Response(JSON)
  - `stream_id`, `segments`[{start,end,text,conf}], `commit_point`

API가 동일하면 엔진 교체 시 상위 서비스 변경이 없습니다.

### 디렉터리 구조

```
docker/                 # compose/Dockerfile들
services/
  api/                  # FastAPI 게이트웨이(+ WebRTC 시그널링/WS)
  stt_server/           # STT 서버(faster-whisper)
config/                 # glossary 등 설정
storage/                # 산출물 저장소(볼륨)
00-docs/                # 설계/계획 문서
z-sample/               # 샘플 오디오
```

### 빠른 시작(개발, M1)

1. Docker dev 구성 기동(API만 컨테이너로 실행)

```bash
cd docker
docker compose -f docker-compose.dev.yml up --build
```

2. STT 엔진(호스트) 실행 옵션

- whisper.cpp(Core ML) 또는 `services/stt_server/server.py`(CPU)로 8081에 HTTP 노출

환경 변수 예시: `STT_ENDPOINT=http://host.docker.internal:8081`

3. 푸시 테스트(파일 기반)

```bash
curl -X POST -F 'name=TEST' http://localhost:8080/sessions/create
# 반환된 session_id 사용
curl -X POST \
  -F 'session_id=Sxxxx' -F 'channel_id=C01' -F 'start_ts=0' \
  -F 'audio=@z-sample/sample16k.wav;type=audio/wav' \
  http://localhost:8080/push
```

### WebRTC 데모(최소)

- 시그널링: `POST /webrtc/offer` → answer 반환
- 미디어: 브라우저 `getUserMedia` → `RTCPeerConnection` 업스트림(오디오)
- 다운스트림: `WebSocket /ws/transcript?session=...`로 파셜/커밋 이벤트 수신
- 이벤트 스키마
  - partial: `{ "type":"partial", "stream_id":"S1_C01", "start":12.1, "end":13.5, "text":"..." }`
  - final: `{ "type":"final", "stream_id":"S1_C01", "segments":[...], "commit_point":14.0 }`

### 운영 전 준비(GPU 서버)

- NVIDIA 드라이버 + nvidia-container-toolkit 설치
- 모델 디렉토리(오프라인) 준비 및 이미지/볼륨에 포함
- `docker-compose.gpu.yml`로 STT 컨테이너 교체 기동(large-v3 fp16 또는 int8_float16)

### 체크리스트(요지)

- [ ] 1인 1채널 입력 보장(최선) 또는 혼합음원시 화자분리 결정
- [ ] 목표 지연·정확도(WER) 기준 수립 및 측정
- [ ] 16 kHz 모노 표준화(리샘플 포함), 16ch×2h 부하에서 RTF<1
- [ ] 용어 사전/initial_prompt 반영, 보안·로그 정책 수립
- [ ] 에어갭 번들(이미지 tar + 모델 + compose) 생성/검증

### 문서

- `00-docs/04-blueprint.md`: 파이프라인 블루프린트
- `00-docs/05-1-cycle-macbook.md`: 1주기 실행 계획(M1)
- `00-docs/06-WebRTC-demo.md`: WebRTC 실시간 데모 계획

### 라이선스/저작권

2025 © SimSimi Inc. 본 리포지토리는 내부 연구·시연 목적의 예시 코드를 포함합니다.
