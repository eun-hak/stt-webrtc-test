import os
import uuid
import yaml
from fastapi import FastAPI, UploadFile, Form, Request, WebSocket, WebSocketDisconnect
import httpx
import uvicorn

# WebRTC
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from av.audio.resampler import AudioResampler
import av
import asyncio
import io
import numpy as np
import soundfile as sf
import time

STT_ENDPOINT = os.getenv("STT_ENDPOINT", "http://127.0.0.1:8081")
GLOSSARY_PATH = os.getenv("GLOSSARY_PATH", "/app/config/glossary.yaml")

# Load glossary once (best-effort)
try:
    with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
        GLOSSARY = yaml.safe_load(f) or {}
except Exception:
    GLOSSARY = {}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI()
sessions = {}
websockets_by_session: dict[str, set[WebSocket]] = {}

# serve static demo page under /demo
# 환경별 경로 자동 감지
import os
static_dir = "/app/static" if os.path.exists("/app/static") else "static"
app.mount("/demo", StaticFiles(directory=static_dir, html=True), name="static")

@app.get("/")
def root_redirect():
    return RedirectResponse(url="/demo/")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/sessions/create")
def create_session(name: str = Form(...)):
    sid = f"S{uuid.uuid4().hex[:8]}"
    sessions[sid] = {"name": name}
    return {"session_id": sid}

@app.post("/push")
async def push_audio(
    session_id: str = Form(...),
    channel_id: str = Form(...),
    start_ts: float = Form(...),
    audio: UploadFile = Form(...),
    initial_prompt: str = Form(""),
    lang: str = Form("auto"),
):
    stream_id = f"{session_id}_{channel_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"audio": (audio.filename, await audio.read(), audio.content_type or "application/octet-stream")}
        data = {
            "stream_id": stream_id,
            "start_ts": str(start_ts),
            "lang": lang,
            "initial_prompt": initial_prompt,
            "word_timestamps": "false",
            "vad": "true",
        }
        r = await client.post(f"{STT_ENDPOINT}/v1/transcribe-window", data=data, files=files)
        res = r.json()

    # Post-process text using glossary map
    mapping = (GLOSSARY or {}).get("map", {})
    for seg in res.get("segments", []):
        text = seg.get("text", "")
        for k, v in mapping.items():
            text = text.replace(k, v)
        seg["text"] = text

    return res

# --- WebRTC Minimal Signaling ---
pcs = set()

@app.post("/webrtc/offer")
async def webrtc_offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])  # type: ignore
    session_id = params.get("session_id", f"S{uuid.uuid4().hex[:6]}")
    channel_id = params.get("channel_id", "C01")
    stream_id = f"{session_id}_{channel_id}"

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        # 오디오 수신 → 16k 모노로 정규화 → 5초 창으로 STT 호출 → WS로 방송
        if track.kind != "audio":
            MediaBlackhole().addTrack(track)
            return

        async def consume_audio():
            resampler = AudioResampler(format="s16", layout="mono", rate=16000)
            buffer = bytearray()
            bytes_per_sec = 16000 * 2  # mono s16
            window_sec = 5.0
            start_ts = 0.0
            frame_count = 0
            last_info = time.time()

            while True:
                try:
                    frame = await track.recv()
                    if frame is None:
                        await asyncio.sleep(0.01)  # 10ms 대기로 CPU 부하 방지
                        continue
                    rframe = resampler.resample(frame)
                    # resampler가 list를 반환할 수 있으므로 처리
                    resampled_frames = rframe if isinstance(rframe, list) else [rframe]
                    for rf in resampled_frames:
                        # to_ndarray: shape (channels, samples) int16
                        pcm = rf.to_ndarray().tobytes()
                        buffer.extend(pcm)
                    frame_count += 1
                    now = time.time()
                    if now - last_info >= 1.0:
                        info_msg = {"type": "info", "message": f"frames={frame_count}, buffer_sec={len(buffer)/bytes_per_sec:.2f}"}
                        await broadcast_transcript(session_id, info_msg)
                        print(f"[webrtc] {stream_id} {info_msg['message']}")
                        last_info = now
                    # 윈도우 처리
                    while len(buffer) >= int(bytes_per_sec * window_sec):
                        chunk = bytes(buffer[: int(bytes_per_sec * window_sec)])
                        del buffer[: int(bytes_per_sec * window_sec)]
                        # WAV 인메모리 생성
                        bio = io.BytesIO()
                        data_i16 = np.frombuffer(chunk, dtype=np.int16)
                        sf.write(bio, data=data_i16, samplerate=16000, format="WAV", subtype="PCM_16")
                        bio.seek(0)
                        # STT 호출
                        async with httpx.AsyncClient(timeout=60) as client:
                            files = {"audio": (f"{channel_id}.wav", bio.read(), "audio/wav")}
                            data = {
                                "stream_id": stream_id,
                                "start_ts": str(start_ts),
                                "lang": "auto",
                                "initial_prompt": "",
                                "word_timestamps": "false",
                                "vad": "true",
                            }
                            r = await client.post(f"{STT_ENDPOINT}/v1/transcribe-window", data=data, files=files)
                            if r.headers.get("content-type", "").startswith("application/json"):
                                payload = r.json()
                            else:
                                payload = {"type": "error", "message": "stt invalid response"}

                        # 용어 맵 적용 및 WS 브로드캐스트
                        mapping = (GLOSSARY or {}).get("map", {})
                        for seg in payload.get("segments", []):
                            text = seg.get("text", "")
                            for k, v in mapping.items():
                                text = text.replace(k, v)
                            seg["text"] = text

                        # 발화자 정보를 포함하여 브로드캐스트 - payload 이후에 speaker 설정
                        message_with_speaker = {"type": "final", **payload, "speaker": channel_id}
                        print(f"[debug] Broadcasting with speaker: {channel_id}, message keys: {list(message_with_speaker.keys())}")
                        await broadcast_transcript(session_id, message_with_speaker)
                        print(f"[stt] {stream_id} segments={len(payload.get('segments', []))} commit={payload.get('commit_point')}")
                        # 타임라인 이동
                        if payload.get("segments"):
                            start_ts = payload.get("commit_point", start_ts + window_sec)
                        else:
                            start_ts += window_sec
                except Exception as e:
                    print(f"[webrtc] Audio processing error: {e}")
                    await asyncio.sleep(0.1)  # 에러 시 잠시 대기
                    # 연결이 끊어진 경우 루프 종료
                    if "Connection" in str(e) or "closed" in str(e).lower():
                        break

        asyncio.create_task(consume_audio())
        # 트랙 수신 시작 알림
        print(f"[webrtc] track received: {stream_id} kind={track.kind}")
        asyncio.create_task(broadcast_transcript(session_id, {"type": "info", "message": f"track received: {channel_id}"}))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "session_id": session_id}


async def broadcast_transcript(session_id: str, message: dict):
    targets = websockets_by_session.get(session_id, set())
    if not targets:
        return
    dead = []
    for ws in targets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        targets.discard(ws)


@app.websocket("/ws/transcript")
async def ws_transcript(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session") or f"S{uuid.uuid4().hex[:6]}"
    group = websockets_by_session.setdefault(session_id, set())
    group.add(ws)
    try:
        await ws.send_json({"type": "info", "message": f"joined {session_id}"})
        while True:
            # 클라에서 오는 메시지는 소비하지 않음(하트비트 용도 가능)
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        group.discard(ws)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
