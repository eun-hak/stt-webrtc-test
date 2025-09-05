

# 06) WebRTC 실시간 전사 데모 계획 (최소 스펙)

## 목표
- 내부망 시연용: 브라우저 마이크 → WebRTC(업스트림) → 서버 → 전사 → 결과를 클라이언트에 실시간 표시
- 복잡도 최소화: STUN/TURN/SFU 없이 단방향 업스트림, HTTP 시그널링 + WS/SSE 다운스트림

## 아키텍처(최소)
- 클라이언트(브라우저)
  - UI: [마이크 시작/정지], [상태], [실시간 전사 목록]
  - 시그널링: `createOffer()` → 서버 `POST /webrtc/offer` → answer 수신
  - 미디어: `getUserMedia({audio:true})` → `RTCPeerConnection` → `addTrack`
  - 결과 수신: `WebSocket /ws/transcript?session=...`(권장) 또는 `SSE /sse/transcript?session=...`
  - 렌더링: 파셜(기울임/회색), 커밋(고정/색상)

- 서버
  - 시그널링: `POST /webrtc/offer` → SDP answer 반환(내부망, STUN/TURN 생략)
  - WebRTC 처리: `aiortc` `ontrack`에서 Opus 수신 → 16 kHz 모노 변환 → VAD → 5–10초 창/20–30% 오버랩 → STT
  - STT: faster-whisper(개발=CPU, 운영=GPU) 스트리밍 옵션, initial_prompt/용어사전 적용
  - 다운스트림: 파셜/커밋을 JSON 이벤트로 WS/SSE 브로드캐스트(세션 단위)
  - 모니터링: 연결 수, 큐 길이, 평균 지연(ms), RTF

## 이벤트 스키마(권장)
- partial
```json
{"type":"partial","stream_id":"S1_C01","start":12.10,"end":13.50,"text":"..."}
```
- final
```json
{"type":"final","stream_id":"S1_C01","segments":[{"start":12.10,"end":14.00,"text":"...","conf":0.87}],"commit_point":14.0}
```
- info/error
```json
{"type":"info","message":"client connected"}
{"type":"error","message":"vad overflow"}
```

## 지연/품질 운영값(초안)
- 프레임 업로드 간격: 0.5–1.0초
- 창 길이: 5–10초, 오버랩: 20–30%
- 파셜 표시: 1–2초 내, 커밋: 3–5초 내
- VAD: WebRTC AEC/NS/AGC + 서버 VAD 임계값 튜닝

## 보안/인증(내부망)
- HTTP 시그널링/WS 가능(로컬/내부망). 필요시 `mkcert`로 HTTPS 간단 적용
- 브라우저 보안 컨텍스트: localhost는 http 허용, 내부망 도메인은 https 권장

## 작업 항목(실행)
1) aiortc 기반 최소 서버 구현(`/webrtc/offer`, `ontrack`) – 단일 세션 우선
2) STT 파이프라인 결합(윈도우링+VAD+faster-whisper)
3) WS(`/ws/transcript`) 또는 SSE(`/sse/transcript`) 구현
4) 클라이언트 HTML/JS(버튼·상태·표시)
5) dev compose/런치 스크립트 추가
6) 시연 리허설(지연/가독성 튜닝, 에러 토스트)

## 주의
- Whisper는 토큰 단위 초저지연 엔진이 아님 → 파셜/커밋 UX로 보완
- 다자/외부망 필요 시에만 STUN/TURN/SFU 확장 고려(Janus/mediasoup)
