// Records one part of the demo: node record.cjs <plan.json> <p1|p2> <outDir>
// Drives the LIVE app (and slides.html) with a visible cursor, one sentence at a time, using the real audio durations,
// and writes <outDir>/<part>.webm plus <outDir>/<part>.timeline.json (when each sentence started, in seconds).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const [planPath, part, outDir] = process.argv.slice(2);
const plan = JSON.parse(fs.readFileSync(planPath))[part];
const GAP = 0.35, HOLD = 0.9, LEAD = 0.9;
const BASE = "https://wind-intelligence.vercel.app";
const SLIDES = "file://" + path.join(__dirname, "slides.html");
const WARM = {
  p1: [`${BASE}/?tab=decision&date=2026-01-12&time=09:20`, `${BASE}/?tab=accuracy&time=09:20`, `${BASE}/?tab=method`],
  p2: [`${BASE}/api/docs`],
};
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));

const CURSOR = `(() => {
  const mk = () => {
    if (document.getElementById("__cur")) return;
    const c = document.createElement("div"); c.id = "__cur";
    c.style.cssText = "position:fixed;z-index:2147483647;width:26px;height:26px;border-radius:50%;background:rgba(255,196,0,.38);border:3px solid #f5a300;pointer-events:none;left:-60px;top:-60px;transform:translate(-50%,-50%) scale(1);transition:transform .1s;box-shadow:0 0 0 1px rgba(0,0,0,.3)";
    document.documentElement.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => { c.style.transform = "translate(-50%,-50%) scale(.65)"; }, true);
    addEventListener("mouseup", () => { c.style.transform = "translate(-50%,-50%) scale(1)"; }, true);
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", mk); else mk();
})();`;

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 640 }, recordVideo: { dir: path.join(outDir, `${part}-raw`), size: { width: 1280, height: 640 } } });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const t0 = Date.now();
  const now = () => (Date.now() - t0) / 1000;
  let mx = 640, my = 320;   // last known cursor position

  // ---------- helpers
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
  async function glide(x, y, secs = 0.9) {
    const n = Math.max(6, Math.round(secs * 50));
    for (let i = 1; i <= n; i++) {
      const k = ease(i / n);
      await page.mouse.move(mx + (x - mx) * k, my + (y - my) * k);
      await sleep(secs / n);
    }
    mx = x; my = y;
  }
  const centre = async (loc, fx = 0.5, fy = 0.5) => {
    const b = await loc.boundingBox();
    if (!b) throw new Error("no box for " + loc);
    return [b.x + b.width * fx, b.y + b.height * fy];
  };
  async function point(loc, secs = 0.9, fx = 0.5, fy = 0.5) { const [x, y] = await centre(loc, fx, fy); await glide(x, y, secs); }
  async function scrollToY(y, secs = 1.0) {
    if (mx > 40) await glide(18, my, 0.3);       // park the cursor in the margin so charts sliding under it do not pop tooltips
    await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), Math.max(0, y));
    await sleep(secs);
  }
  async function scrollToEl(loc, offset = 14, secs = 1.0) {
    const y = await loc.evaluate((el, off) => el.getBoundingClientRect().top + window.scrollY - off, offset);
    await scrollToY(y, secs);
  }
  async function slowScroll(px, secs) {
    const steps = Math.round(secs * 25);
    for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, px / steps); await sleep(secs / steps); }
  }
  const must = (cond, msg) => { if (!cond) throw new Error("NARRATION CHECK FAILED: " + msg); };
  const text = (loc) => loc.innerText();
  const tile = (name) => page.locator(".tile", { hasText: name }).first();
  const card = (name) => page.locator(".chart-card", { hasText: name }).first();
  const appReady = async () => { await page.waitForLoadState("networkidle"); await page.waitForSelector(".hero-figure .value"); await sleep(0.4); await page.mouse.move(mx, my); };

  // ---------- actions (names used in script.py)
  const actions = {
    // decision view
    async pointCutoff() { await point(page.getByRole("button", { name: "09:20 EPEX" }), 0.9); await sleep(1.2); await point(page.locator("input[type=time]").first(), 0.9); },
    async pointDate() { await point(page.locator("input[type=date]").first(), 1.0); },
    async pointHero() { await point(page.locator(".hero-figure .value").first(), 1.0); },
    async pointCount() { await point(tile("Wind to count on"), 1.0, 0.5, 0.35); await sleep(1.2); await point(tile("Wind to count on"), 0.8, 0.5, 0.8); },
    async pointHindsight() { await point(tile("Outturn averaged"), 1.0, 0.5, 0.4); await sleep(0.9); await point(tile("Hours over-forecast"), 1.0, 0.5, 0.4); },
    async pointCountAgain() { await point(tile("Wind to count on"), 1.0, 0.5, 0.35); await sleep(1.0); await point(tile("Outturn averaged"), 1.0, 0.5, 0.35); },
    async scrollChart() { await scrollToEl(card("Forecast held at the decision"), 16, 1.1); },
    async hoverChart() {
      const svg = card("Forecast held at the decision").locator("svg").first();
      const b = await svg.boundingBox();
      await glide(b.x + b.width * 0.30, b.y + b.height * 0.40, 0.9);
      await sleep(0.7);
      await glide(b.x + b.width * 0.52, b.y + b.height * 0.40, 1.3);
      await page.waitForSelector(".tooltip");
      await sleep(0.9);
    },
    async tableToggle() {
      const c = card("Forecast held at the decision");
      await point(c.getByRole("button", { name: "View as table" }), 0.8);
      await page.mouse.down(); await page.mouse.up();
      await sleep(1.6);
      const back = c.getByRole("button", { name: "View chart" });
      await point(back, 0.8);
      await page.mouse.down(); await page.mouse.up();
      await sleep(0.5);
    },
    async showRuns() {
      const box = page.getByLabel(/Show the other forecast runs/);
      await point(box, 0.9);
      await page.mouse.down(); await page.mouse.up();
      await sleep(1.4);
      await scrollToEl(page.locator(".card", { hasText: "Forecast runs for this delivery day" }).first(), 14, 1.1);
      await sleep(0.8);
    },
    async switch0950() {
      await scrollToY(0, 1.0);
      await point(page.getByRole("button", { name: /09:50 N2EX/ }), 0.8);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForFunction(() => /09:30/.test(document.querySelector(".chart-card .subtitle")?.innerText || ""));
      await sleep(0.7);
    },
    // accuracy view
    async gotoAccuracy() {
      await point(page.getByRole("tab", { name: "Forecast accuracy" }), 0.9);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForFunction(() => /over-forecast/.test(document.body.innerText) && /Error by lead time/.test(document.body.innerText));
      // the 09:50 selection travels with the tab: put the portal back on 09:20 so the figures match the narration
      await point(page.getByRole("button", { name: "09:20 EPEX" }), 0.7);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForFunction(() => document.querySelector(".hero-figure .value")?.innerText.trim() === "+1.8");
      await sleep(0.4);
    },
    async pointAccHero() {
      must((await text(page.locator(".hero-figure .value").first())).trim() === "+1.8", "accuracy hero is not +1.8");
      await point(page.locator(".hero-figure .value").first(), 1.0);
    },
    async pointAccTiles() {
      const cap = await text(page.locator(".hero-caption"));
      must(/85%/.test(cap) && /28 of 32/.test(cap) && /16%/.test(cap), "hero caption lacks 85% / 28 of 32 / 16%: " + cap);
      await point(page.locator(".hero-caption"), 1.1, 0.5, 0.6);
    },
    async pointHist() {
      await scrollToEl(card("How wrong, and in which direction"), 16, 1.1);
      const svg = card("How wrong, and in which direction").locator("svg").first();
      const b = await svg.boundingBox();
      await glide(b.x + b.width * 0.52, b.y + b.height * 0.6, 1.0);
      await sleep(0.5);
      await glide(b.x + b.width * 0.66, b.y + b.height * 0.7, 1.0);
    },
    async scrollSize() {
      const c = card("Error by forecast size");
      await scrollToEl(c, 16, 1.2);
      const svg = c.locator("svg").first();
      const b = await svg.boundingBox();
      await glide(b.x + b.width * 0.88, b.y + b.height * 0.55, 1.1);
      await page.waitForSelector(".tooltip", { timeout: 3000 }).catch(() => {});
    },
    async pointSkill() {
      await scrollToY(0, 1.0);
      const t = tile("Skill vs naive persistence");
      must(/51%/.test(await text(t)), "skill tile is not 51%");
      await point(t, 1.1, 0.5, 0.4);
    },
    async pointBiasRemoved() {
      const t = tile("MAE if the bias were removed");
      must(/1\.4 GW/.test(await text(t)), "bias-removed tile is not 1.4 GW");
      await point(t, 1.2, 0.5, 0.4);
    },
    // method page
    async gotoMethod() {
      await scrollToY(0, 0.8);
      await point(page.getByRole("tab", { name: "Method and limits" }), 0.9);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForSelector(".prose");
      await sleep(0.4);
    },
    async scrollMethod() { await glide(900, 360, 0.8); await slowScroll(520, 5.5); },
    // swagger page
    async expandHealth() {
      const rows = page.locator(".opblock-summary");
      for (let i = 0; i < 4; i++) { await point(rows.nth(i), 0.5, 0.2, 0.5); await sleep(0.15); }
      await point(rows.nth(0), 0.45, 0.2, 0.5);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForSelector(".opblock.is-open");
      await sleep(0.4);
    },
    async showDecision() {
      const row = page.locator(".opblock-summary").nth(2);
      await scrollToEl(row, 110, 0.9);
      await point(row, 0.8, 0.2, 0.5);
      await page.mouse.down(); await page.mouse.up();
      await sleep(1.1);
      await scrollToEl(row, 70, 0.9);
    },
    async tryHealth() {
      await point(page.getByRole("button", { name: "Try it out" }), 0.8);
      await page.mouse.down(); await page.mouse.up();
      await point(page.getByRole("button", { name: "Execute" }), 0.7);
      await page.mouse.down(); await page.mouse.up();
      const body = page.locator(".responses-table.live-responses-table .microlight").first();
      await body.waitFor({ timeout: 15000 });
      const t = await text(body);
      must(/snapshot_sha256/.test(t) && /da46ed4951/.test(t), "health response lacks the snapshot hash: " + t);
      await scrollToEl(body, 260, 0.9);
      await point(body, 0.9, 0.5, 0.5);
    },
  };

  async function setup(name) {
    if (name === "decision") {
      await page.goto(`${BASE}/?tab=decision&date=2026-01-12&time=09:20`);
      await appReady();
      const hero = (await text(page.locator(".hero-figure .value").first())).trim();
      must(hero === "19.3", `decision hero is ${hero}, narration says 19.3`);
      must(/15\.0 GW/.test(await text(tile("Wind to count on"))), "wind to count on is not 15.0 GW");
      must(/14\.4 GW/.test(await text(tile("Outturn averaged"))), "outturn is not 14.4 GW");
      must(/24 of 24/.test(await text(tile("Hours over-forecast"))), "hours over-forecast is not 24 of 24");
      must(/Sun 11 Jan 07:30/.test(await text(card("Forecast held at the decision").locator(".subtitle"))), "run used is not Sun 11 Jan 07:30");
    } else if (name === "apidocs") {
      await page.goto(`${BASE}/api/docs`, { waitUntil: "networkidle" });
      await page.waitForSelector(".swagger-ui .opblock-summary");
      await page.mouse.move(mx, my);
      await sleep(0.6);
    } else throw new Error("unknown setup " + name);
  }

  // ---------- calibration marker: white blank page, then the dark title slide (found later in the video)
  await sleep(1.0);
  const timeline = { part, scenes: [], sentences: [], tDark: null };
  let first = true, warmP = null;
  for (const scene of plan) {
    const sceneStart = now();
    if (scene.kind === "slide") {
      await page.goto(`${SLIDES}?slide=${scene.slide}`);
      await page.evaluate(() => document.fonts.ready);
      await page.mouse.move(mx, my);
      if (first) {
        timeline.tDark = now();
        // pre-load the live pages in a second tab (same context, so the same HTTP cache) while the first slides play:
        // the switch from a slide to the app is then instant instead of a blank page
        warmP = (async () => {
          const w = await ctx.newPage();
          for (const u of WARM[part]) await w.goto(u, { waitUntil: "networkidle" }).catch(() => {});
          await w.close();
        })();
      }
    } else if (scene.setup) {
      await setup(scene.setup);
    }
    if (first) await sleep(LEAD); else await sleep(0.5);
    first = false;
    timeline.scenes.push({ id: scene.id, start: sceneStart, speechStart: now() });
    for (const s of scene.sentences) {
      const start = now();
      timeline.sentences.push({ scene: scene.id, i: s.i, start, dur: s.dur, shown: s.shown, wav: s.wav });
      let act = Promise.resolve();
      if (s.act) {
        if (s.act.startsWith("reveal:")) act = page.evaluate((n) => window.step(n), Number(s.act.split(":")[1]));
        else if (actions[s.act]) act = actions[s.act]();
        else throw new Error("unknown action " + s.act);
      }
      await act;
      const wait = start + s.dur + GAP - now();
      if (wait > 0) await sleep(wait);
      else if (wait < -0.05) console.log(`  note: action ${s.act} ran ${(-wait).toFixed(1)} s longer than its sentence (${scene.id}[${s.i}])`);
    }
    await sleep(HOLD);
    console.log(`${scene.id} done at ${now().toFixed(1)} s`);
  }
  if (warmP) await warmP;
  timeline.end = now();
  await sleep(1.0);
  const video = page.video();
  await ctx.close();
  fs.copyFileSync(await video.path(), path.join(outDir, `${part}.webm`));
  fs.writeFileSync(path.join(outDir, `${part}.timeline.json`), JSON.stringify(timeline, null, 1));
  await browser.close();
  console.log(`${part}: recorded ${timeline.end.toFixed(1)} s of events`);
})().catch((e) => { console.error("FAILED:", e.message); process.exit(1); });
