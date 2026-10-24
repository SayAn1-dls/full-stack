"""Turn work/sentences.json (written by tts.py) into work/plan.json, the input of record.cjs."""
import json
import script as sc

m = json.load(open("work/sentences.json"))
plan = {part: [dict(id=s["id"], kind=s["kind"], slide=s.get("slide"), setup=s.get("setup"), sentences=m[s["id"]]) for s in scenes]
        for part, scenes in sc.PARTS.items()}
json.dump(plan, open("work/plan.json", "w"), indent=1)
