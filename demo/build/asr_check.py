"""Transcribe each narration sentence with Whisper and compare with the script, to catch mispronunciations (I cannot listen)."""
import json, re, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel

m = json.load(open("work/sentences.json"))
model = WhisperModel("base.en", device="cpu", compute_type="int8")

NUM = {"zero":0,"oh":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,
       "sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90}
def norm(t):
    t = t.lower().replace("-", " ").replace("%", " percent")
    t = re.sub(r"[^a-z0-9 .]", " ", t)
    t = re.sub(r"(?<=\d)\.(?=\d)", " point ", t).replace(".", " ")
    return re.sub(r"\s+", " ", t).strip()
def wer(ref, hyp):
    r, h = ref.split(), hyp.split()
    d = [[i + j if i * j == 0 else 0 for j in range(len(h) + 1)] for i in range(len(r) + 1)]
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + (r[i-1] != h[j-1]))
    return d[-1][-1] / max(1, len(r))

bad, tot_err, tot_words = [], 0, 0
for scene, rows in m.items():
    for r in rows:
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", r["wav"], "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
        segs, _ = model.transcribe(np.frombuffer(pcm, np.float32), language="en", beam_size=5)
        hyp = norm(" ".join(s.text for s in segs))
        ref = norm(r["spoken"])
        w = wer(ref, hyp)
        tot_err += w * len(ref.split()); tot_words += len(ref.split())
        if w > 0.12:
            bad.append((scene, r["i"], round(w, 2), ref, hyp))
print(f"overall word error rate vs script: {tot_err / tot_words:.1%} over {tot_words} words")
for b in bad:
    print(f"\n[{b[0]}[{b[1]}]] WER {b[2]}\n  script: {b[3]}\n  heard : {b[4]}")
print(f"\n{len(bad)} sentences with word error rate > 12%")
