# Demo video

One unlisted YouTube video in two parts, made for the brief "Part 1: present the portal and analysis to the customer as the output
of a pilot (max 5 minutes); Part 2: walk the tech lead through architecture, design, analysis, code base and key practices
(max 5 minutes); 10 minutes in total".

| | Length |
|---|---|
| Part 1: pilot results for the customer | 4:12 |
| Part 2: tech review | 4:48 |
| Whole video | 9:01 |

Chapters (also in `youtube-description.txt`; paste them into the YouTube description and they become chapter markers):
0:00 Part 1, 0:14 The problem, 0:41 What the pilot did, 1:04 Decision view: the forecast at decision time, 2:08 The chart, table and forecast runs, 2:41 Forecast accuracy, 3:33 Method and limits, 3:50 Summary and next steps, 4:12 Part 2, 4:23 Architecture, 5:03 Design: the key rule, 5:43 Analysis, 6:29 API walkthrough, 7:03 Code base, 7:43 Key practices, 8:15 Run it and deploy it, 8:40 Limits and credits.

## Files

- `out/wind-intelligence-demo.mp4`: the video (1280x720, 24 MB). It is **not** in git; it goes to YouTube.
- `captions.srt`: captions to upload with the video (the same words are also burned into the picture).
- `transcript.md`: the full narration, by chapter.
- `youtube-description.txt`: description and chapter list.
- `narration-script-for-your-voice.md`: the same narration laid out to read aloud, for a version in a real human voice (see below).
- `build/`: the scripts that produced the video.

## Uploading (unlisted)

YouTube, then Create, then Upload video. Pick `out/wind-intelligence-demo.mp4`, set Visibility to **Unlisted**, paste
`youtube-description.txt` into the description, and add `captions.srt` under Subtitles. Copy the video link and use it in the
submission. The video link is not recorded in this repository yet.

## What is synthetic, and a version in a human voice

The narration in `out/wind-intelligence-demo.mp4` is a **computer-generated male voice** (Kokoro-82M, Apache-2.0, voice `am_michael`,
about 160 to 170 words per minute). The script was written by an AI assistant (Claude Code, Anthropic) in short, conversational
English, and the video says both things in its closing slide and sentence. They are declared on purpose: the brief asks for an AI-use
disclosure, and a synthetic voice should not be presented to reviewers as a recording of a person.

For a video in a real human voice, record `narration-script-for-your-voice.md` yourself (one audio file per part, a phone is fine).
The picture can then be re-timed to your pace and rebuilt with your audio instead of the synthetic one. The voice sentence is left out
of that script because the voice would be yours; keep the sentence that says the project was built with an AI coding assistant.

## How it was made

- **Picture:** the live site https://wind-intelligence.vercel.app driven by Playwright (Chromium) with a visible cursor, plus
  slides drawn in HTML (`build/slides.html`). While recording, the script reads the page and stops if a number differs from what
  the narration says (19.3 GW, 15.0 GW, 14.4 GW, 24 of 24, +1.8 GW, 85%, 28 of 32, 51%, 1.4 GW, the data fingerprint).
- **Checks on the voice:** done with a speech-recognition pass (Whisper base.en), not by ear. The recognised text matches the script
  apart from numbers written as digits, and 101 of 104 caption cues have their first word heard within 1.2 s of the cue start.
  "Elexon" is forced to EL-ex-on; "endpoints" and "meta" are respelled so the voice says them clearly.
- **Assembly:** ffmpeg. Each sentence is placed where it was spoken on screen, captions go in a strip under the picture, loudness is
  about -17 LUFS, and moments where the browser shows an empty white page while a page loads are replaced by the previous frame.
- **Provenance only:** the files in `build/` are copies of the scripts used (the Kokoro model files, `work/`, `rec/` and `final/`
  folders they use are not stored). They were not re-run from this folder.
  Order: `tts.py` (voice), `make_plan.py`, `record.cjs` for `p1` and `p2`, `assemble.py` for each part, `finish.py`.

## Known blemishes

- The tooltip on the first chart wraps its "plausible outturn" row onto three narrow lines. That is how the app renders it; it was
  not changed.
- There are three to four quiet seconds where the video switches from a slide to a live page.
- The Part 2 example (12 January) is one of the worst days of the month; the narration says so.
