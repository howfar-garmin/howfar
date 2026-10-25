// HowFar? race prep page: pace from past activities, course profile, library. Everything runs
// in the browser; files are never uploaded. The calculations are in howfar-core.js.
import * as core from "./howfar-core.js?v=5";
import * as extra from "./extra-points.js?v=4";

const FIT_SDK = "https://cdn.jsdelivr.net/npm/@garmin/fitsdk@21.217.0/+esm";
const JSZIP = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
const STORE_KEY = "howfar.library.v1";
const SVGNS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- small helpers

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const km = (m) => (m / 1000).toFixed(1) + " km";
const num = (n) => Math.round(n).toLocaleString("en-US");
const pad = (n) => (n < 10 ? "0" : "") + n;
const hm = (h) => Math.floor(h) + ":" + pad(Math.round((h % 1) * 60) % 60) + " h";
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
const dateLabel = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "–");
const baseName = (f) => f.replace(/\.(gpx|fit)$/i, "");

function status(el, text, isError) {
  el.textContent = text || "";
  el.classList.toggle("error", !!isError);
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("Couldn't load " + src + ". Check your internet connection."));
    document.head.appendChild(s);
  });
}

/** Files (as chosen or dropped) -> [{ name, kind: "gpx" | "fit", data }], opening ZIPs. */
async function expand(fileList) {
  const out = [];
  for (const f of fileList) {
    const lower = f.name.toLowerCase();
    if (lower.endsWith(".zip")) {
      if (!window.JSZip) await loadScript(JSZIP);
      const zip = await window.JSZip.loadAsync(await f.arrayBuffer());
      const inner = Object.values(zip.files).filter((z) => !z.dir && /\.(gpx|fit)$/i.test(z.name));
      if (!inner.length) throw new Error(`${f.name} has no GPX or FIT file inside.`);
      for (const z of inner) {
        const name = z.name.split("/").pop();
        out.push(name.toLowerCase().endsWith(".fit")
          ? { name, kind: "fit", data: await z.async("arraybuffer") }
          : { name, kind: "gpx", data: await z.async("string") });
      }
    } else if (lower.endsWith(".fit")) out.push({ name: f.name, kind: "fit", data: await f.arrayBuffer() });
    else if (lower.endsWith(".gpx")) out.push({ name: f.name, kind: "gpx", data: await f.text() });
    else throw new Error(`${f.name} isn't a GPX, FIT or ZIP file.`);
  }
  return out;
}

async function parse(file) {
  if (file.kind === "gpx") {
    const parsed = core.readGpx(file.data, (t) => new DOMParser().parseFromString(t, "application/xml"));
    if (!parsed.points.length) throw new Error(`${file.name} has no track in it.`);
    return parsed;
  }
  const { Decoder, Stream } = await import(FIT_SDK);
  const decoder = new Decoder(Stream.fromArrayBuffer(file.data));
  if (!decoder.isFIT()) throw new Error(`${file.name} isn't a valid FIT file.`);
  const { messages } = decoder.read();
  return core.readFitMessages(messages);
}

async function copyText(text, button) {
  const done = (label) => { button.textContent = label; setTimeout(() => (button.textContent = "Copy"), 1800); };
  try {
    await navigator.clipboard.writeText(text);
    done("Copied ✓");
  } catch (e) {
    const pre = button.closest(".string-box").querySelector("pre");
    const r = document.createRange(); r.selectNodeContents(pre);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    done("Selected: press Copy");
  }
}

function dropZone(label, input, onFiles) {
  ["dragenter", "dragover"].forEach((ev) => label.addEventListener(ev, (e) => { e.preventDefault(); label.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => label.addEventListener(ev, (e) => { e.preventDefault(); label.classList.remove("over"); }));
  label.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files); });
  input.addEventListener("change", () => { if (input.files.length) onFiles(input.files); input.value = ""; });
}

// ---------------------------------------------------------------- library (this browser)

