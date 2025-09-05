# 04) STT 파이프라인 블루프린트 (온프레미스 MR 작전 훈련)

> 목표: 16채널·2시간 세션을 안정적으로 처리하는 Whisper 계열 STT 파이프라인의 참조 설계. 맥(M1) 개발 → 리눅스 5090 운영을 동일 API로 연결.

---

## 1. 한눈에 보는 구조

- **입력**: 참가자별 1채널 모노(권장) 또는 멀티채널 WAV/Opus
- **VAD**: WebRTC VAD(경량) 또는 Silero VAD(정확)
- **STT 엔진**:
  - 맥(M1): 호스트 `whisper.cpp`(Core ML/Metal) HTTP 서버
  - 리눅스 5090: 컨테이너 `faster-whisper`(CUDA/CT2)
- **후처리**: 용어 정규화(initial_prompt + glossary), 타임스탬프/신뢰도 저장
- **저장/출력**: JSONL(가공), SRT/VTT(재생)

구성: `ingest → broker(옵션) → stt-engine(HTTP) → postprocess → storage`

---

## 2. API 계약(공통)

- `POST /v1/transcribe-window`
  - Body (multipart/form-data)
    - `audio`: 16 kHz mono wav/opus/pcm
    - `stream_id`: 예) `S2025-09-04_C07`
    - `start_ts`: 창 시작 초 단위
    - `lang`: `ko`/`en`/`auto`
    - `initial_prompt`: 콜사인·약어
    - `word_timestamps`: bool
    - `vad`: bool
  - Response
    - `stream_id`, `segments`[{start,end,text,conf}], `commit_point`

> 엔진을 바꿔도 API가 동일하면 상위 서비스는 무변경.

---

## 3. 개발→운영 이행 전략

- **이중 이미지**: `stt-core:arm64-cpu`(맥) / `stt-gpu:amd64-cuda`(리눅스)
- **맥 개발**: 컨테이너로 API/후처리/브로커만 올리고, STT는 호스트 `whisper.cpp`를 8081로 노출. 상위 서비스는 `STT_ENDPOINT=http://host.docker.internal:8081`
- **리눅스 운영**: `nvidia-container-toolkit` + GPU STT 컨테이너. 상위 서비스는 `STT_ENDPOINT=http://stt:8081`
- **모델 반입**: 모델 디렉토리 오프라인 반입(체크섬), 이미지에 포함 또는 볼륨 마운트

---

## 4. 윈도우링/동시성 권장치(16ch)

- 창 길이 5–10초, 오버랩 20–30%
- 파셜→커밋 전이: `commit_point`로 보정
- GPU 1장에는 단일 모델 인스턴스 + API 레벨 큐잉으로 RTF<1 목표
- 품질 우선: `large-v3` + `float16`; 리소스 타이트: `int8_float16`

---

## 5. 용어·정책

- initial_prompt에 콜사인·지명·약어 포함
- glossary 후처리: "알파원→Alpha-1", "블루투→Blue-2" 등
- 보안 정책: 로그 보존/익명화, 비상 삭제, 타임 소스 일관화

---

## 6. 체크리스트(요지)

- [ ] 1인 1채널 입력이 보장되는가
- [ ] 목표 지연/정확도(WER) 기준 수립
- [ ] 16 kHz 모노 표준화/드리프트 방지
- [ ] 모델/컨테이너 해시와 오프라인 번들 준비
- [ ] 16ch × 2h 부하에서 안정(RTF<1), 장애 폴백 준비

---

## 7. 다음 액션

1) 맥에서 API만 compose로 기동 → 호스트 STT 연결
2) 1–2분 실전 샘플로 윈도우/오버랩/VAD 튜닝
3) 리눅스 GPU 컨테이너로 교체 기동 → 성능 측정
4) 에어갭 번들(tar) 작성 및 반입 리허설
