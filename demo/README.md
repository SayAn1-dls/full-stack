# Demo video

One unlisted YouTube video in two parts, made for the brief "Part 1: present the portal and analysis to the customer as the output
of a pilot (max 5 minutes); Part 2: walk the tech lead through architecture, design, analysis, code base and key practices
(max 5 minutes); 10 minutes in total".

| | Length |
|---|---|
| Part 1: pilot results for the customer | 4:07 |
| Part 2: tech review | 4:46 |
| Whole video | 8:54 |

Chapters (also in `youtube-description.txt`, paste them into the YouTube description and they become chapter markers):
0:00 Part 1, 0:14 The problem, 0:39 What the pilot did, 1:02 Decision view, 2:06 The chart, 2:38 Forecast accuracy, 3:29 Method and limits,
3:46 Summary and next steps, 4:07 Part 2, 4:19 Architecture, 4:58 Design, 5:38 Analysis, 6:23 API walkthrough, 6:57 Code base,
7:37 Key practices, 8:08 Run and deploy, 8:33 Limits and credits.

## Files

- `out/wind-intelligence-demo.mp4`: the video (1280x720, 24 MB). It is **not** in git; it goes to YouTube.
- `captions.srt`: captions to upload with the video (the same words are also burned into the picture).
- `transcript.md`: the full narration, by chapter.
- `youtube-description.txt`: description and chapter list.
- `build/`: the scripts that produced the video (see below).

## Uploading (unlisted)

YouTube, then Create, then Upload video. Pick `out/wind-intelligence-demo.mp4`, set Visibility to **Unlisted**, paste
`youtube-description.txt` into the description, and add `captions.srt` under Subtitles. Copy the video link and use it in the
submission. The video link is not recorded in this repository yet.

## How it was made (and what is synthetic)

- **Script:** written by an AI assistant (Claude Code, Anthropic) in short, plain English. Every number in it comes from the app
  or from `TEST_REPORT.md` and `docs/APP_DESIGN.md`.
- **Voice:** computer generated with Kokoro-82M (Apache-2.0) through `kokoro-onnx`, voice `af_heart`, about 160 to 170 words
  per minute. The video says so in its last slide and sentence. It was checked with a speech-recognition pass (Whisper base.en),
  not by ear: the recognised text matches the script apart from numbers written as digits, and 99 of 102 caption cues have their
  first word heard within 1.2 s of the cue start. The voice's pronunciation of "Elexon" was forced to EL-ex-on.
- **Picture:** the live site https://wind-intelligence.vercel.app driven by Playwright (Chromium) with a visible cursor, plus
  slides drawn in HTML (`build/slides.html`). While recording, the script reads the page and stops if a number differs from what
  the narration says (19.3 GW, 15.0 GW, 14.4 GW, 24 of 24, +1.8 GW, 85%, 28 of 32, 51%, 1.4 GW, the data fingerprint).
- **Assembly:** ffmpeg. Each sentence is placed where it was spoken on screen, captions go in a strip under the picture, loudness is
  about -16 LUFS, and moments where the browser shows an empty white page while a page loads are replaced by the previous frame.
- **Provenance only:** the files in `build/` are copies of the scripts used (the Kokoro model files, `work/`, `rec/` and `final/`
  folders they use are not stored). They were not re-run from this folder.
  Order: `tts.py` (voice), `make_plan.py`, `record.cjs` for `p1` and `p2`, `assemble.py` for each part, `finish.py`.

## Known blemishes

- The tooltip on the first chart wraps its "plausible outturn" row onto three narrow lines. That is how the app renders it; it was
  not changed.
- There are three to four quiet seconds where the video switches from a slide to a live page.
- The Part 2 example (12 January) is one of the worst days of the month; the narration says so.
