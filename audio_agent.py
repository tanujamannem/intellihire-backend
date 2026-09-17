import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "local_audio_server:app",
        host="127.0.0.1",
        port=8001
    )
