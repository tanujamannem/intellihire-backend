import os
import json
import queue
import threading
import time

import pyaudiowpatch as pyaudio
import websocket

from dotenv import load_dotenv


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    raise RuntimeError(
        "DEEPGRAM_API_KEY is missing from .env"
    )


# =========================================================
# STATE
# =========================================================

_audio_queue = queue.Queue()

_stop_event = threading.Event()

_audio_thread = None
_sender_thread = None
_receiver_thread = None

_audio_running = False

_audio_lock = threading.Lock()

_audio_transcript = ""
_final_transcript = ""

_audio_error = ""

_ws = None
_pyaudio = None
_stream = None


# =========================================================
# FIND WINDOWS WASAPI LOOPBACK
# =========================================================

def find_wasapi_loopback_device():

    p = pyaudio.PyAudio()

    try:

        wasapi_info = p.get_host_api_info_by_type(
            pyaudio.paWASAPI
        )

        default_speaker = p.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )

        selected = None

        print()
        print("=" * 70)
        print("SEARCHING FOR WASAPI LOOPBACK DEVICE")
        print("=" * 70)

        for i in range(p.get_device_count()):

            device = p.get_device_info_by_index(i)

            if device["hostApi"] != wasapi_info["index"]:
                continue

            print(
                f"[{i}] {device['name']} | "
                f"Inputs: {device['maxInputChannels']} | "
                f"Outputs: {device['maxOutputChannels']}"
            )

            name = device["name"].lower()

            if (
                device["maxInputChannels"] > 0
                and "loopback" in name
            ):

                speaker_name = (
                    default_speaker["name"].lower()
                )

                if (
                    speaker_name in name
                    or name in speaker_name
                ):
                    selected = device

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        if selected is None:

            for i in range(p.get_device_count()):

                device = p.get_device_info_by_index(i)

                if device["hostApi"] != wasapi_info["index"]:
                    continue

                if (
                    device["maxInputChannels"] > 0
                    and "loopback" in device["name"].lower()
                ):

                    selected = device
                    break

        if selected is None:

            raise RuntimeError(
                "WASAPI loopback device was not found."
            )

        print()
        print("=" * 70)
        print("SELECTED WASAPI LOOPBACK DEVICE")
        print("=" * 70)
        print("Name:", selected["name"])
        print("Index:", selected["index"])
        print("Sample rate:", selected["defaultSampleRate"])
        print("Input channels:", selected["maxInputChannels"])
        print("=" * 70)

        return p, selected

    except Exception:

        p.terminate()

        raise


# =========================================================
# AUDIO CALLBACK
# =========================================================

def audio_callback(
    in_data,
    frame_count,
    time_info,
    status
):

    if status:
        print("Audio status:", status)

    if in_data and not _stop_event.is_set():

        try:
            _audio_queue.put_nowait(in_data)

        except queue.Full:

            try:
                _audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                _audio_queue.put_nowait(in_data)
            except queue.Full:
                pass

    return None, pyaudio.paContinue


# =========================================================
# DEEPGRAM RECEIVER
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

            message = ws.recv()

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

            text = alternatives[0].get(
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

            print(
                "TRANSCRIPT:",
                _audio_transcript
            )

    except Exception as e:

        if not _stop_event.is_set():

            _audio_error = str(e)

            print(
                "Deepgram receive error:",
                e
            )


# =========================================================
# SEND AUDIO TO DEEPGRAM
# =========================================================

def send_audio_to_deepgram(ws):

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

                    _audio_error = str(e)

                    print(
                        "Deepgram send error:",
                        e
                    )

                break

    except Exception as e:

        if not _stop_event.is_set():

            _audio_error = str(e)

            print(
                "Audio sender error:",
                e
            )


# =========================================================
# CONNECT DEEPGRAM
# =========================================================

def connect_deepgram(
    sample_rate,
    channels
):

    url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-3"
        "&language=en-IN"
        "&encoding=linear16"
        f"&sample_rate={sample_rate}"
        f"&channels={channels}"
        "&interim_results=true"
        "&smart_format=true"
        "&punctuate=true"
    )

    print()
    print(
        "Connecting to Deepgram..."
    )

    ws = websocket.create_connection(
        url,
        header=[
            f"Authorization: Token "
            f"{DEEPGRAM_API_KEY}"
        ],
        timeout=None
    )

    print(
        "Deepgram connected."
    )

    return ws


# =========================================================
# AUDIO WORKER
# =========================================================

