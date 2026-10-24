# Narration transcript
Total 8:54. Part 1 4:07, Part 2 4:46. Voice: computer generated.

## Part 1: Pilot results (customer)

### Part 1 - Pilot results for the customer
Hello, and thank you for your time. Today I will show you the results of our pilot project, called Wind Intelligence. It is a web portal, made for your day-ahead buying team.

### The problem
Let me start with your problem. Every day, your team must decide how much power to buy for tomorrow. Wind is a big part of Britain's power, and it changes every hour. So your team needs a wind forecast. But new forecasts come out many times a day. Which one could your team really use, at the moment of the decision? And how good are these forecasts? Can you trust them?

### What the pilot did
In this pilot, we answered both questions, using real public data from Elexon. We checked 768 hours, over 32 days, against 280 forecast runs. Just two data sets were used, for decisions made in January 2026.

### Decision view: the forecast at decision time
Here is the portal. This is the Decision view. Your team picks the decision time. The default is 09:20, UK time, on the day before. That is when a day-ahead auction closes. Then they pick the day they are buying for. Let's take Monday, the 12th of January. The big number is the forecast that your team would have seen: 19.3 gigawatts, on average. It only uses what was published by 09:20 on Sunday. Now look at this tile: wind to count on. It says: plan with 15 gigawatts, not 19. In similar past hours, wind came in at or above this level, nine times out of ten. The row below shows what really happened. Wind averaged 14.4 gigawatts. The forecast was too high, in all 24 hours. This was one of the worst days of the month, so it shows the problem clearly. Even the safe number was a bit high, but it was much closer than the forecast.

### The chart, table and forecast runs
The chart tells the same story. Blue is the forecast. Orange is the real wind. The pink area is a normal range. Hover over any hour, and you see the exact numbers. Every chart also has a table view, for people who like numbers. Your team can also see how the forecast moved during the day, run by run. If the team decides at 09:50 instead, the portal picks a newer forecast, and everything updates.

### Forecast accuracy
Now the second question: how good is the forecast? Over the whole month, the forecast was too high by 1.8 gigawatts on average. That is 16% of the average wind. It was too high in 85% of the hours, and on 28 of 32 days. Red bars mean the forecast was too high. Most bars are red. The gap is biggest when the forecast is big. At 17.8 gigawatts or more, it was too high in every single hour. The forecast still beats a simple guess, like: tomorrow looks like now. Its typical miss is about half as big. So the forecast is useful, but it leans high. On this month's data, fixing just the average gap would shrink the typical miss by about a third.

### Method and limits
The Method page explains every rule in plain words, and lists the limits. This is one winter month, from one source. The portal has no demand or price data, so it says how much wind to count on, not how much to buy.

### Summary and next steps
In short, the portal shows the newest forecast your team could use, shows how wrong it has been, and gives a safer number to plan with. Good next steps are more months of data, then demand and price data, and finding out why the forecast leans high. Now, part two is for the technical team.

## Part 2: Tech review (tech lead)

### Part 2 - Tech review
Part two is for the tech lead. I will cover the architecture, the design, the analysis, the code, and how we work. I will keep it simple.

### Architecture
Here is the architecture. The front end is React with TypeScript. It shows the pages you saw. It calls a Python back end, built with FastAPI. There is no database. In production, only two packages are listed. The back end reads one data file: a saved copy of January from Elexon. January is in the past, so a file is fast, and it works even if Elexon is down. A script called ingest can rebuild that file. It stops with an error if there is a gap, a conflicting duplicate, or a row it would have to drop.

### Design: the key rule
This is the key design rule. Each day, Elexon publishes about eight forecast runs. For each hour of the delivery day, we take the newest run published at or before the decision time. The 09:30 run is ten minutes late, so it is not used. This is the real function. It finds the latest run, at or before the cutoff, that has a value for that hour. Error is forecast minus actual. Positive means too high. Forecasts are hourly and wind is half-hourly, so we match start times. Other choices change the error by less than 2%.

### Analysis
Now, the analysis. The pink range comes from past errors. We group forecasts by size, keep the middle 80% of the errors in each group, and blend smoothly between groups. The day being viewed is never used to build its own range. As a check, an 80% range should hold about 80% of outcomes. In our data it holds 78%. We also compare with a simple guess: keep the last known wind the same. The forecast's typical error is about half as big. The main limit: it is one month, and the range uses later days, so it does not promise the future.

### API walkthrough
The API is easy to explore. FastAPI builds this documentation page by itself. There are four endpoints: health, meta, decision, and accuracy. Health returns a fingerprint of the data file, so we can check that the live site uses the right data. The decision and accuracy endpoints take the decision time as an input. Bad inputs get a clear error: 404 for a day outside January, and 422 for a bad time.

### Code base
Now, the code base. backend/app/wind holds the Python. The scope file sets the January window. Elexon and ingest fetch and check the data. Analytics has the maths. Routes has the API. frontend/src has the views and the hand-written charts. data/elexon has the snapshot. The docs folder and the files at the top record every decision and every bug. To change the time window, start in the scope file, then run ingest again. To add a number, add it in analytics, then in schemas and routes, and then in the views.

### Key practices
Now, our key practices. 219 Python tests, and 19 front-end tests. Many recalculate the numbers from the raw data, in a separate way. We also broke the code on purpose, in eight ways. The tests caught all eight. One slipped through at first, so we added a test for it. 19 browser checks click through the real app, including the live site. Versions are pinned, and decisions and bugs are written down.

### Run it and deploy it
To run it, use docker compose up. The site opens on port 8080. In production, the React build is served as static files, and the Python app runs as one Vercel function. Two honest notes. The Vercel project is not linked to GitHub, so a push does not redeploy it. And there is no automatic test pipeline yet.

### Limits and credits
To finish, the limits: one month, one data source, no demand or price, and the cause of the bias is unknown. This project was built with an AI coding assistant, Claude Code, from Anthropic. The voice in this video is computer generated. Thank you for watching.
