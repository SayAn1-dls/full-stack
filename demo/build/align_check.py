"""Transcribe the FINAL soundtrack with word timestamps and check each caption cue starts where its first word is heard."""
import re, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel

mp4 = sys.argv[1]; srt = open(sys.argv[2]).read()
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", mp4, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
audio = np.frombuffer(pcm, np.float32)
model = WhisperModel("base.en", device="cpu", compute_type="int8")
segs, _ = model.transcribe(audio, language="en", word_timestamps=True, beam_size=5, condition_on_previous_text=False, vad_filter=True)
words = [(re.sub(r"[^a-z]", "", w.word.lower()), w.start, w.end) for s in segs for w in s.words]
words = [w for w in words if w[0]]
print(f"heard {len(words)} words over {len(audio)/16000:.0f} s")

def t(s):
    h, m, r = s.split(":"); sec, ms = r.split(","); return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
cues = [(t(m.group(1)), re.sub(r"\s+", " ", m.group(3)).strip()) for m in re.finditer(r"\d+\n(\S+) --> (\S+)\n(.*?)\n\n", srt, re.S)]
checked = ok = 0; off = []
for start, text in cues:
    ws = re.findall(r"[A-Za-z']+", text)
    if not ws or re.search(r"\d", text.split()[0]):
        continue
    first = re.sub(r"[^a-z]", "", ws[0].lower())
    cand = [w for w in words if abs(w[1] - start) < 1.2]
    match = [w for w in cand if w[0] == first or (len(first) > 3 and w[0][:3] == first[:3])]
    checked += 1
    if match:
        ok += 1; off.append(min(match, key=lambda w: abs(w[1] - start))[1] - start)
print(f"{ok}/{checked} caption cues have their first word heard within 1.2 s of the cue start")
off = np.array(off)
print(f"offset heard-minus-cue: median {np.median(off):+.2f} s, 5th-95th percentile {np.percentile(off,5):+.2f} .. {np.percentile(off,95):+.2f} s")
