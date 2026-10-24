// End-to-end interaction checks (19) for the running app, driven by Playwright and Chromium.
//   node frontend/e2e/interact.cjs <baseUrl> [outDir]
// e.g. against `docker compose up` (http://localhost:8080), `npm run preview` with the API running (http://127.0.0.1:4173)
// or https://wind-intelligence.vercel.app. Playwright is not a dependency of this repository: install it yourself
// (`npm i -g playwright && npx playwright install chromium`) or use an environment that has it. Exits 1 if any check fails.
const { chromium } = require("playwright");
const path = require("path");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`);
  if (!ok) failures++;
};

(async () => {
  const base = process.argv[2] || "http://127.0.0.1:4173";
  const out = process.argv[3] || ".";
  const browser = await chromium.launch();
  const errors = [];
  const failedRequests = [];
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  page.on("response", (r) => { if (r.status() >= 400) failedRequests.push(`${r.status()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`); });
  page.on("console", (m) => { if (m.type() === "error" && !/status of 404/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror " + e.message));

  // --- decision view: data and tooltip
  await page.goto(base + "/?tab=decision&date=2026-01-15&time=09:20", { waitUntil: "networkidle" });
  const api = await (await page.request.get(base + "/api/decision?delivery_date=2026-01-15&decision_time=09:20")).json();
  const hero = await page.locator(".hero-figure .value").first().innerText();
  check("hero equals API mean forecast", hero === (api.summary.mean_forecast_mw / 1000).toFixed(1), `${hero} vs ${(api.summary.mean_forecast_mw / 1000).toFixed(1)}`);

  const svg = page.locator(".chart-card svg").first();
  const box = await svg.boundingBox();
  await page.mouse.move(box.x + box.width * 0.45, box.y + 120);
  await page.waitForSelector(".tooltip");
  const tip = await page.locator(".tooltip").innerText();
  check("tooltip lists forecast, outturn, error and band", /forecast at the cutoff/.test(tip) && /outturn/.test(tip) && /error/.test(tip) && /P10/.test(tip), tip.replace(/\n/g, " | ").slice(0, 150));
  await page.screenshot({ path: path.join(out, "decision-tooltip.png") });
  await page.mouse.move(2, 2);
  check("tooltip disappears on leave", (await page.locator(".tooltip").count()) === 0);

  // --- keyboard: arrow keys move the crosshair
  await svg.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  const kbTip = await page.locator(".tooltip").first().innerText().catch(() => "");
  check("arrow keys show a tooltip", /UK time/.test(kbTip), kbTip.split("\n")[0]);

  // --- table twin
  await page.getByRole("button", { name: "View as table" }).first().click();
  const rows = await page.locator(".chart-card table tbody tr").count();
  check("table view lists all 24 hours", rows === 24, `${rows} rows`);
  await page.getByRole("button", { name: "View chart" }).first().click();

  // --- other runs toggle adds grey lines
  const before = await page.locator(".chart-card svg path").count();
  await page.getByLabel(/Show the other forecast runs/).check();
  const after = await page.locator(".chart-card svg path").count();
  check("showing other runs adds lines", after > before + 5, `${before} -> ${after} paths`);
  await page.screenshot({ path: path.join(out, "decision-revisions.png") });

  // --- changing the cutoff changes the run used
  await page.getByRole("button", { name: /09:50 N2EX/ }).click();
  await page.waitForFunction(() => /before the 09:50 cutoff/.test(document.querySelector(".chart-card .subtitle")?.innerText || ""));
  const sub = await page.locator(".chart-card .subtitle").first().innerText();
  check("09:50 cutoff uses the 09:30 run", /Wed 14 Jan 09:30/.test(sub) && /20 min/.test(sub), sub.slice(0, 120));
  check("URL follows the selection", page.url().includes("time=09%3A50") || page.url().includes("time=09:50"), page.url());

  // --- day navigation
  await page.getByRole("button", { name: "Next day" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("Fri, 16 Jan 2026"));
  check("next day moves the delivery date", true);

  // --- early cutoff shows the coverage notice instead of hiding hours
  await page.goto(base + "/?tab=decision&date=2026-01-15&time=00:00", { waitUntil: "networkidle" });
  const note = await page.locator(".callout").first().innerText();
  check("early cutoff explains missing hours", /No forecast covered 22:00, 23:00/.test(note), note.split("\n")[1]);

  // --- error state for an out-of-scope day
  await page.goto(base + "/?tab=decision&date=2026-03-01&time=09:20", { waitUntil: "networkidle" });
  const err = await page.locator(".callout.error").first().innerText();
  check("out-of-scope day shows a clear error", /out of scope/.test(err), err.replace(/\n/g, " ").slice(0, 120));

  // --- December-31 decision label
  await page.goto(base + "/?tab=decision&date=2026-01-01&time=09:20", { waitUntil: "networkidle" });
  check("1 Jan flagged as decided outside the window", /Decided on 31 December 2025/.test(await page.locator(".filters").innerText()));

  // --- accuracy view
  await page.goto(base + "/?tab=accuracy&time=09:20", { waitUntil: "networkidle" });
  const acc = await (await page.request.get(base + "/api/accuracy?decision_time=09:20")).json();
  const accHero = await page.locator(".hero-figure .value").first().innerText();
  check("accuracy hero equals API bias", accHero === `+${(acc.headline.bias_mw / 1000).toFixed(1)}`, accHero);
  await page.mouse.move(2, 2);
  const hist = page.locator(".chart-card svg").first();
  await hist.scrollIntoViewIfNeeded();
  const hb = await hist.boundingBox();
  await page.mouse.move(hb.x + hb.width * 0.55, hb.y + hb.height * 0.75);
  await page.waitForTimeout(150);
  check("histogram bar tooltip", (await page.locator(".tooltip").count()) === 1, (await page.locator(".tooltip").first().innerText().catch(() => "")).replace(/\n/g, " | "));
  await page.screenshot({ path: path.join(out, "accuracy-hover.png") });
  await page.getByRole("button", { name: "Last 7 delivery days" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("of 7 delivery days") || document.body.innerText.includes("of 7 "));
  const h7 = await page.locator(".hero-caption").innerText();
  check("range preset re-scopes every figure", /168 hours/.test(h7), h7.slice(0, 160));

  // --- theme toggle
  await page.getByRole("button", { name: /Colour theme/ }).click();
  check("theme toggle sets data-theme", (await page.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");

  // --- method page
  await page.goto(base + "/?tab=method", { waitUntil: "networkidle" });
  const method = await page.locator(".prose").innerText();
  check("method page states scope limits", /Elexon only/.test(method) && /Wind only/.test(method) && /09:20/.test(method) && /09:50/.test(method));

  await browser.close();
  check("the only failing request is the intentional out-of-scope one", failedRequests.length === 1 && /2026-03-01/.test(failedRequests[0]), failedRequests.join(" ; "));
  check("no console errors", errors.length === 0, errors.join(" || ").slice(0, 300));
  console.log(failures ? `\n${failures} FAILED` : "\nALL PASSED");
  process.exit(failures ? 1 : 0);
})();
