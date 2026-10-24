"""Narration script for the Wind Intelligence demo video.

Two parts (UAB APEX brief): part 1 = customer pitch of the pilot results, part 2 = tech-lead review. Each must be <= 5 minutes, total <= 10.

A sentence is (text, action). In `text`, {shown|spoken} gives the caption wording and the wording sent to the voice
(numbers are spelled out for the voice so they are read the same way every time). `action` names a step in record.cjs
that runs while the sentence is spoken (None = nothing happens on screen).
"""

# kind: "slide" (slides.html?slide=<name>) or "app" (the live site, set up by record.cjs `setup:<name>`)
P1 = [
    dict(id="p1_title", kind="slide", slide="title1", sentences=[
        ("Hello, and thank you for your time.", None),
        ("Today I will show you the results of our pilot project, called Wind Intelligence.", None),
        ("It is a web portal, made for your day-ahead buying team.", None),
    ]),
    dict(id="p1_problem", kind="slide", slide="problem", sentences=[
        ("Let me start with your problem.", None),
        ("Every day, your team must decide how much power to buy for tomorrow.", None),
        ("Wind is a big part of Britain's power, and it changes every hour. So your team needs a wind forecast.", None),
        ("But new forecasts come out many times a day. Which one could your team really use, at the moment of the decision?", "reveal:1"),
        ("And how good are these forecasts? Can you trust them?", "reveal:2"),
    ]),
    dict(id="p1_pilot", kind="slide", slide="pilot", sentences=[
        ("In this pilot, we answered both questions, using real public data from Elexon.", None),
        ("{We checked 768 hours, over 32 days, against 280 forecast runs.|We checked seven hundred and sixty-eight hours, over thirty-two days, against two hundred and eighty forecast runs.}", "reveal:1"),
        ("Just two data sets were used, for decisions made in {January 2026|January, twenty twenty-six}.", "reveal:2"),
    ]),
    dict(id="p1_decision", kind="app", setup="decision", sentences=[
        ("Here is the portal. This is the Decision view.", None),
        ("Your team picks the decision time. The default is {09:20|nine twenty}, UK time, on the day before. That is when a day-ahead auction closes.", "pointCutoff"),
        ("Then they pick the day they are buying for. Let's take Monday, the {12th|twelfth} of January.", "pointDate"),
        ("The big number is the forecast that your team would have seen: {19.3 gigawatts|nineteen point three gigawatts}, on average. It only uses what was published by {09:20|nine twenty} on Sunday.", "pointHero"),
        ("Now look at this tile: wind to count on. It says: plan with {15 gigawatts|fifteen gigawatts}, not {19|nineteen}. In similar past hours, wind came in at or above this level, nine times out of ten.", "pointCount"),
        ("The row below shows what really happened. Wind averaged {14.4 gigawatts|fourteen point four gigawatts}. The forecast was too high, in all {24|twenty-four} hours.", "pointHindsight"),
        ("This was one of the worst days of the month, so it shows the problem clearly. Even the safe number was a bit high, but it was much closer than the forecast.", "pointCountAgain"),
    ]),
    dict(id="p1_chart", kind="app", setup=None, sentences=[
        ("The chart tells the same story. Blue is the forecast. Orange is the real wind. The pink area is a normal range.", "scrollChart"),
        ("Hover over any hour, and you see the exact numbers.", "hoverChart"),
        ("Every chart also has a table view, for people who like numbers.", "tableToggle"),
        ("Your team can also see how the forecast moved during the day, run by run.", "showRuns"),
        ("If the team decides at {09:50|nine fifty} instead, the portal picks a newer forecast, and everything updates.", "switch0950"),
    ]),
    dict(id="p1_accuracy", kind="app", setup=None, sentences=[
        ("Now the second question: how good is the forecast?", "gotoAccuracy"),
        ("Over the whole month, the forecast was too high by {1.8 gigawatts|one point eight gigawatts} on average. That is {16%|sixteen percent} of the average wind.", "pointAccHero"),
        ("It was too high in {85%|eighty-five percent} of the hours, and on {28 of 32|twenty-eight of thirty-two} days.", "pointAccTiles"),
        ("Red bars mean the forecast was too high. Most bars are red.", "pointHist"),
        ("The gap is biggest when the forecast is big. At {17.8 gigawatts|seventeen point eight gigawatts} or more, it was too high in every single hour.", "scrollSize"),
        ("The forecast still beats a simple guess, like: tomorrow looks like now. Its typical miss is about half as big.", "pointSkill"),
        ("So the forecast is useful, but it leans high. On this month's data, fixing just the average gap would shrink the typical miss by about a third.", "pointBiasRemoved"),
    ]),
    dict(id="p1_limits", kind="app", setup=None, sentences=[
        ("The Method page explains every rule in plain words, and lists the limits.", "gotoMethod"),
        ("This is one winter month, from one source. The portal has no demand or price data, so it says how much wind to count on, not how much to buy.", "scrollMethod"),
    ]),
    dict(id="p1_close", kind="slide", slide="recap1", sentences=[
        ("In short, the portal shows the newest forecast your team could use, shows how wrong it has been, and gives a safer number to plan with.", "reveal:1"),
        ("Good next steps are more months of data, then demand and price data, and finding out why the forecast leans high.", "reveal:2"),
        ("Now, part two is for the technical team.", None),
    ]),
]

