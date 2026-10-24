"""Assemble one part: python assemble.py <rec dir> <part> <out dir>
Finds the first dark frame in the screen recording (the title slide) to sync the audio, mixes every sentence at the moment it was
spoken on screen, burns captions into a 80 px strip under the 1280x640 recording, and encodes a 1280x720 MP4."""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image
import io

rec, part, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
tl = json.loads((rec / f"{part}.timeline.json").read_text())
webm = rec / f"{part}.webm"
FPS = 25

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)

# --- 1. sync: match strong brightness jumps (slide changes) in the recording to the recorder's own clock
raw = run(["ffmpeg", "-v", "error", "-i", str(webm), "-vf", f"fps={FPS},scale=64:32", "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
means = np.frombuffer(raw, np.uint8).reshape(-1, 32, 64).mean(axis=(1, 2))
jumps = [(i + 1) / FPS for i in np.where(np.abs(np.diff(means)) > 30)[0]]
# node time at which each slide scene's page finished loading (goto resolved)
LEAD, SETTLE = 0.9, 0.5
tn = [sc["speechStart"] - (LEAD if k == 0 else SETTLE) for k, sc in enumerate(tl["scenes"])
      if json.loads((Path(__file__).parent / "work" / "plan.json").read_text())[part][k]["kind"] == "slide"]
best = None
for J in jumps:
    for t in tn:
        cand = J - t
        diffs = []
        for jj in jumps:
            d = min((jj - x - cand for x in tn), key=abs)
            if abs(d) < 0.3:
                diffs.append(d)
        if best is None or len(diffs) > best[0]:
            best = (len(diffs), cand, diffs)
n_matched, cand, diffs = best
assert n_matched >= 2 and max(diffs) - min(diffs) < 0.25, f"could not sync: jumps {jumps}, slide times {tn}"   # extra jumps come from scrolling app pages
shift = cand + float(np.median(diffs))            # video time minus node time
first_tn = tn[0]
trim = max(0.0, first_tn + shift - 0.1)
dur_video = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(webm)]).stdout)
length = dur_video - trim
print(f"{part}: {n_matched}/{len(jumps)} slide changes matched, shift {shift:+.2f} s (spread {max(diffs)-min(diffs):.2f} s), trim {trim:.2f} s; video {dur_video:.1f} s -> final {length:.1f} s")

# --- 1b. hold the previous frame wherever the browser shows an empty white page while the next page loads
W, H = 1280, 640
fixed = out / f"{part}.fixed.mp4"
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{trim:.3f}", "-i", str(webm.resolve()), "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(fixed.resolve())], stdin=subprocess.PIPE)
last_good, n_frames, n_held, spans, run = None, 0, 0, [], None
size = W * H * 3
while True:
    buf = dec.stdout.read(size)
    if len(buf) < size:
        break
    arr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    blank = (arr[::4, ::4] < 245).any(axis=2).mean() < 0.005
    if blank and last_good is not None:
        enc.stdin.write(last_good); n_held += 1
        run = (run[0], n_frames) if run else (n_frames, n_frames)
    else:
        enc.stdin.write(buf); last_good = buf
        if run: spans.append(run); run = None
    n_frames += 1
if run: spans.append(run)
enc.stdin.close(); enc.wait(); dec.wait()
print(f"{part}: {n_frames} frames, {n_held} blank-page frames held; spans (s):", [(round(a / FPS, 1), round((b + 1) / FPS, 1)) for a, b in spans])

# --- 2. audio: place each sentence where it started on screen
SR = 24000
mix = np.zeros(int(length * SR) + SR, np.float32)
final_start = {}
for s in tl["sentences"]:
    t = s["start"] + shift - trim
    final_start[(s["scene"], s["i"])] = t
    with wave.open(s["wav"]) as w:
        assert w.getframerate() == SR
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    a = int(round(t * SR))
    mix[a:a + len(x)] += x
    assert a + len(x) <= len(mix), "sentence runs past the end of the video"
raw_wav = out / f"{part}.mix.wav"
with wave.open(str(raw_wav), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
# overlapping sentences would be a sync bug: check
ends = sorted((final_start[(s["scene"], s["i"])], final_start[(s["scene"], s["i"])] + s["dur"]) for s in tl["sentences"])
for (a0, a1), (b0, b1) in zip(ends, ends[1:]):
    assert b0 >= a1 - 0.01, f"sentences overlap: {a0:.2f}-{a1:.2f} and {b0:.2f}"

# --- 3. captions (ASS, 1280x720 coordinates; the strip is y 640..720)
def chunks(text, limit=100):
    if len(text) <= limit:
        return [text]
    mid = len(text) // 2
    cands = [i + 1 for i, ch in enumerate(text) if ch in ".,;:" and 25 < i < len(text) - 25]
    cut = min(cands, key=lambda i: abs(i - mid)) if cands else text.rfind(" ", 0, mid)
    return chunks(text[:cut].strip(), limit) + chunks(text[cut:].strip(), limit)

def ts(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

lines, srt = [], []
for s in tl["sentences"]:
    t0 = final_start[(s["scene"], s["i"])]
    parts = chunks(s["shown"])
    total = sum(len(p) for p in parts)
    cur = t0
    for p in parts:
        d = (s["dur"] + 0.2) * len(p) / total
        lines.append(f"Dialogue: 0,{ts(cur)},{ts(cur + d)},Cap,,0,0,0,,{p}")
        srt.append((cur, cur + d, p))
        cur += d
ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,Inter,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,70,70,10,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""" + "\n".join(lines) + "\n"
(out / f"{part}.ass").write_text(ass)
json.dump(dict(srt=srt, scenes=[dict(id=sc["id"], start=sc["speechStart"] + shift - trim) for sc in tl["scenes"]], length=length), open(out / f"{part}.meta.json", "w"))

# --- 4. encode
vf = (f"[0:v]setpts=PTS-STARTPTS,fps=30,pad=1280:720:0:0:color=0x0b111a,"
      f"subtitles={part}.ass:fontsdir=/usr/share/fonts/opentype/inter,format=yuv420p[v];"
      f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]")
cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(fixed.resolve()), "-i", str(raw_wav.resolve()),
       "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
       str((out / f"{part}.mp4").resolve())]
subprocess.run(cmd, check=True, cwd=out)
print("wrote", out / f"{part}.mp4")
