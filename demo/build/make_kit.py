"""Write demo/narration-script-for-your-voice.md: the narration as a read-aloud script, one sentence per line, with on-screen cues."""
import script as sc

CUES = {
    "p1_title": "Title slide", "p1_problem": "Slide: the problem (two questions appear one by one)", "p1_pilot": "Slide: what the pilot did (numbers, then the two data sets)",
    "p1_decision": "Live app, Decision view for 12 January: pointer visits the cutoff, the date, the big number, the 'wind to count on' tile, the hindsight row",
    "p1_chart": "Live app: the chart, hover tooltip, table view, other forecast runs, then 09:50", "p1_accuracy": "Live app, Forecast accuracy tab: headline, histogram, forecast size chart, skill tiles",
    "p1_limits": "Live app, Method and limits tab", "p1_close": "Slide: what the pilot delivers and next steps",
    "p2_title": "Title slide for part two", "p2_arch": "Slide: architecture diagram builds up", "p2_rule": "Slide: timeline of forecast runs, the real function, the error formula",
    "p2_analysis": "Slide: the four analysis cards", "p2_api": "Live API documentation page (FastAPI), health endpoint is executed", "p2_code": "Slide: where things live in the repository",
    "p2_practices": "Slide: tests, mutation checks, browser checks", "p2_run": "Slide: run it and ship it", "p2_close": "Closing slide",
}
TITLES = {"p1": "Part 1: pilot results for the customer (about 4 minutes 30 seconds when read)", "p2": "Part 2: tech review for the tech lead (about 4 minutes 50 seconds when read)"}
lines = ["""# Narration script to read in your own voice

The same words as the video, laid out to read aloud. One sentence per line. Leave a short breath between lines, and a slightly longer
one between sections. At about 150 words per minute Part 1 takes about 4 minutes 30 seconds and Part 2 about 4 minutes 50 seconds with the pauses
(the brief allows 5 minutes each and 10 in total). If a part runs past 5 minutes, speak a little faster or cut a sentence; the
facts on the slides do not depend on any single sentence.

How to record: a quiet room, a phone voice memo is fine, one file per part. Read it the way you would explain it to a colleague;
change any wording that does not sound like you, as long as the facts stay the same. If you change a number, check it against the app.

Say these words like this: **Elexon** = EL-ex-on. **FastAPI** = "fast A-P-I". **gigawatt** = GIG-a-watt. **09:20** = "nine twenty".
**09:50** = "nine fifty". **404 / 422** = "four oh four" / "four twenty-two". **8080** = "eight zero eight zero".

One honest note: the last section of Part 2 says the project was built with an AI coding assistant. Keep that sentence; the brief asks for an
AI-use disclosure. The computer-voice sentence from the generated version is left out below, because in this version the voice is yours.
"""]
for name, scenes in sc.PARTS.items():
    lines.append(f"\n## {TITLES[name]}\n")
    for s in scenes:
        lines.append(f"\n### {CUES[s['id']].split(':')[0] if False else s['id'].split('_', 1)[1].replace('_', ' ').title()}  \n*On screen: {CUES[s['id']]}*\n")
        for text, act in s["sentences"]:
            shown = sc.split(text)[0]
            if "voice in this video is computer generated" in shown:
                shown = shown.replace(" And the voice in this video is computer generated.", "")
            lines.append(shown + "  ")
        lines.append("")
open("kit.md", "w").write("\n".join(lines))
words = sum(len(sc.split(t)[0].split()) for sl in sc.PARTS.values() for s in sl for t, _ in s["sentences"])
print("kit written;", words, "words in total")
