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
# SETTINGS
# =========================================================

CHUNK_SIZE = 1024

_audio_queue = queue.Queue(maxsize=200)

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

    print()
    print("=" * 70)
    print("SEARCHING FOR WINDOWS SPEAKER WASAPI LOOPBACK")
    print("=" * 70)

    p = pyaudio.PyAudio()

    try:

        # -------------------------------------------------
        # Get WASAPI information
        # -------------------------------------------------

        wasapi_info = p.get_host_api_info_by_type(
            pyaudio.paWASAPI
        )

        print(
            "WASAPI Host API index:",
            wasapi_info["index"]
        )

        # -------------------------------------------------
        # Get Windows default speaker
        # -------------------------------------------------

        default_speaker = p.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )

        print(
            "Default Windows speaker:",
            default_speaker["name"]
        )

        print()
        print(
            "Searching for corresponding WASAPI loopback..."
        )
        print()

        selected = None

        # -------------------------------------------------
        # If default device itself is loopback
        # -------------------------------------------------

        if default_speaker.get(
            "isLoopbackDevice",
            False
        ):

            selected = default_speaker

        else:

            # -------------------------------------------------
            # PyAudioWPatch loopback devices
            # -------------------------------------------------

            for loopback in (
                p.get_loopback_device_info_generator()
            ):

                print(
                    f"[{loopback['index']}] "
                    f"{loopback['name']} | "
                    f"Inputs: "
                    f"{loopback['maxInputChannels']} | "
                    f"Outputs: "
                    f"{loopback['maxOutputChannels']}"
                )

                if (
                    default_speaker["name"]
                    in loopback["name"]
                ):

                    selected = loopback
                    break

        # -------------------------------------------------
        # Fallback: first usable loopback
        # -------------------------------------------------

        if selected is None:

            print()
            print(
                "Exact default speaker loopback "
                "not found."
            )

            print(
                "Searching for any usable loopback..."
            )

            for loopback in (
                p.get_loopback_device_info_generator()
            ):

                if int(
                    loopback.get(
                        "maxInputChannels",
                        0
                    )
                ) > 0:

                    selected = loopback

                    print(
                        "Using fallback loopback:",
                        loopback["name"]
                    )

                    break

        # -------------------------------------------------
        # No device
        # -------------------------------------------------

        if selected is None:

            raise RuntimeError(
                "Could not find a suitable "
                "Windows WASAPI speaker loopback device."
            )

        # -------------------------------------------------
        # Validate channels
        # -------------------------------------------------

        input_channels = int(
            selected.get(
                "maxInputChannels",
                0
            )
        )

        if input_channels <= 0:

            raise RuntimeError(
                "Selected WASAPI loopback has "
                "no input channels."
            )

        # -------------------------------------------------
        # Print selected device
        # -------------------------------------------------

        print()
        print("=" * 70)
        print("SELECTED WASAPI LOOPBACK DEVICE")
        print("=" * 70)

        print(
            "Name:",
            selected["name"]
        )

        print(
            "Index:",
            selected["index"]
        )

        print(
            "Sample rate:",
            selected["defaultSampleRate"]
        )

        print(
            "Input channels:",
            selected["maxInputChannels"]
        )

        print("=" * 70)
        print()

        return p, selected

    except Exception:

        try:
            p.terminate()
        except Exception:
            pass

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

        print(
            "Audio status:",
            status
        )

    if (
        in_data
        and not _stop_event.is_set()
    ):

        try:

            _audio_queue.put_nowait(
                in_data
            )

        except queue.Full:

            try:
                _audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                _audio_queue.put_nowait(
                    in_data
                )
            except queue.Full:
                pass

    return (
        None,
        pyaudio.paContinue
    )


# =========================================================
# CONNECT TO DEEPGRAM
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
            "Authorization: Token "
            + DEEPGRAM_API_KEY
        ],
        timeout=None
    )

    print(
        "Deepgram connected."
    )

    return ws


# =========================================================
# RECEIVE TRANSCRIPT FROM DEEPGRAM
# =========================================================

def receive_from_deepgram(ws):

    global _audio_transcript
    global _final_transcript
    global _audio_error

    print()
    print("=" * 70)
    print("DEEPGRAM TRANSCRIPTION ACTIVE")
    print("=" * 70)
    print()

    try:

        while not _stop_event.is_set():

            message = ws.recv()

            if not message:
                continue

            try:

                data = json.loads(
                    message
                )

            except Exception:

                continue

            channel = data.get(
                "channel"
            )

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

            # -------------------------------------------------
            # Update transcript
            # -------------------------------------------------

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

            # -------------------------------------------------
            # Terminal output
            # -------------------------------------------------

            if is_final:

                print()
                print(
                    "CANDIDATE:",
                    _audio_transcript
                )

            else:

                print(
                    "\rCANDIDATE:",
                    _audio_transcript,
                    end="",
                    flush=True
                )

    except Exception as e:

        if not _stop_event.is_set():

            _audio_error = repr(e)

            print()
            print(
                "Deepgram receive error:",
                repr(e)
            )


