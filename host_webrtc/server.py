import io
import os
import time
import asyncio
import numpy as np
import soundfile as sf
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from av.audio.resampler import AudioResampler
import uvicorn

STT_ENDPOINT = os.getenv("STT_ENDPOINT", "http://127.0.0.1:8081")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"]
)

websockets_by_session: dict[str, set[WebSocket]] = {}
pcs = set()

# 정적 파일 서버 추가
app.mount("/demo", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
def root_redirect():
    return RedirectResponse(url="/demo/")

@app.get("/health")
def health():
    return {"ok": True}


async def broadcast_transcript(session_id: str, message: dict):
    print(f"[debug-broadcast-1] Broadcasting to session: {session_id}")
    print(f"[debug-broadcast-2] Message to broadcast: {message}")
    print(f"[debug-broadcast-3] Message speaker field: {message.get('speaker', 'NOT_FOUND')}")
    
    targets = websockets_by_session.get(session_id, set())
    print(f"[debug-broadcast-4] Found {len(targets)} WebSocket targets")
    
    if not targets:
        print(f"[debug-broadcast-5] No targets found, skipping broadcast")
        return
    
    dead = []
    for i, ws in enumerate(targets):
        try:
            print(f"[debug-broadcast-6] Sending to WebSocket {i+1}")
            await ws.send_json(message)
            print(f"[debug-broadcast-7] Successfully sent to WebSocket {i+1}")
        except Exception as e:
            print(f"[debug-broadcast-8] Failed to send to WebSocket {i+1}: {e}")
            dead.append(ws)
    
    for ws in dead:
        targets.discard(ws)
    
    print(f"[debug-broadcast-9] Broadcast completed, removed {len(dead)} dead connections")


@app.websocket("/ws/transcript")
async def ws_transcript(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session") or f"S{int(time.time())}"
    group = websockets_by_session.setdefault(session_id, set())
    group.add(ws)
    try:
        await ws.send_json({"type": "info", "message": f"joined {session_id}"})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        group.discard(ws)


@app.post("/webrtc/offer")
async def webrtc_offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])  # type: ignore
    session_id = params.get("session_id", f"S{int(time.time())}")
    channel_id = params.get("channel_id", "C01")
    stream_id = f"{session_id}_{channel_id}"

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind != "audio":
            MediaBlackhole().addTrack(track)
            return

        async def consume():
            resampler = AudioResampler(format="s16", layout="mono", rate=16000)
            buffer = bytearray()
            bytes_per_sec = 16000 * 2
            window_sec = 5.0
            start_ts = 0.0
            frame_count = 0
            last = time.time()

            while True:
                frame = await track.recv()
                if frame is None:
                    continue
                r = resampler.resample(frame)
                resampled_frames = r if isinstance(r, list) else [r]
                for rf in resampled_frames:
                    pcm = rf.to_ndarray().tobytes()
                    buffer.extend(pcm)
                frame_count += 1
                now = time.time()
                if now - last >= 1.0:
                    await broadcast_transcript(session_id, {"type":"info", "message": f"frames={frame_count}, buffer_sec={len(buffer)/bytes_per_sec:.2f}"})
                    print(f"[webrtc-host] {stream_id} frames={frame_count} buffer_sec={len(buffer)/bytes_per_sec:.2f}")
                    last = now

                while len(buffer) >= int(bytes_per_sec * window_sec):
                    chunk = bytes(buffer[: int(bytes_per_sec * window_sec)])
                    del buffer[: int(bytes_per_sec * window_sec)]
                    bio = io.BytesIO()
                    data_i16 = np.frombuffer(chunk, dtype=np.int16)
                    sf.write(bio, data=data_i16, samplerate=16000, format="WAV", subtype="PCM_16")
                    bio.seek(0)
                    print(f"[debug-1] Starting STT request for channel: {channel_id}")
                    async with httpx.AsyncClient(timeout=60) as client:
                        files = {"audio": (f"{channel_id}.wav", bio.read(), "audio/wav")}
                        data = {"stream_id": stream_id, "start_ts": str(start_ts), "lang": "auto", "initial_prompt": "", "word_timestamps": "false", "vad": "true"}
                        print(f"[debug-2] STT request data: {data}")
                        r = await client.post(f"{STT_ENDPOINT}/v1/transcribe-window", data=data, files=files)
                        payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"type":"error","message":"stt invalid"}
                        print(f"[debug-3] STT response payload: {payload}")
                    
                    # 발화자 정보를 포함하여 브로드캐스트 - payload 이후에 speaker 설정
                    print(f"[debug-4] Adding speaker field to payload")
                    message_with_speaker = {"type":"final", **payload, "speaker": channel_id}
                    print(f"[debug-5] Final message with speaker: {message_with_speaker}")
                    print(f"[debug-6] Message keys: {list(message_with_speaker.keys())}")
                    print(f"[debug-7] Speaker field value: {message_with_speaker.get('speaker', 'NOT_FOUND')}")
                    
                    print(f"[debug-8] Broadcasting to session: {session_id}")
                    await broadcast_transcript(session_id, message_with_speaker)
                    print(f"[debug-9] Broadcast completed")
                    print(f"[stt-host] {stream_id} segs={len(payload.get('segments',[]))} commit={payload.get('commit_point')}")
                    if payload.get("segments"):
                        start_ts = payload.get("commit_point", start_ts + window_sec)
                    else:
                        start_ts += window_sec

        asyncio.create_task(consume())
        asyncio.create_task(broadcast_transcript(session_id, {"type":"info","message":f"track received: {channel_id}"}))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "session_id": session_id}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8082)


