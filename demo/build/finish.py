"""Combine the two parts and write captions.srt, transcript.md and youtube-description.txt: python finish.py <out dir>"""
import json, subprocess, sys
from pathlib import Path

out = Path(sys.argv[1])
import script as sc

def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True).stdout)

d1, d2 = dur(out / "p1.mp4"), dur(out / "p2.mp4")
(out / "list.txt").write_text(f"file '{(out / 'p1.mp4').resolve()}'\nfile '{(out / 'p2.mp4').resolve()}'\n")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(out / "list.txt"), "-c", "copy", "-movflags", "+faststart", str(out / "wind-intelligence-demo.mp4")], check=True)
total = dur(out / "wind-intelligence-demo.mp4")
print(f"part 1 {d1:.1f}s, part 2 {d2:.1f}s, combined {total:.1f}s ({int(total//60)}:{int(total%60):02d})")

def mmss(t):
    return f"{int(t//60)}:{int(t%60):02d}"
def srt_ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

m1 = json.loads((out / "p1.meta.json").read_text()); m2 = json.loads((out / "p2.meta.json").read_text())
cues = [(a, b, t) for a, b, t in m1["srt"]] + [(a + d1, b + d1, t) for a, b, t in m2["srt"]]
(out / "captions.srt").write_text("".join(f"{i}\n{srt_ts(a)} --> {srt_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1)))

titles = {"p1_title": "Part 1 - Pilot results for the customer", "p1_problem": "The problem", "p1_pilot": "What the pilot did", "p1_decision": "Decision view: the forecast at decision time",
          "p1_chart": "The chart, table and forecast runs", "p1_accuracy": "Forecast accuracy", "p1_limits": "Method and limits", "p1_close": "Summary and next steps",
          "p2_title": "Part 2 - Tech review", "p2_arch": "Architecture", "p2_rule": "Design: the key rule", "p2_analysis": "Analysis", "p2_api": "API walkthrough",
          "p2_code": "Code base", "p2_practices": "Key practices", "p2_run": "Run it and deploy it", "p2_close": "Limits and credits"}
chapters = [(s["start"], titles[s["id"]]) for s in m1["scenes"]] + [(s["start"] + d1, titles[s["id"]]) for s in m2["scenes"]]
chapters[0] = (0.0, chapters[0][1])
chapters[len(m1["scenes"])] = (d1, chapters[len(m1["scenes"])][1])
ch = "\n".join(f"{mmss(t)} {name}" for t, name in chapters)
(out / "youtube-description.txt").write_text(f"""Wind Intelligence - demo video ({mmss(total)})

Part 1 ({mmss(d1)}): pilot results shown to the customer. The portal, the analysis, what it means for a day-ahead buying team.
Part 2 ({mmss(d2)}): technical review for the tech lead. Architecture, design, analysis, code base and key development practices.

Live app: https://wind-intelligence.vercel.app
Data: Elexon BMRS FUELHH (wind outturn) and WINDFOR (wind forecast), decisions made in January 2026.
Built with an AI coding assistant (Claude Code, Anthropic). The narration voice is computer generated.

Chapters
{ch}
""")

lines = ["# Narration transcript\n", f"Total {mmss(total)}. Part 1 {mmss(d1)}, Part 2 {mmss(d2)}. Voice: computer generated.\n"]
for name, scenes in sc.PARTS.items():
    lines.append(f"\n## {'Part 1: Pilot results (customer)' if name == 'p1' else 'Part 2: Tech review (tech lead)'}\n")
    for s in scenes:
        lines.append(f"\n### {titles[s['id']]}\n")
        lines.append(" ".join(sc.split(t)[0] for t, _ in s["sentences"]) + "\n")
(out / "transcript.md").write_text("".join(lines))
print("wrote captions.srt, transcript.md, youtube-description.txt")
