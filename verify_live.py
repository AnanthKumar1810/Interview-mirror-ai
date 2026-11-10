"""Explicit user-run Gnani smoke test; contacts live endpoints and may consume API credits.

Examples:
  python verify_live.py --tts
  python verify_live.py --audio my_16k_mono.wav --language en-IN
"""
import argparse
import io
from pathlib import Path
import wave

from dotenv import load_dotenv
from gnani import GnaniClient, GnaniError

load_dotenv(Path(__file__).parent / '.env')

parser = argparse.ArgumentParser(description='Live Gnani smoke test (uses API credits).')
parser.add_argument('--tts', action='store_true', help='synthesize a short question and save a WAV file')
parser.add_argument('--audio', type=Path, help='transcribe an existing 16 kHz mono WAV (0.2 to 30 sec)')
parser.add_argument('--language', choices=['en-IN', 'te-IN', 'hi-IN'], default='en-IN')
parser.add_argument('--output', type=Path, default=Path('question-preview.wav'))
args = parser.parse_args()
client = GnaniClient()
if not client.enabled:
    parser.exit(2, 'No GNANI_API_KEY found. Configure it in .env first; never share it.\n')
if not args.tts and not args.audio:
    parser.exit(2, 'Specify --tts or --audio. Use --help for instructions.\n')
try:
    if args.tts:
        question = {'en-IN':'Tell me about a project you built.', 'te-IN':'మీరు చేసిన ఒక ప్రాజెక్ట్ గురించి చెప్పండి.', 'hi-IN':'अपने एक प्रोजेक्ट के बारे में बताइए।'}[args.language]
        audio = client.synthesize(question, args.language)
        args.output.write_bytes(audio)
        print(f'Timbre v2.5: saved {len(audio)} bytes to {args.output.resolve()}')
    if args.audio:
        audio = args.audio.read_bytes()
        with wave.open(io.BytesIO(audio), 'rb') as w:
            duration = w.getnframes() / w.getframerate()
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16000 or not 0.2 <= duration <= 30:
                parser.error('Input must be mono PCM 16-bit, 16 kHz WAV, duration 0.2–30s')
        response = client.transcribe(audio, args.language)
        print(f'Prisma ({response["model"]}): {response["transcript"]}')
        if response.get('request_id'):
            print(f'Request ID: {response["request_id"]}')
except (GnaniError, ValueError, FileNotFoundError, wave.Error) as exc:
    parser.exit(1, f'Live test failed: {exc}\n')
