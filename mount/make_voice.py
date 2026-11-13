"""English voice-over for the sensor-mounting video: one WAV per line of narration/lines.json, spoken by Piper (local
neural text-to-speech, voice en_US-ryan-high). The WAVs are kept in narration/, so render_video.js can rebuild the
video without the voice model.
    pip install piper-tts;  PIPER_VOICE=/path/en_US-ryan-high.onnx python3 make_voice.py"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = os.environ.get("PIPER_VOICE", "en_US-ryan-high.onnx")
lines = json.load(open(os.path.join(HERE, "narration", "lines.json")))
for ln in lines:
    wav = os.path.join(HERE, "narration", ln["id"] + ".wav")
    subprocess.run([sys.executable, "-m", "piper", "-m", VOICE, "-f", wav, "--length-scale", "0.97", "--sentence-silence", "0.25"],
                   input=ln["text"], text=True, check=True, capture_output=True)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                             capture_output=True, text=True).stdout)
    print(f'{ln["id"]}  {d:5.2f} s  at {ln["at"]}')