function loadLibrary() {
  try {
    const lib = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    if (lib && Array.isArray(lib.paces) && Array.isArray(lib.courses)) return lib;
  } catch (e) { /* private window or blocked storage: start empty */ }
  return { version: 1, paces: [], courses: [] };
}
let library = loadLibrary();
function saveLibrary() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(library)); return true; } catch (e) { return false; }
}
function upsert(list, item) {
  const i = list.findIndex((x) => x.id === item.id);
  if (i >= 0) list[i] = item; else list.unshift(item);
}

// ---------------------------------------------------------------- charts

function el(name, attrs, parent) {
  const n = document.createElementNS(SVGNS, name);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function txt(parent, x, y, s, attrs) {
  const t = el("text", Object.assign({ x, y, fill: "var(--ink-3)", "font-size": 12, "font-family": "var(--font-body)" }, attrs || {}), parent);
  t.textContent = s;
  return t;
}
function tip(box, html, evt) {
  let t = box.querySelector(".tip");
  if (!t) { t = document.createElement("div"); t.className = "tip"; box.appendChild(t); }
  if (html === null) { t.hidden = true; return; }
  t.innerHTML = html; t.hidden = false;
  const r = box.getBoundingClientRect();
  const x = evt.clientX - r.left, y = evt.clientY - r.top;
  t.style.left = Math.min(Math.max(8, x + 14), box.clientWidth - t.offsetWidth - 8) + "px";
  t.style.top = Math.max(4, y - 10) + "px";
}

function drawPace(layer) {
  const svg = $("paceChart"), box = $("paceChartBox");
  svg.replaceChildren();
  const M = { W: 640, H: 300, l: 44, r: 16, t: 16, b: 34 };
  const bins = [];
  for (let i = 0; i < core.NUM_BINS; i++) if (layer.weights[i] >= 3) bins.push([core.binCenter(i), layer.speed(i), layer.weights[i]]);
  const vmax = Math.max(1.2, Math.ceil((Math.max(...bins.map((b) => b[1]), 0) + 0.2) / 0.6) * 0.6);
  const mx = (g) => M.l + ((g + 40) / 80) * (M.W - M.l - M.r);
  const my = (v) => M.t + ((vmax - v) / vmax) * (M.H - M.t - M.b);
  for (let v = 0; v <= vmax + 1e-9; v += 0.6) {
    el("line", { x1: M.l, x2: M.W - M.r, y1: my(v), y2: my(v), stroke: "var(--line-soft)" }, svg);
    txt(svg, M.l - 6, my(v) + 4, v.toFixed(1), { "text-anchor": "end" });
  }
  [-40, -20, 0, 20, 40].forEach((g) => txt(svg, mx(g), M.H - 12, (g > 0 ? "+" : "") + g + "%", { "text-anchor": "middle" }));
  txt(svg, M.l + 4, M.t + 8, "m/s");
  if (bins.length) {
    el("polyline", { points: bins.map((b) => mx(b[0]).toFixed(1) + "," + my(b[1]).toFixed(1)).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 2.5, "stroke-linejoin": "round" }, svg);
    bins.forEach((b) => el("circle", { cx: mx(b[0]), cy: my(b[1]), r: 3, fill: "var(--accent)" }, svg));
  }
  const cross = el("line", { y1: M.t, y2: M.H - M.b, stroke: "var(--ink-3)", visibility: "hidden" }, svg);
  svg.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const g = (((e.clientX - r.left) / r.width) * M.W - M.l) / (M.W - M.l - M.r) * 80 - 40;
    const i = core.binIndex(g);
    cross.setAttribute("x1", mx(core.binCenter(i))); cross.setAttribute("x2", mx(core.binCenter(i))); cross.setAttribute("visibility", "visible");
    const c = core.binCenter(i);
    if (layer.weights[i] < 3) return tip(box, `<b>${c > 0 ? "+" : ""}${c}% slope</b><br>not enough data here`, e);
    const v = layer.speed(i), pace = 1000 / v;
    tip(box, `<b>${c > 0 ? "+" : ""}${c}% slope</b><br>${v.toFixed(2)} m/s · ${Math.floor(pace / 60)}:${pad(Math.round(pace % 60))} per km<br>${num(layer.weights[i])} samples`, e);
  };
  svg.onmouseleave = () => { tip(box, null); cross.setAttribute("visibility", "hidden"); };
}

