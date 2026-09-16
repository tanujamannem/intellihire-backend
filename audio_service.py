import os
import json
import queue
import threading

import websocket
from dotenv import load_dotenv


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    raise RuntimeError(
        "DEEPGRAM_API_KEY is missing from environment variables."
    )


# =========================================================
# STATE
# =========================================================

_audio_running = False

_audio_transcript = ""
_final_transcript = ""
_audio_error = ""

_audio_lock = threading.Lock()

_audio_queue = queue.Queue(maxsize=200)

_stop_event = threading.Event()

_ws = None

_audio_thread = None


# =========================================================
# DEEPGRAM CONNECTION
# =========================================================

def connect_deepgram():

    url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-3"
        "&language=en-IN"
        "&interim_results=true"
        "&smart_format=true"
        "&punctuate=true"
    )

    print()
    print("Connecting to Deepgram...")

    ws = websocket.create_connection(
        url,
        header=[
            "Authorization: Token "
            + DEEPGRAM_API_KEY
        ],
        timeout=None
    )

    print("Deepgram connected.")

    return ws


# =========================================================
# RECEIVE TRANSCRIPT
# =========================================================

def receive_from_deepgram(ws):

    global _audio_transcript
    global _final_transcript
    global _audio_error

    print()
    print("=" * 70)
    print("DEEPGRAM TRANSCRIPTION ACTIVE")
    print("=" * 70)

    try:

        while not _stop_event.is_set():

            try:
                message = ws.recv()

            except Exception as e:

                if not _stop_event.is_set():

                    _audio_error = repr(e)

                    print(
                        "Deepgram receive error:",
                        repr(e)
                    )

                break

            if not message:
                continue

            try:

                data = json.loads(message)

            except Exception:

                continue

            channel = data.get("channel")

            if not channel:
                continue

            alternatives = channel.get(
                "alternatives",
                []
            )

            if not alternatives:
                continue

            alternative = alternatives[0]

            text = alternative.get(
                "transcript",
                ""
            ).strip()

            if not text:
                continue

            is_final = data.get(
                "is_final",
                False
            )

            with _audio_lock:

                if is_final:

                    if _final_transcript:

                        _final_transcript += (
                            " " + text
                        )

                    else:

                        _final_transcript = text

                    _audio_transcript = (
                        _final_transcript
                    )

                else:

                    if _final_transcript:

                        _audio_transcript = (
                            _final_transcript
                            + " "
                            + text
                        )

                    else:

                        _audio_transcript = text

            if is_final:

                print(
                    "CANDIDATE:",
                    _audio_transcript
                )

    except Exception as e:

        if not _stop_event.is_set():

            _audio_error = repr(e)

            print(
                "Deepgram receiver error:",
                repr(e)
            )


# =========================================================
# SEND AUDIO TO DEEPGRAM
# =========================================================

def send_audio_to_deepgram(ws):

    global _audio_error

    print(
        "Starting Deepgram audio sender..."
    )

    try:

        while not _stop_event.is_set():

            try:

                audio_data = _audio_queue.get(
                    timeout=0.5
                )

            except queue.Empty:

                continue

            if not audio_data:
                continue

            try:

                ws.send(
                    audio_data,
                    opcode=websocket.ABNF.OPCODE_BINARY
                )

            except Exception as e:

                if not _stop_event.is_set():

                    _audio_error = repr(e)

                    print(
                        "Deepgram send error:",
                        repr(e)
                    )

                break

    except Exception as e:

        if not _stop_event.is_set():

            _audio_error = repr(e)

            print(
                "Audio sender error:",
                repr(e)
            )


# =========================================================
# AUDIO WORKER
# =========================================================

def audio_worker():

    global _audio_running
    global _ws

    try:

        _ws = connect_deepgram()

        receiver_thread = threading.Thread(
            target=receive_from_deepgram,
            args=(_ws,),
            daemon=True
        )

        receiver_thread.start()

        sender_thread = threading.Thread(
            target=send_audio_to_deepgram,
            args=(_ws,),
            daemon=True
        )

        sender_thread.start()

        print(
            "Browser audio service is ready."
        )

        while not _stop_event.is_set():

            _stop_event.wait(0.2)

    except Exception as e:

        if not _stop_event.is_set():

            global _audio_error

            _audio_error = repr(e)

            print(
                "Audio worker error:",
                repr(e)
            )

    finally:

        _audio_running = False

        cleanup_audio()


# =========================================================
# CLEANUP
# =========================================================

def cleanup_audio():

    global _ws

    if _ws is not None:

        try:

            _ws.send(
                json.dumps(
                    {
                        "type": "CloseStream"
                    }
                )
            )

        except Exception:

            pass

        try:

            _ws.close()

        except Exception:

            pass

        _ws = None


# =========================================================
# START AUDIO
# =========================================================

def start_audio():

    global _audio_thread
    global _audio_running
    global _audio_transcript
    global _final_transcript
    global _audio_error

    with _audio_lock:

        if _audio_running:

            return {
                "success": True,
                "running": True,
                "message": "Candidate audio already running.",
                "transcript": _audio_transcript
            }

        _audio_transcript = ""
        _final_transcript = ""
        _audio_error = ""

        while not _audio_queue.empty():

            try:

                _audio_queue.get_nowait()

            except queue.Empty:

                break

        _stop_event.clear()

        _audio_running = True

    _audio_thread = threading.Thread(
        target=audio_worker,
        daemon=True
    )

    _audio_thread.start()

    return {
        "success": True,
        "running": True,
        "message": "Browser audio service started.",
        "transcript": ""
    }


# =========================================================
# RECEIVE BROWSER AUDIO CHUNK
# =========================================================

def add_audio_chunk(audio_data: bytes):

    if not audio_data:

        return {
            "success": False,
            "message": "Empty audio chunk."
        }

    if not _audio_running:

        return {
            "success": False,
            "message": "Audio service is not running."
        }

    try:

        _audio_queue.put_nowait(
            audio_data
        )

    except queue.Full:

        try:
            _audio_queue.get_nowait()
        except queue.Empty:
            pass

        try:

            _audio_queue.put_nowait(
                audio_data
            )

        except queue.Full:

            return {
                "success": False,
                "message": "Audio queue is full."
            }

    return {
        "success": True
    }


# =========================================================
# STOP AUDIO
# =========================================================

def stop_audio():

    global _audio_running
    global _ws

    print()
    print(
        "Stopping candidate audio..."
    )

    _stop_event.set()

    _audio_running = False

    if _ws is not None:

        try:
            _ws.close()
        except Exception:
            pass

    return {
        "success": True,
        "running": False,
        "message": "Candidate audio stopped."
    }


# =========================================================
# GET TRANSCRIPT
# =========================================================

def get_transcript():

    with _audio_lock:

        return {
            "success": True,
            "running": _audio_running,
            "transcript": _audio_transcript,
            "final_transcript": _final_transcript,
            "error": _audio_error
        }
