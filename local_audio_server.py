from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audio_service import (
    start_audio,
    stop_audio,
    get_transcript,
)

app = FastAPI(
    title="IntelliHire Local Audio Server"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://charming-cendol-100307.netlify.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "IntelliHire local Windows audio server is running"
    }


@app.post("/api/audio/start")
def audio_start():
    try:
        result = start_audio()
        return result
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@app.post("/api/audio/stop")
def audio_stop():
    try:
        result = stop_audio()
        return result
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/api/audio/transcript")
def audio_transcript():
    try:
        result = get_transcript()
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "local_audio_server:app",
        host="127.0.0.1",
        port=8001,
        reload=False
    )