function drawCourse(profile, checkpoints) {
  const svg = $("courseChart"), box = $("courseChartBox");
  svg.replaceChildren();
  const E = { W: 1000, H: 280, l: 52, r: 18, t: 56, b: 30 };
  const dmax = profile[profile.length - 1][0] || 1;
  const alts = profile.map((p) => p[1]);
  const y0 = Math.floor((Math.min(...alts) - 50) / 100) * 100, y1 = Math.ceil((Math.max(...alts) + 50) / 100) * 100;
  const ex = (d) => E.l + (d / dmax) * (E.W - E.l - E.r);
  const ey = (a) => E.H - E.b - ((a - y0) / (y1 - y0)) * (E.H - E.t - E.b);
  const stepA = Math.max(100, Math.ceil((y1 - y0) / 4 / 100) * 100);
  for (let a = y0; a <= y1; a += stepA) {
    el("line", { x1: E.l, x2: E.W - E.r, y1: ey(a), y2: ey(a), stroke: "var(--line-soft)" }, svg);
    txt(svg, E.l - 8, ey(a) + 4, num(a), { "text-anchor": "end" });
  }
  const kmStep = dmax > 60000 ? 20 : dmax > 25000 ? 10 : 5;
  for (let k = 0; k <= dmax / 1000; k += kmStep) txt(svg, ex(k * 1000), E.H - 10, k + " km", { "text-anchor": "middle" });
  const pts = profile.map((p) => ex(p[0]).toFixed(1) + "," + ey(p[1]).toFixed(1)).join(" ");
  el("polygon", { points: `${ex(0)},${ey(y0)} ${pts} ${ex(dmax)},${ey(y0)}`, fill: "var(--terrain)" }, svg);
  el("polyline", { points: pts, fill: "none", stroke: "var(--accent)", "stroke-width": 2 }, svg);
  let row = 0;
  checkpoints.forEach((c) => {
    const x = ex(c.d), y = ey(c.alt);
    el("line", { x1: x, x2: x, y1: y - 4, y2: row ? 40 : 22, stroke: "var(--line)", "stroke-dasharray": "2 3" }, svg);
    el("circle", { cx: x, cy: y, r: 4.5, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 1.5 }, svg);
    const label = c.name.length > 22 ? c.name.slice(0, 21) + "…" : c.name;
    txt(svg, x, row ? 36 : 18, label, { "text-anchor": x > E.W - 90 ? "end" : x < E.l + 60 ? "start" : "middle", fill: "var(--ink-2)" });
    row = 1 - row;
  });
  svg.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const d = Math.min(dmax, Math.max(0, ((((e.clientX - r.left) / r.width) * E.W - E.l) / (E.W - E.l - E.r)) * dmax));
    const p = profile.reduce((best, q) => (Math.abs(q[0] - d) < Math.abs(best[0] - d) ? q : best), profile[0]);
    tip(box, `<b>${km(p[0])}</b> · ${num(p[1])} m`, e);
  };
  svg.onmouseleave = () => tip(box, null);
}

// ---------------------------------------------------------------- step 1: pace

// dirty: changed since it was last saved or opened from the library
const pace = { id: null, name: "", activities: [], dirty: false };

/** The name of what's open, and whether it's in the library, at the top of its section. */
function showLoaded(kind, item, fallback) {
  $(kind + "Title").textContent = item.name.trim() || fallback;
  const state = $(kind + "State");
  const saved = item.id && library[kind === "pace" ? "paces" : "courses"].some((x) => x.id === item.id);
  state.textContent = !saved ? "Not saved yet" : item.dirty ? "Changed since you saved it" : "Saved in your library";
  state.className = "loaded-state" + (saved && !item.dirty ? " saved" : "");
  $(kind + "SaveTop").hidden = saved && !item.dirty;
}

for (const kind of ["pace", "course"]) $(kind + "SaveTop").addEventListener("click", () => $(kind + "Save").click());