P2 = [
    dict(id="p2_title", kind="slide", slide="title2", sentences=[
        ("Part two is for the tech lead.", None),
        ("I will cover the architecture, the design, the analysis, the code, and how we work. I will keep it simple.", "reveal:1"),
    ]),
    dict(id="p2_arch", kind="slide", slide="arch", sentences=[
        ("Here is the architecture.", None),
        ("The front end is React with TypeScript. It shows the pages you saw.", "reveal:1"),
        ("It calls a Python back end, built with FastAPI. There is no database. In production, only two packages are listed.", "reveal:2"),
        ("The back end reads one data file: a saved copy of January from Elexon. January is in the past, so a file is fast, and it works even if Elexon is down.", "reveal:3"),
        ("A script called ingest can rebuild that file. It stops with an error if there is a gap, a conflicting duplicate, or a row it would have to drop.", "reveal:4"),
    ]),
    dict(id="p2_rule", kind="slide", slide="rule", sentences=[
        ("This is the key design rule.", None),
        ("Each day, Elexon publishes about eight forecast runs.", "reveal:1"),
        ("For each hour of the delivery day, we take the newest run published at or before the decision time. The {09:30|nine thirty} run is ten minutes late, so it is not used.", "reveal:2"),
        ("This is the real function. It finds the latest run, at or before the cutoff, that has a value for that hour.", "reveal:3"),
        ("Error is forecast minus actual. Positive means too high. Forecasts are hourly and wind is half-hourly, so we match start times. Other choices change the error by less than {2%|two percent}.", "reveal:4"),
    ]),
    dict(id="p2_analysis", kind="slide", slide="analysis", sentences=[
        ("Now, the analysis.", None),
        ("The pink range comes from past errors. We group forecasts by size, keep the middle {80%|eighty percent} of the errors in each group, and blend smoothly between groups.", "reveal:1"),
        ("The day being viewed is never used to build its own range. As a check, an {80%|eighty percent} range should hold about {80%|eighty percent} of outcomes. In our data it holds {78%|seventy-eight percent}.", "reveal:2"),
        ("We also compare with a simple guess: keep the last known wind the same. The forecast's typical error is about half as big.", "reveal:3"),
        ("The main limit: it is one month, and the range uses later days, so it does not promise the future.", "reveal:4"),
    ]),
    dict(id="p2_api", kind="app", setup="apidocs", sentences=[
        ("The API is easy to explore. FastAPI builds this documentation page by itself.", None),
        ("There are four endpoints: health, meta, decision, and accuracy.", "expandHealth"),
        ("Health returns a fingerprint of the data file, so we can check that the live site uses the right data.", "tryHealth"),
        ("The decision and accuracy endpoints take the decision time as an input. Bad inputs get a clear error: {404|four oh four} for a day outside January, and {422|four twenty-two} for a bad time.", "showDecision"),
    ]),
    dict(id="p2_code", kind="slide", slide="repo", sentences=[
        ("Now, the code base.", None),
        ("{backend/app/wind|backend, app, wind} holds the Python. The scope file sets the January window. Elexon and ingest fetch and check the data. Analytics has the maths. Routes has the API.", "reveal:1"),
        ("{frontend/src|frontend, src} has the views and the hand-written charts. {data/elexon|data, elexon} has the snapshot. The docs folder and the files at the top record every decision and every bug.", "reveal:2"),
        ("To change the time window, start in the scope file, then run ingest again. To add a number, add it in analytics, then in schemas and routes, and then in the views.", None),
    ]),
    dict(id="p2_practices", kind="slide", slide="practices", sentences=[
        ("Now, our key practices.", None),
        ("{219|Two hundred and nineteen} Python tests, and {19|nineteen} front-end tests. Many recalculate the numbers from the raw data, in a separate way.", "reveal:1"),
        ("We also broke the code on purpose, in eight ways. The tests caught all eight. One slipped through at first, so we added a test for it.", "reveal:2"),
        ("{19|Nineteen} browser checks click through the real app, including the live site. Versions are pinned, and decisions and bugs are written down.", "reveal:3"),
    ]),
    dict(id="p2_run", kind="slide", slide="run", sentences=[
        ("To run it, use {docker compose up|docker compose up}. The site opens on port {8080|eight zero eight zero}.", "reveal:1"),
        ("In production, the React build is served as static files, and the Python app runs as one Vercel function.", "reveal:2"),
        ("Two honest notes. The Vercel project is not linked to GitHub, so a push does not redeploy it. And there is no automatic test pipeline yet.", "reveal:3"),
    ]),
    dict(id="p2_close", kind="slide", slide="close", sentences=[
        ("To finish, the limits: one month, one data source, no demand or price, and the cause of the bias is unknown.", "reveal:1"),
        ("This project was built with an AI coding assistant, Claude Code, from Anthropic. The voice in this video is computer generated.", "reveal:2"),
        ("Thank you for watching.", None),
    ]),
]

