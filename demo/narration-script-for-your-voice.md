# Narration script to read in your own voice

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


## Part 1: pilot results for the customer (about 4 minutes 30 seconds when read)


### Title  
*On screen: Title slide*

Hi, and thanks for taking the time.  
Today I'm going to show you what came out of our pilot project, called Wind Intelligence.  
It's a web portal, built for your day-ahead buying team.  


### Problem  
*On screen: Slide: the problem (two questions appear one by one)*

Let's start with the problem you face.  
Every day, your team has to decide how much power to buy for tomorrow.  
Wind is a big part of Britain's power, and it changes hour by hour. So you need a wind forecast.  
But new forecasts come out many times a day. So which one could your team really use, at the moment they decide?  
And how good are these forecasts? Can you trust them?  


### Pilot  
*On screen: Slide: what the pilot did (numbers, then the two data sets)*

In this pilot, we answered both questions, using real public data from Elexon.  
We checked 768 hours, over 32 days, against 280 forecast runs.  
We used just two data sets, for decisions made in January 2026.  


### Decision  
*On screen: Live app, Decision view for 12 January: pointer visits the cutoff, the date, the big number, the 'wind to count on' tile, the hindsight row*

Here's the portal. This is the Decision view.  
Your team picks a decision time. The default is 09:20, UK time, on the day before. That's when a day-ahead auction closes.  
Then they pick the day they're buying for. Let's take Monday, the 12th of January.  
The big number is the forecast that your team would have seen: 19.3 gigawatts, on average. And it only uses what had been published by 09:20 on Sunday.  
Now look at this tile: wind to count on. It says, plan with 15 gigawatts, not 19. In similar past hours, wind came in at or above this level, nine times out of ten.  
The row below shows what really happened. Wind averaged 14.4 gigawatts. So the forecast was too high, in all 24 hours.  
This was one of the worst days of the month, so it shows the problem clearly. Even the safe number was a bit high, but it was much closer than the forecast.  


### Chart  
*On screen: Live app: the chart, hover tooltip, table view, other forecast runs, then 09:50*

The chart tells the same story. Blue is the forecast. Orange is the real wind. And the pink area is a normal range.  
If you hover over any hour, you can see the exact numbers.  
Every chart also has a table view, for people who like numbers.  
Your team can also see how the forecast moved during the day, run by run.  
And if the team decides at 09:50 instead, the portal picks a newer forecast, and everything updates.  


### Accuracy  
*On screen: Live app, Forecast accuracy tab: headline, histogram, forecast size chart, skill tiles*

Now for the second question: how good is the forecast?  
Over the whole month, the forecast was too high by 1.8 gigawatts on average. That's 16% of the average wind.  
It was too high in 85% of the hours, and on 28 of the 32 days.  
Red bars mean the forecast was too high, and most of the bars are red.  
The gap is biggest when the forecast is big. At 17.8 gigawatts or more, it was too high in every single hour.  
The forecast still beats a simple guess, like: tomorrow will look like right now. Its typical miss is about half as big.  
So the forecast is useful, but it leans high. On this month's data, fixing just the average gap would shrink the typical miss by about a third.  


### Limits  
*On screen: Live app, Method and limits tab*

The Method page explains every rule in plain words, and lists the limits.  
This is one winter month, from one source. And the portal has no demand or price data, so it tells you how much wind to count on, not how much to buy.  


### Close  
*On screen: Slide: what the pilot delivers and next steps*

So, in short, the portal shows the newest forecast your team could use, shows how wrong it has been, and gives you a safer number to plan with.  
Good next steps are more months of data, then demand and price data, and finding out why the forecast leans high.  
Now, part two is for the technical team.  


## Part 2: tech review for the tech lead (about 4 minutes 50 seconds when read)


### Title  
*On screen: Title slide for part two*

Part two is for the tech lead.  
I'll cover the architecture, the design, the analysis, the code, and how we work. I'll keep it simple.  


### Arch  
*On screen: Slide: architecture diagram builds up*

Here's the architecture.  
The front end is React with TypeScript. It shows the pages you just saw.  
It calls a Python back end, built with FastAPI. There's no database, and in production only two packages are listed.  
The back end reads one data file: a saved copy of January from Elexon. January is in the past, so a file is fast, and it works even if Elexon is down.  
A script called ingest can rebuild that file. It stops with an error if there's a gap, a conflicting duplicate, or a row it would have to drop.  


### Rule  
*On screen: Slide: timeline of forecast runs, the real function, the error formula*

This is the key design rule.  
Each day, Elexon publishes about eight forecast runs.  
For each hour of the delivery day, we take the newest run published at or before the decision time. The 09:30 run is ten minutes late, so we don't use it.  
This is the real function. It finds the latest run, at or before the cutoff, that has a value for that hour.  
Error is forecast minus actual, so positive means too high. Forecasts are hourly and wind is half-hourly, so we match start times. Other choices change the error by less than 2%.  


### Analysis  
*On screen: Slide: the four analysis cards*

Now, the analysis.  
The pink range comes from past errors. We group forecasts by size, keep the middle 80% of the errors in each group, and blend smoothly between groups.  
The day being viewed is never used to build its own range. As a check, an 80% range should hold about 80% of outcomes. In our data, it holds 78%.  
We also compare with a simple guess: keep the last known wind the same. The forecast's typical error is about half as big.  
The main limit is that it's one month, and the range uses later days, so it doesn't promise the future.  


### Api  
*On screen: Live API documentation page (FastAPI), health endpoint is executed*

The API is easy to explore. FastAPI builds this documentation page by itself.  
There are four endpoints: health, meta, decision, and accuracy.  
Health returns a fingerprint of the data file, so we can check that the live site is using the right data.  
The decision and accuracy endpoints take the decision time as an input. Bad inputs get a clear error: 404 for a day outside the January window, and 422 for a bad time.  


### Code  
*On screen: Slide: where things live in the repository*

Now, the code base.  
backend/app/wind holds the Python. The scope file sets the January window. Elexon and ingest fetch and check the data. Analytics has the maths, and routes has the API.  
frontend/src has the views and the hand-written charts. data/elexon has the snapshot. And the docs folder and the files at the top record every decision and every bug.  
To change the time window, start in the scope file, then run ingest again. To add a number, add it in analytics, then in schemas and routes, and then in the views.  


### Practices  
*On screen: Slide: tests, mutation checks, browser checks*

Now, our key practices.  
We have 219 Python tests, and 19 front-end tests. Many of them recalculate the numbers from the raw data, in a separate way.  
We also broke the code on purpose, in eight ways. The tests caught all eight. One slipped through at first, so we added a test for it.  
19 browser checks click through the real app, including the live site. Versions are pinned, and decisions and bugs are written down.  


### Run  
*On screen: Slide: run it and ship it*

To run it, use docker compose up. The site opens on port 8080.  
In production, the React build is served as static files, and the Python app runs as one Vercel function.  
Two honest notes. The Vercel project isn't linked to GitHub, so a push doesn't redeploy it. And there's no automatic test pipeline yet.  


### Close  
*On screen: Closing slide*

To finish, the limits: one month, one data source, no demand or price, and we don't know why the forecast leans high.  
This project was built with an AI coding assistant, Claude Code, from Anthropic.  
Thanks for watching.  
