# Worklog (시간 역순)

## 2025-09-04 22:49 KST
- **사용자 지시**: "이 프로젝트 코드베이스를 git repository 만들자. 00-docs를 읽어 README.md와 초기 커밋 메시지를 작성하자."
- **수행 내용**:
  - 00-docs 전반 요약을 바탕으로 `README.md` 작성(아키텍처/API/시작/데모/체크리스트).
  - `.gitignore` 추가, Git 초기화 및 최초 커밋 작업 준비.
- **산출물**: `README.md`

## 2025-09-04 22:39 KST
- **사용자 지시**: "시간 표시 제로패딩, 솔루션명/저작권 반영. 그리고 전체 작업 여정 정리."
- **수행 내용**:
  - 데모 UI 개선: 타임코드 `mm:ss.mmm`/`hh:mm:ss.mmm` 제로패딩, 하단 `2025 © SimSimi Inc.` 표기.
  - 시그널링/WS를 호스트(8082)로 전환, 강력 새로고침 가이드.
  - WebRTC 경로 정상화 확인.
- **메모(핵심 여정)**:
  1) 초기 파일 전사 파이프라인 구축(맥 개발→GPU 운영 설계, `04-blueprint.md`, `05-1-cycle-macbook.md`).
  2) Docker dev 구성(api/stt/postprocess/glossary) 및 샘플 /push 성공.
  3) WebRTC 최소 스펙 설계(`06-WebRTC-demo.md`): 업(WebRTC) + 다운(WS/SSE) 결정.
  4) 컨테이너 내 aiortc로 시도 → macOS Desktop 네트워크 제약(UDP 경로)로 미디어 프레임 미수신.
  5) 옵션 2 선택: **호스트 WebRTC 서버(8082)** 분리. 데모는 컨테이너(정적) 유지.
  6) 호스트 STT 서버는 faster-whisper CPU로 가동, STT 엔드포인트를 127.0.0.1:8081로 고정.
  7) 버그 수정 다수: `python-multipart` 누락, float64→float32, VAD 타입, aiortc `track.recv()` 사용, resampler 반환 리스트 처리, 변수명 충돌(frames) 수정.
  8) 최종: 브라우저 콘솔에 frames/buffer_sec, 서버 로그에 [webrtc-host]/[stt-host] 출력 확인. 실시간 전사 동작.
- **산출물**: 데모 페이지(UI 개선), 호스트 WebRTC 서버(8082), 워크플로 문서/구성들 업데이트

---
## 2025-09-04 20:58 KST
- **사용자 지시**: "06-WebRTC-demo.md 에 위 계획을 정리해 두고 작업 진행하자."
- **수행 내용**:
  - `06-WebRTC-demo.md` 작성(최소 스펙: WebRTC 업스트림 + WS/SSE 다운스트림, 이벤트 스키마, 작업 항목).
  - 린트 확인(이상 없음).
- **산출물**: `06-WebRTC-demo.md`

---
## 2025-09-04 12:24 KST
- **사용자 지시**: "다른 오디오 테스트 해 보자... sample-songdaegwan-01.wav"
- **수행 내용**:
  - `sample-songdaegwan-01.wav` → 16kHz 모노 변환 → `/push` 실행.
  - 응답 수신: 0.0–25.48초 구간 다수 세그먼트 전사 확인(한국어 정상 인식).
- **산출물**: `sample-songdaegwan-01-16k.wav`, `/tmp/push_songdaegwan.json`