/** The pencil next to the name: edit it in place; Enter or leaving the box keeps it, Esc doesn't. */
function renamer(kind, item, fallback) {
  const title = $(kind + "Title"), input = $(kind + "TitleInput"), btn = $(kind + "Rename");
  const start = () => {
    input.value = item.name;
    title.hidden = btn.hidden = true;
    input.hidden = false;
    input.focus();
    input.select();
  };
  const finish = (keep) => {
    if (input.hidden) return;
    const v = input.value.trim();
    if (keep && v !== item.name) {
      item.name = v;
      item.dirty = true;
      $(kind + "Saved").textContent = "";
    }
    input.hidden = true;
    title.hidden = btn.hidden = false;
    showLoaded(kind, item, fallback);
    if (!keep) btn.focus();
  };
  btn.addEventListener("click", start);
  title.addEventListener("click", start);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    else if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}

function paceLayer() {
  const layer = new core.Layer();
  for (const a of pace.activities) layer.merge(new core.Layer(a.paces, a.weights));
  return layer;
}

function renderPace() {
  $("paceResult").hidden = pace.activities.length === 0;
  if (!pace.activities.length) return;
  $("paceRows").innerHTML = pace.activities.map((a) => `
    <tr><td>${esc(a.file)}</td><td class="num">${dateLabel(a.date)}</td><td class="num">${km(a.km * 1000)}</td>
    <td class="num">${num(a.up)} m</td><td class="num">${hm(a.movingHours)}</td>
    <td class="num"><button type="button" class="btn small-btn" data-remove="${a.id}" aria-label="Remove ${esc(a.file)}">Remove</button></td></tr>`).join("");
  const layer = paceLayer();
  drawPace(layer);
  const samples = layer.totalWeight();
  $("paceNote").textContent = samples < 300
    ? `Only ${num(samples)} samples so far (about ${num(samples * 25 / 1000)} km). Add more activities for a steadier curve.`
    : `${num(samples)} samples, about ${num(samples * 25 / 1000)} km of moving data.`;
  $("paceText").textContent = layer.toString();
  showLoaded("pace", pace, "Untitled pace");
}

async function addPaceFiles(fileList) {
  const st = $("paceStatus");
  try {
    status(st, "Opening files…");
    const files = await expand(fileList);
    const problems = [];
    for (const f of files) {
      status(st, `Reading ${f.name}…`);
      await new Promise((r) => setTimeout(r, 0)); // let the message show before the work
      const parsed = await parse(f);
      const learned = core.learnActivity(parsed.points);
      if (learned.observations < 5) { problems.push(`${f.name} has no times or altitude, so no pace can be learned from it.`); continue; }
      pace.activities.push({
        id: newId(), file: f.name, date: parsed.startTime, km: learned.km, up: learned.up, hours: learned.hours,
        movingHours: learned.movingHours, obs: learned.observations, paces: learned.layer.paces, weights: learned.layer.weights,
      });
      pace.dirty = true;
    }
    if (!pace.name && pace.activities.length) pace.name = "My pace, " + new Date().toLocaleDateString(undefined, { month: "short", year: "numeric" });
    status(st, problems.join(" "), problems.length > 0);
    renderPace();
  } catch (e) {
    status(st, e.message, true);
  }
}

$("paceRows").addEventListener("click", (e) => {
  const id = e.target.getAttribute("data-remove");
  if (!id) return;
  pace.activities = pace.activities.filter((a) => a.id !== id);
  pace.dirty = true;
  renderPace();
});
renamer("pace", pace, "Untitled pace");
$("paceCopy").addEventListener("click", (e) => copyText($("paceText").textContent, e.currentTarget));
$("paceSave").addEventListener("click", () => {
  pace.id = pace.id || newId();
  pace.name = pace.name.trim() || "My pace";
  upsert(library.paces, { id: pace.id, name: pace.name, saved: new Date().toISOString(), activities: pace.activities, text: paceLayer().toString() });
  const ok = saveLibrary();
  $("paceSaved").textContent = ok ? "Saved in your library." : "Couldn't save: this browser blocks storage. Use a backup file.";
  pace.dirty = !ok;
  showLoaded("pace", pace, "Untitled pace");
  renderLibrary();
});
$("paceNew").addEventListener("click", () => {
  Object.assign(pace, { id: null, name: "", activities: [], dirty: false });
  $("paceSaved").textContent = "";
  status($("paceStatus"), "");
  renderPace();
});
dropZone($("paceDrop"), $("paceFiles"), addPaceFiles);

