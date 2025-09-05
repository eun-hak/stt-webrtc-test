> 아키텍처에서 해야 할 것들이 있어서 그런지 docker 가지고는 다 안 되는가보다? 맥북에서 docker 로 구현하고 그대로 패키징해서 리눅스에 배포한다든지 말이지..

짧게 결론부터: **거의 다 Docker로 됩니다.** 다만 두 가지는 “호스트 의존”이라 그대로 이식이 안 됩니다.

1. **가속기**: 맥(M1)은 **Core ML/Metal**, 리눅스 5090은 **CUDA**라서 *같은 컨테이너*로 가속을 공통 처리할 수 없습니다.
2. **오디오 입력**: 맥의 CoreAudio/마이크 직접 캡처는 Docker에서 제약이 큽니다(가상화+권한 이슈).

그래서 \*\*“API 추상화 + 이중 이미지 전략(arm64-CPU/amd64-CUDA)”\*\*을 권합니다. 개발은 맥에서 Docker로 대부분 돌리되, STT 엔진만은

* 맥: 컨테이너 밖(호스트)에서 whisper.cpp(Core ML)로 띄우고,
* 서버/운영: 컨테이너 안에서 faster-whisper(CUDA)로 띄우는 방식입니다.
  둘 다 **같은 HTTP/gRPC API**를 제공하게 해두면 코드 변경 없이 교체됩니다.

---

# 권장 토폴로지

* **ingest**: (선택) 장비/무전에서 들어오는 **오디오를 파일/RTP/WS**로 표준화해 브로커로 푸시
* **broker**: Redis/NATS (경량 큐)
* **stt-engine**: Whisper 계열 (맥=호스트 whisper.cpp, 리눅스=컨테이너 faster-whisper)
* **diarizer**: (필요 시) NeMo/pyannote 컨테이너
* **postprocess**: 용어 정규화/타임스탬프 머지
* **api-gateway**: STT/대화록 조회 REST

> 포인트: **장치·가속기 의존부**(오디오 캡처·GPU)는 호스트/플랫폼에 붙이고, 나머지는 전부 컨테이너로 고정.

---

# Docker로 “그대로 패키징→배포”를 위한 실전 가이드

## 1) 맥(M1) 개발 흐름

* **컨테이너**: `api-gateway`, `diarizer`, `postprocess`, `broker` 등 전부 Docker로.
* **STT 엔진**: 맥 호스트에서 whisper.cpp(Core ML) 실행 → `http://localhost:8081` 같은 엔드포인트 노출.
* **컨테이너들은** `STT_ENDPOINT=http://host.docker.internal:8081` 로 호스트 엔진에 붙습니다.
* **오디오 입력**: 맥에서 컨테이너에 마이크 패스스루는 번거로워서, 개발 시엔

  * (권장) **파일/네트워크 시뮬레이터**로 대체(녹음본 WAV/Opus를 5\~10초 단위로 흘려보내기),
  * 또는 BlackHole/Loopback 같은 가상장치→로컬 서비스(호스트)→컨테이너로 **네트워크 전송**.

### docker-compose.dev.yml (요지)

```yaml
services:
  broker:
    image: redis:7
  api:
    build: ./services/api
    environment:
      STT_ENDPOINT: "http://host.docker.internal:8081"
    depends_on: [broker]
  diarizer:
    build: ./services/diarizer
    depends_on: [broker]
  postprocess:
    build: ./services/postprocess
    depends_on: [broker]
```

> 맥에서는 **STT 컨테이너가 아예 없음**(호스트 whisper.cpp로 대체). API는 동일.

## 2) 리눅스(GPU) 테스트/운영

* **NVIDIA 드라이버 + nvidia-container-toolkit** 설치.
* **STT 전용 GPU 이미지**를 따로 빌드해서 배포(`amd64 + CUDA`).
* **모델 파일**(large-v3 등)은 **이미지에 포함**하거나 **오프라인 볼륨**에 넣기(에어갭 대비).

### Dockerfile.gpu (요지)

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# 필수 패키지
RUN apt-get update && apt-get install -y python3-pip ffmpeg && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 고정
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r /app/requirements.txt
# requirements.txt 예: faster-whisper==1.0.0 ctranslate2==4.5.0 uvicorn fastapi

# 모델(오프라인) 미리 복사 or 첫 실행 시 로컬 볼륨에서 로드
COPY models/ /models/
COPY stt_server/ /app/
WORKDIR /app