`$ sid=$(curl -s -F 'name=TEST' http://localhost:8080/sessions/create | sed -n 's/.*"session_id":"\([^"]\+\)".*/\1/p'); curl -s -F "session_id=$sid" -F "channel_id=C01" -F "start_ts=0" -F "audio=@/Users/sijay/git/akain-whisper-test/sample-songdaegwan-01-16k.wav;type=audio/wav" -F "initial_prompt=Alpha-1, Blue-2, 알파원, 블루투" -
F "lang=auto" http://localhost:8080/push | tee /tmp/push_songdaegwan.json | cat`
~~~json
{"stream_id":"_C01","segments":[{"start":0.0,"end":3.9,"text":" 가수로의 자리를 보장받을 수 없는데","conf":-0.2707116239600
7115},{"start":3.9,"end":5.64,"text":" 어떻게 와서 노래를 했냐","conf":-0.27071162396007115},{"start":5.64,"end":7.24,
"text":" 노래가 좋은 걸 어떻게","conf":-0.27071162396007115},{"start":7.24,"end":9.68,"text":" 노래를만 부르고 부르게 해주면","con
f":-0.27071162396007115},{"start":9.68,"end":11.72,"text":"  나는 살견노라고","conf":-0.27071162396007115},{"start"
:11.72,"end":13.36,"text":" 나는 행복하다고","conf":-0.27071162396007115},{"start":13.36,"end":15.44,"text":" 나는 생각
하기 때문에","conf":-0.27071162396007115},{"start":15.44,"end":19.04,"text":" 가수는 얼마나 속이 없는 사람들인지 알아?","conf":-0.
27071162396007115},{"start":19.04,"end":21.6,"text":" 내일을 몰라 가수는","conf":-0.27071162396007115},{"start":21.6
,"end":24.48,"text":" 노래가 좋아서 미친듯이 하는 거야","conf":-0.27071162396007115},{"start":24.48,"end":25.48,"text":" 근
데 내가 누구예요?","conf":-0.27071162396007115}],"commit_point":25.48}
~~~

### 질문
> 지금은 small 이었던 건가? 맥북에서 medium/large-v3 돌아가긴 하나?

- **네, 지금은 small입니다.** `host_stt/server.py`에서 `MODEL_DIR="small"`로 설정돼 있습니다.
- **맥북에서 medium/large-v3 가능**합니다.
  - 현재 방식(faster-whisper CPU, `compute_type=int8`)으로도 동작하지만, 속도는 느립니다. 다운로드/메모리도 커집니다(대략 medium ≈ 1.5GB+, large-v3 ≈ 3GB+).
  - 맥에서는 보통 **whisper.cpp + Metal**이 medium/large-v3 실행 체감이 더 좋습니다. 빠른 반복/실시간성 기대 시 whisper.cpp 권장, 정확도만 보려면 지금 세팅에서 모델만 바꿔도 됩니다.

원하시면 바로 `MODEL_DIR=medium`(또는 `large-v3`)로 바꿔 서버 재시작해 비교 테스트 진행하겠습니다.

> 어차피 맥에서 얼마나 속도가 빠른지는 중요하지 않고, 실제 운용할 리눅스 서버에서 성능이 중요한데 16 개 채널에서 들어오는 걸 5090 서버가 문제 없이 잘 처리할까? 그런 건 맥에서 테스트 한 거 가지고는 추정 불가능하지?

- **요약**: 맥 성능으로는 5090 서버의 16채널 처리 가능 여부를 신뢰성 있게 추정하기 어렵습니다. 실제 CUDA/Tensor Core, 메모리 대역, 드라이버/RTX 최적화 등 변수가 달라서 반드시 서버에서 부하 테스트가 필요합니다.

- **현실적 기대치(가이드)**:
  - `large-v3 fp16`: 16채널 동시 실시간은 빡셈. VAD로 말하는 구간만 보내고 큐잉하면 가능할 수도 있으나 여유 작지 않음.
  - `large-v3 int8_float16` 또는 `medium fp16/int8_float16`: 16채널 실시간 운영 현실적. VAD(말하는 구간만) + 5–10s 창/20–30% 오버랩 + 단일 모델 인스턴스 큐잉.
  - 채널이 16개라도 동시 발화율이 100%가 아님(보통 20–50%). 이 전제를 활용하면 처리량이 크게 올라감.

- **판단 기준**:
  - 핵심 지표는 RTF(Real-Time Factor). 채널별 RTF×동시 발화 채널 수의 합이 1 미만이면 실시간 유지.
  - 예: 채널별 RTF≈0.25, 동시 발화 4채널이면 합 1.0 → 실시간 경계. RTF↓(양자화/윈도우 튜닝) 또는 동시성↓(큐잉)로 여유 확보.

- **다음 단계(권장 테스트)**:
  - 5090 서버에 GPU 이미지로 배포(faster-whisper CUDA, `float16`→부하 시 `int8_float16`).
  - 16채널·2시간 소크 테스트: RTF, GPU/VRAM, 실패율, 지연, 큐 대기시간 수집.
  - 파라미터 스윕: 모델 크기(`medium`↔`large-v3`), `compute_type`, 창/오버랩, VAD 임계값.
  - 기준: RTF 합<1, 드롭 0%, VRAM 여유(>10–20%), 평균 지연 목표 내.

원하시면 바로 GPU용 compose와 Dockerfile 정리해서 서버에서 부하 테스트 스크립트까지 준비하겠습니다.

---

## 2025-09-04 10:55 KST
- **사용자 지시**: "오키. 옵션 B로 하자."
- **수행 내용**:
  - dev compose에서 API의 `STT_ENDPOINT`를 `http://host.docker.internal:8081`로 전환.
  - whisper.cpp 호스트 실행 준비(클론/빌드 및 8081 HTTP 래퍼 예정).
- **산출물**: `docker/docker-compose.dev.yml` 업데이트


---

## 2025-09-04 10:41 KST
- **사용자 지시**: "오케이 진행하자"
- **수행 내용**:
  - 테스트용 16kHz 모노 WAV(3초) 생성.
  - `/sessions/create`로 세션 발급 → `/push` 호출하여 엔드투엔드 검증.
  - 응답 확인: `segments[0].text = [stub:sample16k.wav]`, `commit_point ≈ 3.0s`.
- **산출물**: `sample16k.wav`, `/tmp/session.json`, `/tmp/push.json`

### 질문
> 일단 질문에 답변해라.
sample16k.wav 는 재생하니까 삐 소리만 나네? 
session.json 은 어디에 쓰는 거냐. 
push.json 의 text 가 [stub:sample16k.wav] 인 거는 무슨 의미지? 
지금 사용하는 모델은 whisper.cpp ? 얘는 large/small 이런 이름이 없는가?
실제 오디오 파일로 테스트 해 보긴 해봐야겠는데?


- **sample16k.wav이 삐 소리인 이유**: 파이프라인 연결만 확인하려고 1 kHz 사인파(3초)를 생성한 테스트 음원입니다. 음성 인식 품질 검증용이 아니라 “엔드투엔드가 돈다”를 확인하려는 용도예요.

- **session.json 용도**: `/sessions/create`로 받은 `session_id`를 저장해 `/push` 호출에 쓰기 위한 임시 값입니다. 현재는 `/tmp/session.json`에 저장했고, 이후 세션별 결과를 모으거나 반복 호출에 재사용할 때 편합니다.

- **push.json의 text가 “[stub:sample16k.wav]”인 의미**: 지금 STT는 “모의 서버(stub)”입니다. 실제 인식 대신 파일명을 표시해 파이프라인이 정상 동작함을 보여주는 자리표시자 텍스트예요. 실제 모델로 바꾸면 여기에 전사가 들어갑니다.

- **현재 사용 중인 모델**: whisper.cpp도 faster-whisper도 아직 “사용 안 함”(모의 STT만 동작).  
  - Whisper 모델 크기들은 존재합니다: `tiny/base/small/medium/large-v3`.  
  - whisper.cpp는 보통 `ggml-*.bin`(또는 `gguf-*.gguf`) 형태로 로드합니다. 예: `ggml-small.bin`, `ggml-large-v3.bin`.

- **실제 오디오로 테스트**: 가능해요. 다만 지금은 stub라 결과가 여전히 “[stub:파일명]”으로 나옵니다. “실제 전사”를 보려면 아래 둘 중 하나로 전환해야 합니다.
  - 옵션 A: STT 컨테이너를 faster-whisper(CT2, CPU)로 교체해 Docker만으로 실행
  - 옵션 B: 맥 호스트에서 whisper.cpp 실행 후 `STT_ENDPOINT=http://host.docker.internal:8081`로 API가 붙도록 변경

원하는 옵션 알려주시면 바로 STT를 실제 모델로 전환하고, 같은 방법으로 “실제 오디오 파일”을 푸시해 전사 결과까지 확인해드리겠습니다.


### 다시 질문 
> 아까는 옵션 B 를 계획했던 거 같은데? 옵션 A 를 현재 맥북에서 할 수 있는거냐? 뭐가 더 좋은거냐?

- **맞아요, 옵션 B 계획**: 초기 계획은 맥(M1)에서 호스트 `whisper.cpp`(Core ML/Metal)로 STT를 돌리고 컨테이너들은 `host.docker.internal`로 붙이는 방식이었습니다.
- **옵션 A(맥에서 가능?)**: 가능합니다. 다만 맥 Docker에서는 CUDA/Metal이 없어 faster-whisper가 CPU로만 동작합니다. 성능이 느리고 전력 소모가 큽니다.
- **무엇이 더 좋은가(맥 개발)**: **옵션 B가 우수**합니다. `whisper.cpp + Core ML/Metal`이 훨씬 빠르고(실시간에 근접) 개발 회전이 좋습니다. 단, 호스트 프로세스를 따로 띄워야 합니다.
- **프로덕션 관점**: 리눅스 5090 GPU에서는 **옵션 A(컨테이너 + CUDA)**가 정답입니다. 운영/배포/에어갭 모두 용이합니다.
- **실제 오디오 테스트**: 당장 결과 확인이 목적이면
  - 빠른 품질·속도 확인: 맥에서 옵션 B로 진행(권장)
  - 도커 일관성 우선: 맥에서 옵션 A(CPU)로도 가능하지만 느립니다

원하시면 바로 옵션 B로 전환해 실제 오디오 파일 전사 테스트까지 진행하겠습니다.

---

## 2025-09-04 10:39 KST
- **사용자 지시**: "docker 기반으로 다시 진행. 비-docker 흔적 정리하고 compose(dev)로 가자."
- **수행 내용**:
  - dev compose에 STT 컨테이너 포함 구조로 수정(`stt`=FastAPI 스텁, 8081).
  - Docker Desktop 기동 및 데몬 확인 후 `docker compose up -d --build` 성공.
  - API 의존성 보완(`python-multipart`)하여 재빌드, `/health` 정상 응답 확인.
  - STT `/health` 정상.
- **산출물**: `docker/docker-compose.dev.yml` 업데이트, API 이미지 재빌드

---

## 2025-09-04 10:33 KST
- **사용자 지시**: "docker 를 안 띄워 놨었네. docker 기반으로 가기로 했으니 비-docker 계획과 그 실행 시도로 인해 진행된 거 되돌리고 다시 docker 쪽으로 방향잡아서 진행해. worklog.md 쓰는 rule 은 시간 역순으로 하는 걸로 정의 다시 해."
- **수행 내용**:
  - 워크로그 규칙을 '시간 역순(최신 상단)+분 단위'로 재정의(메모리 반영).
  - 비-Docker 경로를 취소하고 Docker 경로로 전환 계획 수립.
- **산출물**: 규칙 업데이트

---

## 2025-09-04 10:25 KST
- **사용자 지시**: "어 rule 에서 worklog.md 에 시간을 분 단위까지 기록하도록 변경하고. 다음 단계 실행하자."
- **수행 내용**:
  - 워크로그 규칙을 '분 단위'로 업데이트(메모리 반영).
  - 현재 시각 확인 및 워크로그 포맷을 분 단위 헤더로 개정.
  - dev 스캐폴딩 생성 준비(디렉터리 생성 및 파일 작성 계획 수립).
- **산출물**: 규칙 업데이트

---

## 2025-09-04 10:28 KST
- **사용자 지시**: "다음 단계 실행하자."
- **수행 내용**:
  - dev 스캐폴딩 생성: `docker/docker-compose.dev.yml`, `docker/api.Dockerfile` 추가.
  - API 최소 구현 추가: `services/api/main.py`, `services/api/requirements.txt` 생성.
  - 설정/스토리지: `config/glossary.yaml`, `storage/.gitkeep` 생성.
  - 린트 확인(일부 로컬 해석 경고는 컨테이너 내 설치로 해결 예정).
- **산출물**: dev compose, API, glossary, storage

---

## 2025-09-04 10:28 KST
- **사용자 지시**: "compose(dev)로 실행"
- **수행 내용**:
  - `docker compose up -d --build` 시도하였으나 Docker 데몬 연결 실패(`docker.sock`).
  - 경로 전환: 로컬(비-Docker) 실행 플랜으로 변경.
- **산출물**: 실행 경로 변경(기록)

---

## 2025-09-04
- **사용자 지시**: "진행해. 지금부터 모든 작업을 worklog.md 에 시간 역순으로 쌓자. ... rule 에다가 넣어 두자."
- **수행 내용**:
  - 작업 로그 규칙을 메모리에 저장(모든 작업 시 `worklog.md` 갱신, 최신 항목 상단, 현지 시각 기준 가능 시 타임스탬프 포함).
  - `worklog.md` 파일 생성 및 초기 로그 작성.
- **산출물**: `worklog.md`

---

## 2025-09-04
- **사용자 지시**: "이 폴더의 3개 md 를 순서대로 읽어보고 04-blueprint.md 문서와 05-1-cycle-macbook.md 를 작성한 뒤, 작업 진행하자."
- **수행 내용**:
  - `01-the-first-question.md`, `02-the-second-question.md`, `03-the-third-question.md`를 읽고 핵심 맥락 정리.
  - `04-blueprint.md` 초안 작성(아키텍처, API 계약, 이행 전략, 체크리스트 등).
  - `05-1-cycle-macbook.md` 초안 작성(맥 개발 1주기 실행 계획, DoD, 튜닝 포인트 등).
  - 문서 린트 확인(이상 없음).
- **산출물**: `04-blueprint.md`, `05-1-cycle-macbook.md`