def audio_worker():

    global _audio_running
    global _ws
    global _pyaudio
    global _stream
    global _sender_thread
    global _receiver_thread
    global _audio_error

    try:

        # -------------------------------------------------
        # FIND LOOPBACK
        # -------------------------------------------------

        _pyaudio, device = (
            find_wasapi_loopback_device()
        )

        device_index = int(
            device["index"]
        )

        sample_rate = int(
            device["defaultSampleRate"]
        )

        channels = min(
            2,
            int(device["maxInputChannels"])
        )

        if channels < 1:
            channels = 1

        print()
        print("=" * 70)
        print("OPENING WASAPI LOOPBACK")
        print("=" * 70)
        print("Device:", device["name"])
        print("Index:", device_index)
        print("Sample rate:", sample_rate)
        print("Channels:", channels)
        print("=" * 70)

        # -------------------------------------------------
        # CONNECT DEEPGRAM
        # -------------------------------------------------

        _ws = connect_deepgram(
            sample_rate,
            channels
        )

        # -------------------------------------------------
        # OPEN AUDIO STREAM
        # -------------------------------------------------

        _stream = _pyaudio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024,
            stream_callback=audio_callback
        )

        _stream.start_stream()

        print()
        print(
            "WASAPI LOOPBACK ACTIVE"
        )
        print(
            "Listening to candidate audio..."
        )

        # -------------------------------------------------
        # DEEPGRAM RECEIVER
        # -------------------------------------------------

        _receiver_thread = threading.Thread(
            target=receive_from_deepgram,
            args=(_ws,),
            daemon=True
        )

        _receiver_thread.start()

        # -------------------------------------------------
        # DEEPGRAM SENDER
        # -------------------------------------------------

        _sender_thread = threading.Thread(
            target=send_audio_to_deepgram,
            args=(_ws,),
            daemon=True
        )

        _sender_thread.start()

        # -------------------------------------------------
        # KEEP WORKER ALIVE
        # -------------------------------------------------

        while (
            not _stop_event.is_set()
            and _stream is not None
            and _stream.is_active()
        ):

            time.sleep(0.2)

    except Exception as e:

        _audio_error = str(e)

        print()
        print("=" * 70)
        print("AUDIO SERVICE ERROR")
        print("=" * 70)
        print(str(e))
        print("=" * 70)

    finally:

        _audio_running = False

        cleanup_audio()


# =========================================================
# CLEANUP
# =========================================================

def cleanup_audio():

    global _stream
    global _ws
    global _pyaudio

    # -----------------------------------------------------
    # AUDIO STREAM
    # -----------------------------------------------------

    if _stream is not None:

        try:
            if _stream.is_active():
                _stream.stop_stream()
        except Exception:
            pass

        try:
            _stream.close()
        except Exception:
            pass

        _stream = None

    # -----------------------------------------------------
    # DEEPGRAM
    # -----------------------------------------------------

    if _ws is not None:

        try:
            _ws.send(
                json.dumps({
                    "type": "CloseStream"
                })
            )
        except Exception:
            pass

        try:
            _ws.close()
        except Exception:
            pass

        _ws = None

    # -----------------------------------------------------
    # PYAUDIO
    # -----------------------------------------------------

    if _pyaudio is not None:

        try:
            _pyaudio.terminate()
        except Exception:
            pass

        _pyaudio = None


# =========================================================
# START AUDIO
# =========================================================

def start_audio():

    global _audio_thread
    global _audio_running
    global _audio_transcript
    global _final_transcript
    global _audio_error
    global _stop_event

    with _audio_lock:

        if _audio_running:

            return {
                "success": True,
                "running": True,
                "message": "Candidate audio already running."
            }

        # -------------------------------------------------
        # RESET
        # -------------------------------------------------

        while not _audio_queue.empty():

            try:
                _audio_queue.get_nowait()
            except queue.Empty:
                break

        _audio_transcript = ""
        _final_transcript = ""
        _audio_error = ""

        _stop_event.clear()

        _audio_running = True

    # -----------------------------------------------------
    # START WORKER
    # -----------------------------------------------------

    _audio_thread = threading.Thread(
        target=audio_worker,
        daemon=True
    )

    _audio_thread.start()

    return {
        "success": True,
        "running": True,
        "message": "WASAPI candidate audio started."
    }


# =========================================================
# STOP AUDIO
# =========================================================

def stop_audio():

    global _audio_running

    _stop_event.set()

    _audio_running = False

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
            "error": _audio_error,
        }