EXPOSE 8081
CMD ["python3", "server.py", "--model_dir", "/models/whisper-large-v3-ct2", "--device", "cuda", "--compute_type", "float16"]
```

### docker-compose.gpu.yml (요지)

```yaml
services:
  broker:
    image: redis:7
  stt:
    image: yourrepo/stt-gpu:1.0
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
    environment:
      CT2_USE_EXPERIMENTAL_PACKED_GEMM: "1"
  api:
    build: ./services/api
    environment:
      STT_ENDPOINT: "http://stt:8081"
    depends_on: [stt, broker]
```

> Compose v2 이상이면 `deploy.resources.reservations.devices.capabilities: ["gpu"]` 또는 `gpus: all` 사용.

## 3) 이미지·아키텍처 전략

* **두 개의 태그**를 권장:

  * `stt-core:arm64-cpu` (맥 개발용, CPU 또는 호스트 Core ML와 인터페이스 호환)
  * `stt-gpu:amd64-cuda` (리눅스 운영용)
* `docker buildx`로 멀티 아키텍처 매니페스트를 만들 수도 있지만, **CUDA가 포함된 이미지는 맥에서 쓸 수 없으니** 논리적으로 분리하는 게 깔끔합니다.
* 에어갭 환경이면 `docker save`/`load`로 **tar 아카이브 반입**.

---

# 어디까지 Docker로 되고, 어디서 주의해야 하나?

**✅ Docker로 OK**

* STT API 서버(HTTP/gRPC), 후처리, 화자분리(모델만 준비되면), 브로커, 대시보드, 스토리지(미니오 등)
* 멀티채널 파일 처리(16ch WAV/Opus), RTP/WS 입력, 배치·스트리밍 파이프라인

**⚠️ 호스트 의존/주의**

* **맥에서 마이크/무전 “직접 캡처”**: 개발편의상 **호스트 프로세스 → 네트워크로 컨테이너에 전달** 권장
* **가속기**: Mac Metal/Core ML은 컨테이너 내부에서 쓰기 어려움(사실상 호스트가 유리). 리눅스는 CUDA 전용 컨테이너로 분리
* **ALSA/Pulse(리눅스)**: 실장 시 `/dev/snd` 마운트, `audio` 그룹 권한, `--privileged` 없이 권한 세팅 필요
* **실시간성**: 컨테이너에 `CAP_SYS_NICE`/`rtprio` 등 낮은 레이턴시 튜닝이 필요할 수 있음

---

# 운영 체크리스트(질문형, 핵심만)

* [ ] **STT 엔진 엔드포인트**를 환경변수로 추상화했나? (맥=host.docker.internal, 리눅스=서비스명)
* [ ] **모델 파일을 이미지/볼륨에 오프라인 내장**했나? (운영 반입 시 외부 다운로드 X)
* [ ] **5090 GPU에 CUDA 런타임/드라이버·nvidia-container-toolkit** 설치 확인했나?
* [ ] **16채널·2시간 부하 테스트**(RTF<1, GPU 메모리 여유) 결과를 수집했나?
* [ ] **시간 동기화/타임스탬프 기준**(컨테이너 TZ/NTP 대안) 맞췄나?
* [ ] **로그/메트릭**(GPU·CPU·I/O)와 **폴백 경로**(장애 시 배치 전사) 마련했나?

---

# 추천 “첫 주 세팅” 순서 (가장 빠른 길)

1. 맥에서 **컨테이너(브로커·API·후처리)** 올리고, **호스트 whisper.cpp(Core ML)** 를 HTTP 서버로 띄워 **엔드투엔드** 파이프라인 확인
2. **리눅스 서버**에 GPU 이미지(`stt-gpu:amd64-cuda`) 빌드/배포 → 동일 API로 교체 테스트
3. **실전 입력**(멀티채널 WAV 또는 RTP) 붙이고, **VAD 튜닝**→ 레이턴시/정확도 맞추기
4. 필요하면 **화자분리 컨테이너** 추가 → 채널분리와 비교 후 채택 결정
5. **에어갭용 번들**(이미지 tar + 모델 + compose 파일) 만들어 반입 리허설

---

원하면 위 구성을 **템플릿 리포(폴더 구조 + 두 가지 Dockerfile + compose 2종 + 샘플 API 서버)** 형태로 바로 만들어줄게.
운영 환경에서 **오디오 입력이 채널별 분리인지(최선)**, \*\*혼합 한두 채널인지(화자분리 필요)\*\*만 알려주면 그에 맞춰 세팅안을 바로 찍어줄게.