PARTS = {"p1": P1, "p2": P2}

VOICE = "af_heart"
SPEED = 0.87
GAP = 0.35          # pause after each sentence (s)
SCENE_HOLD = 0.9    # extra pause at the end of each scene (s)
LEAD_IN = 0.9       # silence before the first sentence of a part (s)


def split(text):
    """Return (shown, spoken) from a sentence with {shown|spoken} markers."""
    import re
    shown, spoken, pos = [], [], 0
    for m in re.finditer(r"\{([^{}|]*)\|([^{}|]*)\}", text):
        shown.append(text[pos:m.start()]); spoken.append(text[pos:m.start()])
        shown.append(m.group(1)); spoken.append(m.group(2)); pos = m.end()
    shown.append(text[pos:]); spoken.append(text[pos:])
    return "".join(shown), "".join(spoken)


if __name__ == "__main__":
    for name, scenes in PARTS.items():
        words = sum(len(split(t)[1].split()) for s in scenes for t, _ in s["sentences"])
        n = sum(len(s["sentences"]) for s in scenes)
        est = words / 2.35 + n * GAP + len(scenes) * SCENE_HOLD + LEAD_IN
        print(f"{name}: {len(scenes)} scenes, {n} sentences, {words} spoken words, rough length {est/60:.1f} min")