// ---------------------------------------------------------------- step 2: course

// candidates: every checkpoint found on the course, { name, dist, on }; unticked ones are left out
const course = { id: null, name: "", file: "", parsed: null, view: null, candidates: null, offTrack: 0, dirty: false };

function courseView(points, coursePoints, maxLen) {
  const { step, text, entries } = core.bestProfile(points, coursePoints, maxLen);
  const elev = new core.Elevation(points);
  const profile = [];
  const every = Math.max(50, elev.length / 400);
  for (let d = 0; d < elev.length; d += every) profile.push([Math.round(d), Math.round(elev.at(d))]);
  profile.push([Math.round(elev.length), Math.round(elev.at(elev.length))]);
  let at = 0;
  const checkpoints = [];
  for (const [name, len, grades] of entries) {
    at += len;
    const climbM = grades.reduce((s, g, i) => s + Math.max(0, g / 1000) * (i === grades.length - 1 ? len - step * (grades.length - 1) : step), 0);
    if (name !== core.FINISH_NAME) checkpoints.push({ name, d: at, alt: Math.round(elev.at(at)), seg: len, climb: climbM });
    else checkpoints.push({ name: "Finish", d: at, alt: Math.round(elev.at(at)), seg: len, climb: climbM, finish: true });
  }
  return { step, text, profile, checkpoints, length: elev.length, up: core.climb(points) };
}

function renderCourse() {
  const v = course.view;
  $("courseResult").hidden = !v;
  if (!v) return;
  const real = v.checkpoints.filter((c) => !c.finish);
  $("courseDrop").classList.add("compact");
  $("courseDropTitle").textContent = "Replace the course";
  $("addPoints").hidden = !course.parsed;
  $("readOnlyNote").hidden = !!course.parsed;
  const has = (kinds) => (course.candidates || []).some((c) => kinds.includes(c.added));
  $("removeClimbs").hidden = !has(["top", "bottom"]);
  $("removePlaces").hidden = !has(["hut", "village"]);
  $("courseSummary").innerHTML = `<b>${esc(course.file)}</b>: ${km(v.length)}, ${num(v.up)} m of climbing, ${real.length} checkpoint${real.length === 1 ? "" : "s"}.`;
  drawCourse(v.profile, v.checkpoints);
  const tag = (c) => (c.added ? `<span class="added-tag">added: ${extra.ADDED_LABELS[c.added]}</span>` : "");
  const row = (c, pick) => `<tr><td>${pick}${esc(c.name)}${pick ? "</label>" : ""}${tag(c)}</td><td class="num">${(c.d / 1000).toFixed(1)}</td><td class="num">${km(c.seg)}</td><td class="num">${num(c.climb)} m</td></tr>`;
  const cands = course.parsed && course.candidates;
  $("coursePickNote").hidden = !cands || !cands.length;
  if (cands) {
    // kept candidates and the profile's checkpoints are in the same order
    let k = 0;
    $("courseRows").innerHTML = cands.map((c, i) => {
      const box = `<label class="cp-pick"><input type="checkbox" data-cp="${i}"${c.on ? " checked" : ""}>`;
      if (c.on) return row(real[k++], box);
      return `<tr class="off"><td>${box}${esc(c.name)}</label>${tag(c)}</td><td class="num">${(c.dist / 1000).toFixed(1)}</td><td class="num">–</td><td class="num">–</td></tr>`;
    }).join("") + v.checkpoints.filter((c) => c.finish).map((c) => row(c, "")).join("");
  } else {
    $("courseRows").innerHTML = v.checkpoints.map((c) => row(c, "")).join("");
  }
  const warn = [];
  if (!real.length) warn.push("This course has no checkpoints, so HowFar? will only count down to the finish. If the race publishes a file with checkpoints, use that one.");
  const offTrack = course.candidates ? course.offTrack : (course.skipped || []).length;
  if (offTrack) warn.push(`${offTrack} checkpoint${offTrack === 1 ? " was" : "s were"} left out because ${offTrack === 1 ? "it isn't" : "they aren't"} on this course's track (race files often list the whole race's).`);
  const finishes = (cands || []).filter((c) => c.finish && !c.on);
  if (finishes.length) warn.push(`Unticked: ${finishes.map((c) => "“" + c.name + "”").join(", ")}, a finish line the course passes by but doesn't end at, probably another race's. Tick it if it's a checkpoint of this race.`);
  $("courseWarn").hidden = !warn.length;
  $("courseWarn").textContent = warn.join(" ");
  $("courseMeta").innerHTML = `The text for the setting <b>“Course profile”</b> · one slope every ${v.step} m · ${num(v.text.length)} characters`;
  $("courseText").textContent = v.text;
  showLoaded("course", course, "Untitled course");
}

