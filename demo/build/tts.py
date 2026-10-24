"""Synthesize every sentence of the script with Kokoro; write wavs and sentences.json (text, durations)."""
import json, sys, time
from pathlib import Path
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
import script as sc

root = Path(sys.argv[1]); models = root / "models"; out = root / "work" / "audio"
k = Kokoro(str(models / "kokoro-v1.0.onnx"), str(models / "voices-v1.0.bin"))
only = set(sys.argv[2:])  # optional scene ids to re-synthesize
meta = json.loads((root / "work" / "sentences.json").read_text()) if (root / "work" / "sentences.json").exists() else {}

PHONEME_FIXES = {"ᵻlˈɛksən": "ˈɛlɛksɑn"}

def trim(s, sr):
    idx = np.where(np.abs(s) > 0.012)[0]
    a = max(0, idx[0] - int(0.04 * sr)); b = min(len(s), idx[-1] + int(0.12 * sr))
    return s[a:b]

for part, scenes in sc.PARTS.items():
    (out / part).mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        if only and scene["id"] not in only and scene["id"] in meta:
            continue
        rows = []
        for i, (text, act) in enumerate(scene["sentences"]):
            shown, spoken = sc.split(text)
            t0 = time.time()
            ph = k.tokenizer.phonemize(spoken, "en-us")
            for bad, good in PHONEME_FIXES.items():        # espeak stresses "Elexon" on the second syllable; it is EL-ex-on
                ph = ph.replace(bad, good)
            s, sr = k.create(ph, voice=sc.VOICE, speed=sc.SPEED, lang="en-us", is_phonemes=True)
            s = trim(s.astype(np.float32), sr)
            f = out / part / f"{scene['id']}_{i}.wav"
            sf.write(f, s, sr)
            rows.append(dict(i=i, shown=shown, spoken=spoken, act=act, dur=round(len(s) / sr, 3), wav=str(f)))
            print(f"{scene['id']}[{i}] {len(s)/sr:5.2f}s ({time.time()-t0:4.1f}s)  {shown[:70]}", flush=True)
        meta[scene["id"]] = rows
        (root / "work" / "sentences.json").write_text(json.dumps(meta, indent=1))
print("DONE")
