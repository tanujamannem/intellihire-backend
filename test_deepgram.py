import os
import asyncio
import traceback

from dotenv import load_dotenv
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents


load_dotenv()

API_KEY = os.getenv("DEEPGRAM_API_KEY")


print("=" * 70)
print("DEEPGRAM SDK 7 CONNECTION TEST")
print("=" * 70)


if not API_KEY:
    print("ERROR: DEEPGRAM_API_KEY not found.")
    raise SystemExit(1)


print("\n1. API KEY")
print("-" * 70)
print("API key found.")
print("Length:", len(API_KEY))
print("Prefix:", API_KEY[:6] + "...")


async def test_deepgram():

    print("\n2. DEEPGRAM CLIENT")
    print("-" * 70)

    try:
        client = DeepgramClient(
            api_key=API_KEY
        )

        print("Deepgram client created.")

    except Exception as error:
        print("CLIENT ERROR:")
        print(repr(error))
        traceback.print_exc()
        return


    print("\n3. DEEPGRAM LIVE CONNECTION")
    print("-" * 70)

    try:

        # ------------------------------------------------------
        # SDK 7.x
        # ------------------------------------------------------

        connection = (
            client.listen.asyncwebsocket.v("1")
        )

        print("Live WebSocket object created.")

        # ------------------------------------------------------
        # EVENT HANDLERS
        # ------------------------------------------------------

        async def on_open(*args, **kwargs):
            print(">>> Deepgram WebSocket OPEN")

        async def on_message(*args, **kwargs):
            print(">>> Deepgram MESSAGE")
            print(args)

        async def on_error(*args, **kwargs):
            print(">>> Deepgram ERROR EVENT")
            print(args)

        async def on_close(*args, **kwargs):
            print(">>> Deepgram WebSocket CLOSED")

        # ------------------------------------------------------
        # REGISTER EVENTS
        # ------------------------------------------------------

        connection.on(
            LiveTranscriptionEvents.Open,
            on_open,
        )

        connection.on(
            LiveTranscriptionEvents.Transcript,
            on_message,
        )

        connection.on(
            LiveTranscriptionEvents.Error,
            on_error,
        )

        connection.on(
            LiveTranscriptionEvents.Close,
            on_close,
        )

        # ------------------------------------------------------
        # OPTIONS
        # ------------------------------------------------------

        options = LiveOptions(
            model="nova-3",
            language="en-US",
            smart_format=True,
            interim_results=True,
            punctuate=True,
            encoding="linear16",
            sample_rate=16000,
            channels=1,
        )

        print("Opening Deepgram WebSocket...")

        connected = await connection.start(
            options
        )

        print(
            "connection.start() returned:",
            connected,
        )

        if not connected:
            print(
                "ERROR: Deepgram WebSocket did not open."
            )
            return

        print()
        print("=" * 70)
        print("DEEPGRAM WEBSOCKET CONNECTED SUCCESSFULLY")
        print("=" * 70)

        # Keep connection alive briefly
        await asyncio.sleep(5)

        print("Closing connection...")

        await connection.finish()

        print("Connection closed.")

    except Exception as error:

        print()
        print("DEEPGRAM ERROR:")
        print(repr(error))

        traceback.print_exc()


if __name__ == "__main__":

    try:
        asyncio.run(
            test_deepgram()
        )

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        print()
        print("=" * 70)
        print("TEST FINISHED")
        print("=" * 70)