function recomputeCourse() {
  if (!course.parsed) return;
  const c = core.courseFrom(course.parsed);
  if (!course.candidates) {
    course.candidates = c.coursePoints.map((p) => ({ name: p.name, dist: p.dist, on: true }))
      .concat(c.otherFinishes.map((p) => ({ name: p.name, dist: p.dist, on: false, finish: true })))
      .sort((a, b) => a.dist - b.dist);
    course.offTrack = c.skipped.length - c.otherFinishes.length;
  }
  const picked = course.candidates.filter((p) => p.on);
  course.view = courseView(c.points, picked.map((p) => ({ name: p.name, dist: p.dist })), Number($("courseMax").value));
  let k = 0;
  for (const cp of course.view.checkpoints) if (!cp.finish && picked[k]) cp.added = picked[k++].added;
  renderCourse();
}

// ---------------------------------------------------------------- step 2: adding points

function addPoints(kind, found) {
  // a new run replaces the points the same button added before
  course.candidates = course.candidates.filter((c) => !kind.includes(c.added)).concat(found.map((p) => ({ ...p, on: true })))
    .sort((a, b) => a.dist - b.dist);
  course.dirty = true;
  $("courseSaved").textContent = "";
  recomputeCourse();
}

const courseCheckpoints = () => course.candidates.filter((c) => !c.added);

$("addClimbs").addEventListener("click", () => {
  if (!course.parsed || !course.candidates) return;
  const kinds = ["top", "bottom"];
  const others = course.candidates.filter((c) => c.added && !kinds.includes(c.added));
  const found = extra.climbPoints(core.courseFrom(course.parsed).points, Number($("climbMin").value), courseCheckpoints(), others);
  addPoints(kinds, found);
  status($("addStatus"), found.length
    ? `Added ${found.length} climb top${found.length === 1 ? "" : "s"} and bottom${found.length === 1 ? "" : "s"}.`
    : "No climbs that big on this course, away from its checkpoints. Try a smaller size.");
});

$("addPlaces").addEventListener("click", async (e) => {
  if (!course.parsed || !course.candidates) return;
  const btn = e.currentTarget, st = $("addStatus");
  const points = core.courseFrom(course.parsed).points;
  btn.disabled = true;
  status(st, "Asking OpenStreetMap…");
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 90000);
    const res = await fetch(extra.OVERPASS_URL, { method: "POST", body: new URLSearchParams({ data: extra.overpassQuery(points) }), signal: ctl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error([429, 502, 503, 504].includes(res.status) ? "OpenStreetMap is busy right now. Try again in a minute." : `OpenStreetMap answered with an error (${res.status}).`);
    const kinds = ["hut", "village"];
    const others = course.candidates.filter((c) => c.added && !kinds.includes(c.added));
    const found = extra.placePoints(await res.json(), points, core.project, courseCheckpoints(), others);
    addPoints(kinds, found);
    status(st, found.length ? `Added ${found.length} hut${found.length === 1 ? "" : "s"} and village${found.length === 1 ? "" : "s"}.` : "OpenStreetMap has no named huts or villages along this course, away from its checkpoints.");
  } catch (err) {
    status(st, err.name === "AbortError" ? "OpenStreetMap didn't answer in time. Try again later." : err.message.startsWith("OpenStreetMap") ? err.message : "Couldn't reach OpenStreetMap. Check your connection and try again.", true);
  } finally {
    btn.disabled = false;
  }
});