# =========================================================
# SEND AUDIO TO DEEPGRAM
# =========================================================

def send_audio_to_deepgram(ws):

    print(
        "Starting Deepgram audio sender..."
    )

    print(
        "Sending candidate audio to Deepgram..."
    )

    try:

        while not _stop_event.is_set():

            try:

                audio_data = (
                    _audio_queue.get(
                        timeout=0.5
                    )
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
    global _pyaudio
    global _stream
    global _ws
    global _sender_thread
    global _receiver_thread
    global _audio_error

    try:

        # =================================================
        # FIND WASAPI LOOPBACK
        # =================================================

        _pyaudio, device = (
            find_wasapi_loopback_device()
        )

        device_index = int(
            device["index"]
        )

        sample_rate = int(
            device["defaultSampleRate"]
        )

        channels = int(
            device["maxInputChannels"]
        )

        if channels <= 0:

            raise RuntimeError(
                "WASAPI loopback has no input channels."
            )

        # =================================================
        # OPENING INFORMATION
        # =================================================

        print()
        print("=" * 70)
        print("OPENING AUDIO CAPTURE")
        print("=" * 70)

        print(
            "Device       :",
            device["name"]
        )

        print(
            "Device index :",
            device_index
        )

        print(
            "Sample rate  :",
            sample_rate
        )

        print(
            "Channels     :",
            channels
        )

        print("=" * 70)
        print()

        # =================================================
        # OPEN WASAPI AUDIO STREAM
        # =================================================

        print(
            "Opening WASAPI audio stream..."
        )

        _stream = _pyaudio.open(

            format=pyaudio.paInt16,

            channels=channels,

            rate=sample_rate,

            input=True,

            input_device_index=device_index,

            frames_per_buffer=CHUNK_SIZE,

            stream_callback=audio_callback
        )

        _stream.start_stream()

        print()
        print("=" * 70)
        print("WASAPI AUDIO CAPTURE ACTIVE")
        print("Listening for candidate voice...")
        print("=" * 70)
        print()

        # =================================================
        # CONNECT TO DEEPGRAM
        # =================================================

        _ws = connect_deepgram(
            sample_rate,
            channels
        )

        # =================================================
        # START DEEPGRAM RECEIVER
        # =================================================

        _receiver_thread = threading.Thread(

            target=receive_from_deepgram,

            args=(_ws,),

            daemon=True
        )

        _receiver_thread.start()

        # =================================================
        # START DEEPGRAM SENDER
        # =================================================

        _sender_thread = threading.Thread(

            target=send_audio_to_deepgram,

            args=(_ws,),

            daemon=True
        )

        _sender_thread.start()

        # =================================================
        # KEEP AUDIO RUNNING
        # =================================================

        print(
            "Audio capture is running."
        )

        print(
            "Waiting for candidate speech..."
        )

        print()

        while not _stop_event.is_set():

            time.sleep(0.2)

            if (
                _stream is None
                or not _stream.is_active()
            ):

                break

    except Exception as e:

        _audio_error = repr(e)

        print()
        print("=" * 70)
        print("WASAPI AUDIO ERROR")
        print("=" * 70)
        print(
            repr(e)
        )
        print("=" * 70)
        print()

    finally:

        _audio_running = False

        cleanup_audio()

        print()
        print(
            "Candidate audio capture stopped."
        )


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
    # DEEPGRAM WEBSOCKET
    # -----------------------------------------------------

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
# START AUDIO SERVICE
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
                "message": (
                    "Candidate audio "
                    "already running."
                ),
                "transcript": _audio_transcript
            }

        # -------------------------------------------------
        # CLEAR OLD AUDIO
        # -------------------------------------------------

        while not _audio_queue.empty():

            try:

                _audio_queue.get_nowait()

            except queue.Empty:

                break

        # -------------------------------------------------
        # RESET TRANSCRIPT
        # -------------------------------------------------

        _audio_transcript = ""

        _final_transcript = ""

        _audio_error = ""

        _stop_event.clear()

        _audio_running = True

    # -----------------------------------------------------
    # START BACKGROUND AUDIO WORKER
    # -----------------------------------------------------

    _audio_thread = threading.Thread(

        target=audio_worker,

        daemon=True
    )

    _audio_thread.start()

    return {
        "success": True,
        "running": True,
        "message": (
            "WASAPI candidate audio started."
        ),
        "transcript": ""
    }


# =========================================================
# STOP AUDIO SERVICE
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

    # -----------------------------------------------------
    # Close Deepgram websocket so receiver doesn't
    # remain blocked on ws.recv()
    # -----------------------------------------------------

    if _ws is not None:

        try:

            _ws.close()

        except Exception:

            pass

    return {
        "success": True,
        "running": False,
        "message": (
            "Candidate audio stopped."
        )
    }


# =========================================================
# GET CURRENT TRANSCRIPT
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