$("courseFit").addEventListener("click", async (e) => {
  if (!course.parsed || !course.candidates) return;
  const btn = e.currentTarget;
  btn.disabled = true;
  try {
    const fit = await import(FIT_SDK);
    const points = core.courseFrom(course.parsed).points;
    const name = course.name.trim() || baseName(course.file);
    const bytes = extra.courseFit(fit, name, points, course.candidates.filter((c) => c.on));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
    a.download = name.replace(/[^\w .,()-]+/g, "_") + ".fit";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  } catch (err) {
    status($("addStatus"), "Couldn't make the FIT file: " + err.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("removeClimbs").addEventListener("click", () => {
  addPoints(["top", "bottom"], []);
  status($("addStatus"), "Removed the climb tops and bottoms.");
});
$("removePlaces").addEventListener("click", () => {
  addPoints(["hut", "village"], []);
  status($("addStatus"), "Removed the huts and villages.");
});

$("courseRows").addEventListener("change", (e) => {
  const i = e.target.dataset && e.target.dataset.cp;
  if (i == null || !course.candidates) return;
  course.candidates[Number(i)].on = e.target.checked;
  course.dirty = true;
  $("courseSaved").textContent = "";
  recomputeCourse();
});

async function addCourseFile(fileList) {
  const st = $("courseStatus");
  try {
    status(st, "Opening the course…");
    const files = await expand([fileList[0]]);
    const f = files[0];
    status(st, `Reading ${f.name}…`);
    await new Promise((r) => setTimeout(r, 0));
    const parsed = await parse(f);
    if (!parsed.points.some((p) => p.alt != null)) throw new Error(`${f.name} has no elevation data, so no profile can be made from it.`);
    Object.assign(course, { id: null, name: baseName(f.name), file: f.name, parsed, candidates: null, dirty: true });
    $("courseSaved").textContent = "";
    recomputeCourse();
    status(st, "");
  } catch (e) {
    status(st, e.message, true);
  }
}

$("courseMax").addEventListener("change", () => {
  course.dirty = true;
  recomputeCourse();
});
renamer("course", course, "Untitled course");
$("courseCopy").addEventListener("click", (e) => copyText($("courseText").textContent, e.currentTarget));
/** The course's track, thinned to a point every 10 m or more and rounded, so a saved course
 *  can be opened and changed again without its file: [[dist, alt, lat, lon], ...]. */
function compactTrack(points) {
  const out = [];
  let last = -Infinity;
  points.forEach((p, i) => {
    if (p.dist - last < 10 && i < points.length - 1) return;
    last = p.dist;
    const r = (x, n) => (x == null ? null : Number(x.toFixed(n)));
    out.push([r(p.dist, 1), r(p.alt, 1), r(p.lat, 6), r(p.lon, 6)]);
  });
  return out;
}

const expandTrack = (track) => track.map(([dist, alt, lat, lon]) => ({ dist, alt, lat, lon }));

$("courseSave").addEventListener("click", () => {
  const v = course.view;
  course.id = course.id || newId();
  course.name = course.name.trim() || baseName(course.file);
  const before = library.courses.find((x) => x.id === course.id) || {};
  upsert(library.courses, {
    id: course.id, name: course.name, file: course.file, saved: new Date().toISOString(), text: v.text, step: v.step,
    length: v.length, up: v.up, profile: v.profile, checkpoints: v.checkpoints,
    skipped: course.candidates ? [] : before.skipped || [], offTrack: course.offTrack || 0,
    // what's needed to change it later
    track: course.parsed ? compactTrack(core.courseFrom(course.parsed).points) : before.track,
    candidates: course.candidates || before.candidates,
  });
  const ok = saveLibrary();
  $("courseSaved").textContent = ok ? "Saved in your library." : "Couldn't save: this browser blocks storage. Use a backup file.";
  course.dirty = !ok;
  showLoaded("course", course, "Untitled course");
  renderLibrary();
});
dropZone($("courseDrop"), $("courseFile"), addCourseFile);

// ---------------------------------------------------------------- library view

function libItem(kind, item, meta) {
  return `<li class="lib-item">
    <div><b>${esc(item.name)}</b><span class="small muted">${meta}</span></div>
    <div class="lib-actions">
      <button type="button" class="btn small-btn" data-open="${kind}:${item.id}">Open</button>
      <button type="button" class="btn small-btn" data-copy="${kind}:${item.id}">Copy text</button>
      <button type="button" class="btn small-btn danger" data-delete="${kind}:${item.id}">Delete</button>
    </div></li>`;
}

function renderLibrary() {
  $("libPaces").innerHTML = library.paces.length
    ? library.paces.map((p) => libItem("pace", p, `${p.activities.length} activit${p.activities.length === 1 ? "y" : "ies"} · saved ${dateLabel(p.saved)}`)).join("")
    : `<li class="lib-empty small muted">Nothing saved yet. Make one in step 1 and press “Save in my library”.</li>`;
  $("libCourses").innerHTML = library.courses.length
    ? library.courses.map((c) => libItem("course", c, `${km(c.length)} · ${c.checkpoints.filter((x) => !x.finish).length} checkpoints · saved ${dateLabel(c.saved)}`)).join("")
    : `<li class="lib-empty small muted">Nothing saved yet. Make one in step 2 and press “Save in my library”.</li>`;
}

$("library").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const [kind, id] = (b.dataset.open || b.dataset.copy || b.dataset.delete || ":").split(":");
  const list = kind === "pace" ? library.paces : library.courses;
  const item = list.find((x) => x.id === id);
  if (!item) return;
  if (b.dataset.copy) {
    navigator.clipboard.writeText(item.text).then(() => { b.textContent = "Copied ✓"; setTimeout(() => (b.textContent = "Copy text"), 1800); },
      () => { b.textContent = "Open it to copy"; });
  } else if (b.dataset.delete) {
    if (b.dataset.armed) {
      list.splice(list.indexOf(item), 1);
      saveLibrary();
      renderLibrary();
    } else {
      b.dataset.armed = "1";
      b.textContent = "Sure? Delete";
      setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.textContent = "Delete"; } }, 3000);
    }
  } else if (kind === "pace") {
    Object.assign(pace, { id: item.id, name: item.name, activities: item.activities.map((a) => ({ ...a })), dirty: false });
    $("paceSaved").textContent = "";
    renderPace();
    $("pace").scrollIntoView({ behavior: "smooth" });
  } else {
    const editable = !!(item.track && item.candidates);
    Object.assign(course, {
      id: item.id, name: item.name, file: item.file, skipped: item.skipped, dirty: false,
      parsed: editable ? { points: expandTrack(item.track), waypoints: [], coursePoints: [] } : null,
      candidates: editable ? item.candidates.map((c) => ({ ...c })) : null, offTrack: item.offTrack || 0,
      view: { step: item.step, text: item.text, profile: item.profile, checkpoints: item.checkpoints, length: item.length, up: item.up },
    });
    $("courseSaved").textContent = "Opened from your library.";
    renderCourse();
    $("course").scrollIntoView({ behavior: "smooth" });
  }
});

$("backupSave").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(library, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `howfar-library-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  $("backupStatus").textContent = "Backup file saved to your downloads.";
});
$("backupLoad").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    if (!Array.isArray(data.paces) || !Array.isArray(data.courses)) throw new Error();
    let added = 0;
    for (const p of data.paces) if (!library.paces.some((x) => x.id === p.id)) { library.paces.push(p); added++; }
    for (const c of data.courses) if (!library.courses.some((x) => x.id === c.id)) { library.courses.push(c); added++; }
    saveLibrary();
    renderLibrary();
    $("backupStatus").textContent = added ? `Added ${added} item${added === 1 ? "" : "s"} from the backup.` : "Everything in that backup is already here.";
  } catch (err) {
    $("backupStatus").textContent = "That file isn't a HowFar? backup.";
  }
});

renderLibrary();
