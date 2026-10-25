// HowFar race prep page: course profile and checkpoints, library. Everything runs
// in the browser; files are never uploaded. The calculations are in howfar-core.js.
import * as core from "./howfar-core.js?v=7";
import * as extra from "./extra-points.js?v=6";

const FIT_SDK = "https://cdn.jsdelivr.net/npm/@garmin/fitsdk@21.217.0/+esm";
const JSZIP = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
const STORE_KEY = "howfar.library.v1";
const SVGNS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
// the page's language (tools/build_site.py): translated messages and numbers
const LANG = window.HOWFAR_LANG || "en";
const _t = window._t || ((s, v) => (v ? s.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m)) : s));
const dec = (x, n) => x.toLocaleString(LANG, { minimumFractionDigits: n, maximumFractionDigits: n });

// ---------------------------------------------------------------- small helpers

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const km = (m) => dec(m / 1000, 1) + " km";
const num = (n) => Math.round(n).toLocaleString(LANG);
const pad = (n) => (n < 10 ? "0" : "") + n;
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
const dateLabel = (iso) => (iso ? new Date(iso).toLocaleDateString(LANG, { year: "numeric", month: "short", day: "numeric" }) : "–");
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
    s.onerror = () => reject(new Error(_t("Couldn't load {src}. Check your internet connection.", { src })));
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
      if (!inner.length) throw new Error(_t("{file} has no GPX or FIT file inside.", { file: f.name }));
      for (const z of inner) {
        const name = z.name.split("/").pop();
        out.push(name.toLowerCase().endsWith(".fit")
          ? { name, kind: "fit", data: await z.async("arraybuffer") }
          : { name, kind: "gpx", data: await z.async("string") });
      }
    } else if (lower.endsWith(".fit")) out.push({ name: f.name, kind: "fit", data: await f.arrayBuffer() });
    else if (lower.endsWith(".gpx")) out.push({ name: f.name, kind: "gpx", data: await f.text() });
    else throw new Error(_t("{file} isn't a GPX, FIT or ZIP file.", { file: f.name }));
  }
  return out;
}

async function parse(file) {
  if (file.kind === "gpx") {
    const parsed = core.readGpx(file.data, (t) => new DOMParser().parseFromString(t, "application/xml"));
    if (!parsed.points.length) throw new Error(_t("{file} has no track in it.", { file: file.name }));
    return parsed;
  }
  const { Decoder, Stream } = await import(FIT_SDK);
  const decoder = new Decoder(Stream.fromArrayBuffer(file.data));
  if (!decoder.isFIT()) throw new Error(_t("{file} isn't a valid FIT file.", { file: file.name }));
  const { messages } = decoder.read();
  return core.readFitMessages(messages);
}

async function copyText(text, button) {
  const done = (label) => { button.textContent = label; setTimeout(() => (button.textContent = _t("Copy")), 1800); };
  try {
    await navigator.clipboard.writeText(text);
    done(_t("Copied") + " ✓");
  } catch (e) {
    const pre = button.closest(".string-box").querySelector("pre");
    const r = document.createRange(); r.selectNodeContents(pre);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    done(_t("Selected: press Copy"));
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
    // libraries from before HowFar learned only on the run also hold paces, now unused
    if (lib && Array.isArray(lib.courses)) return lib;
  } catch (e) { /* private window or blocked storage: start empty */ }
  return { version: 1, courses: [] };
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

/** onPick(metres): called with the course distance clicked, when points can be added. */
function drawCourse(profile, checkpoints, onPick) {
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
    el("circle", { cx: x, cy: y, r: c.minor ? 3 : 4.5, fill: "var(--surface)", stroke: c.minor ? "var(--ink-3)" : "var(--ink)", "stroke-width": 1.5 }, svg);
    const label = c.name.length > 22 ? c.name.slice(0, 21) + "…" : c.name;
    txt(svg, x, row ? 36 : 18, label, { "text-anchor": x > E.W - 90 ? "end" : x < E.l + 60 ? "start" : "middle", fill: c.minor ? "var(--ink-3)" : "var(--ink-2)" });
    row = 1 - row;
  });
  svg.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const d = Math.min(dmax, Math.max(0, ((((e.clientX - r.left) / r.width) * E.W - E.l) / (E.W - E.l - E.r)) * dmax));
    const p = profile.reduce((best, q) => (Math.abs(q[0] - d) < Math.abs(best[0] - d) ? q : best), profile[0]);
    tip(box, `<b>${km(p[0])}</b> · ${num(p[1])} m` + (onPick ? "<br>" + _t("Click to add a point here") : ""), e);
  };
  svg.onmouseleave = () => tip(box, null);
  svg.onclick = onPick ? (e) => {
    const r = svg.getBoundingClientRect();
    onPick(Math.min(dmax, Math.max(0, ((((e.clientX - r.left) / r.width) * E.W - E.l) / (E.W - E.l - E.r)) * dmax)));
  } : null;
  svg.classList.toggle("pickable", !!onPick);
}

// ---------------------------------------------------------------- what's open

/** The name of what's open, and whether it's in the library, at the top of its section. */
function showLoaded(kind, item, fallback) {
  $(kind + "Title").textContent = item.name.trim() || fallback;
  const state = $(kind + "State");
  const saved = item.id && library.courses.some((x) => x.id === item.id);
  state.textContent = !saved ? _t("Not saved yet") : item.dirty ? _t("Changed since you saved it") : _t("Saved in your library");
  state.className = "loaded-state" + (saved && !item.dirty ? " saved" : "");
  $(kind + "SaveTop").hidden = saved && !item.dirty;
}

$("courseSaveTop").addEventListener("click", () => $("courseSave").click());

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

// ---------------------------------------------------------------- step 1: course

// dirty: changed since it was last saved or opened from the library
// candidates: every checkpoint found on the course, { name, dist, on }; unticked ones are left out
const course = { id: null, name: "", file: "", parsed: null, view: null, candidates: null, offTrack: 0, dirty: false };

// A minor point's name starts with "+" in the profile text: the watch counts down to the main
// points and shows the next minor one on the way. Added points are minor unless you switch them.
const MINOR_MARK = "+";
const isMinor = (c) => (c.minor != null ? c.minor : !!c.added);

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
    const minor = name.startsWith(MINOR_MARK);
    if (name !== core.FINISH_NAME) checkpoints.push({ name: minor ? name.slice(1) : name, minor, d: at, alt: Math.round(elev.at(at)), seg: len, climb: climbM });
    else checkpoints.push({ name: _t("Finish"), d: at, alt: Math.round(elev.at(at)), seg: len, climb: climbM, finish: true });
  }
  return { step, text, profile, checkpoints, length: elev.length, up: core.climb(points) };
}

function renderCourse() {
  const v = course.view;
  $("courseResult").hidden = !v;
  if (!v) return;
  const real = v.checkpoints.filter((c) => !c.finish);
  $("courseDrop").classList.add("compact");
  $("courseDropTitle").textContent = _t("Replace the course");
  $("addPoints").hidden = !course.parsed;
  $("readOnlyNote").hidden = !!course.parsed;
  const has = (kinds) => (course.candidates || []).some((c) => kinds.includes(c.added));
  $("removeClimbs").hidden = !has(["top", "bottom"]);
  $("removePlaces").hidden = !has(["hut", "village"]);
  $("removeOwn").hidden = !has(["own"]);
  $("courseSummary").innerHTML = `<b>${esc(course.file)}</b>: ` + (real.length === 1
    ? _t("{len}, {up} m of climbing, 1 checkpoint.", { len: km(v.length), up: num(v.up) })
    : _t("{len}, {up} m of climbing, {n} checkpoints.", { len: km(v.length), up: num(v.up), n: real.length }));
  drawCourse(v.profile, v.checkpoints, course.parsed ? pickOwn : null);
  const ADDED = { top: _t("top of a climb"), bottom: _t("bottom of a climb"), hut: _t("hut"), village: _t("village"), own: _t("your point") };
  const tag = (c) => (c.added ? `<span class="added-tag">${_t("added: {what}", { what: ADDED[c.added] || c.added })}</span>` : "");
  const kindText = (minor) => (minor ? _t("Minor") : _t("Main"));
  const kind = (c, i) => (i == null ? `<span class="kind${c.minor ? " minor" : ""}">${kindText(c.minor)}</span>`
    : `<button type="button" class="kind${c.minor ? " minor" : ""}" data-kind="${i}" title="${esc(_t("Switch between main and minor"))}">${kindText(c.minor)}</button>`);
  const row = (c, pick, i) => `<tr${c.minor ? ' class="minor-row"' : ""}><td>${pick}${esc(c.name)}${pick ? "</label>" : ""}${tag(c)}</td><td class="num">${dec(c.d / 1000, 1)}</td><td class="num">${km(c.seg)}</td><td class="num">${num(c.climb)} m</td><td>${kind(c, i)}</td></tr>`;
  const cands = course.parsed && course.candidates;
  $("coursePickNote").hidden = !cands || !cands.length;
  if (cands) {
    // kept candidates and the profile's checkpoints are in the same order
    let k = 0;
    $("courseRows").innerHTML = cands.map((c, i) => {
      const box = `<label class="cp-pick"><input type="checkbox" data-cp="${i}"${c.on ? " checked" : ""}>`;
      if (c.on) return row(real[k++], box, i);
      return `<tr class="off"><td>${box}${esc(c.name)}</label>${tag(c)}</td><td class="num">${dec(c.dist / 1000, 1)}</td><td class="num">–</td><td class="num">–</td><td></td></tr>`;
    }).join("") + v.checkpoints.filter((c) => c.finish).map((c) => row(c, "")).join("");
  } else {
    $("courseRows").innerHTML = v.checkpoints.map((c) => row(c, "")).join("");
  }
  const warn = [];
  if (!real.length) warn.push(_t("This course has no checkpoints, so HowFar will only count down to the finish. If the race publishes a file with checkpoints, use that one."));
  const offTrack = course.candidates ? course.offTrack : (course.skipped || []).length;
  if (offTrack) warn.push(offTrack === 1
    ? _t("1 checkpoint was left out because it isn't on this course's track (race files often list the whole race's).")
    : _t("{n} checkpoints were left out because they aren't on this course's track (race files often list the whole race's).", { n: offTrack }));
  const finishes = (cands || []).filter((c) => c.finish && !c.on);
  if (finishes.length) warn.push(_t("Unticked: {names}, a finish line the course passes by but doesn't end at, probably another race's. Tick it if it's a checkpoint of this race.", { names: finishes.map((c) => "“" + c.name + "”").join(", ") }));
  $("courseWarn").hidden = !warn.length;
  $("courseWarn").textContent = warn.join(" ");
  $("courseMeta").innerHTML = _t("The text for the setting <b>“Course profile”</b> · one slope every {step} m · {n} characters", { step: v.step, n: num(v.text.length) });
  $("courseText").textContent = v.text;
  showLoaded("course", course, _t("Untitled course"));
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
  course.view = courseView(c.points, picked.map((p) => ({ name: (isMinor(p) ? MINOR_MARK : "") + p.name.replace(/^\++/, ""), dist: p.dist })),
    Number($("courseMax").value));
  let k = 0;
  for (const cp of course.view.checkpoints) if (!cp.finish && picked[k]) cp.added = picked[k++].added;
  renderCourse();
}

// ---------------------------------------------------------------- step 1: adding points

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
  const found = extra.climbPoints(core.courseFrom(course.parsed).points, Number($("climbMin").value), courseCheckpoints(), others,
    { top: _t("Top"), bottom: _t("Bottom") });
  addPoints(kinds, found);
  status($("addStatus"), found.length
    ? _t("Added {n} climb tops and bottoms.", { n: found.length })
    : _t("No climbs that big on this course, away from its checkpoints. Try a smaller size."));
});

$("addPlaces").addEventListener("click", async (e) => {
  if (!course.parsed || !course.candidates) return;
  const btn = e.currentTarget, st = $("addStatus");
  const points = core.courseFrom(course.parsed).points;
  btn.disabled = true;
  status(st, _t("Asking OpenStreetMap…"));
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 90000);
    const res = await fetch(extra.OVERPASS_URL, { method: "POST", body: new URLSearchParams({ data: extra.overpassQuery(points) }), signal: ctl.signal });
    clearTimeout(timer);
    if (!res.ok) throw Object.assign(new Error([429, 502, 503, 504].includes(res.status) ? _t("OpenStreetMap is busy right now. Try again in a minute.") : _t("OpenStreetMap answered with an error ({code}).", { code: res.status })), { osm: true });
    const kinds = ["hut", "village"];
    const others = course.candidates.filter((c) => c.added && !kinds.includes(c.added));
    const found = extra.placePoints(await res.json(), points, core.project, courseCheckpoints(), others);
    addPoints(kinds, found);
    status(st, found.length ? _t("Added {n} huts and villages.", { n: found.length }) : _t("OpenStreetMap has no named huts or villages along this course, away from its checkpoints."));
  } catch (err) {
    status(st, err.name === "AbortError" ? _t("OpenStreetMap didn't answer in time. Try again later.") : err.osm ? err.message : _t("Couldn't reach OpenStreetMap. Check your connection and try again."), true);
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
    status($("addStatus"), _t("Couldn't make the FIT file: {why}", { why: err.message }), true);
  } finally {
    btn.disabled = false;
  }
});

// a point of your own: a name and where it is, typed or clicked on the chart
function pickOwn(metres) {
  $("ownKm").value = (Math.round(metres / 100) / 10).toFixed(1);
  $("ownName").focus();
  status($("addStatus"), _t("Picked km {km}. Give it a name and press Add.", { km: dec(metres / 1000, 1) }));
}

$("addOwn").addEventListener("click", () => {
  if (!course.parsed || !course.candidates) return;
  const st = $("addStatus");
  const name = $("ownName").value.replace(/^[\s+]+/, "").trim();
  const at = Number(String($("ownKm").value).replace(",", ".")) * 1000;
  const length = core.courseFrom(course.parsed).points.slice(-1)[0].dist;
  if (!name) return status(st, _t("Give the point a name."), true);
  if (!(at > 0 && at < length)) return status(st, _t("Choose a place between km 0 and km {km}.", { km: dec(length / 1000, 1) }), true);
  const near = course.candidates.find((c) => c.on && Math.abs(c.dist - at) < 100);
  if (near) return status(st, _t("“{name}” is already within 100 m of there.", { name: near.name }), true);
  course.candidates = course.candidates.concat([{ name, dist: at, on: true, added: "own" }]).sort((a, b) => a.dist - b.dist);
  course.dirty = true;
  $("courseSaved").textContent = "";
  $("ownName").value = "";
  $("ownKm").value = "";
  recomputeCourse();
  status(st, _t("Added “{name}” at km {km}.", { name, km: dec(at / 1000, 1) }));
});
$("ownName").addEventListener("keydown", (e) => { if (e.key === "Enter") $("addOwn").click(); });
$("ownKm").addEventListener("keydown", (e) => { if (e.key === "Enter") $("addOwn").click(); });

$("removeOwn").addEventListener("click", () => {
  addPoints(["own"], []);
  status($("addStatus"), _t("Removed your points."));
});

$("removeClimbs").addEventListener("click", () => {
  addPoints(["top", "bottom"], []);
  status($("addStatus"), _t("Removed the climb tops and bottoms."));
});
$("removePlaces").addEventListener("click", () => {
  addPoints(["hut", "village"], []);
  status($("addStatus"), _t("Removed the huts and villages."));
});

$("courseRows").addEventListener("click", (e) => {
  const b = e.target.closest("[data-kind]");
  if (!b || !course.candidates) return;
  const c = course.candidates[Number(b.dataset.kind)];
  c.minor = !isMinor(c);
  course.dirty = true;
  $("courseSaved").textContent = "";
  recomputeCourse();
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
    status(st, _t("Opening the course…"));
    const files = await expand([fileList[0]]);
    const f = files[0];
    status(st, _t("Reading {file}…", { file: f.name }));
    await new Promise((r) => setTimeout(r, 0));
    const parsed = await parse(f);
    if (!parsed.points.some((p) => p.alt != null)) throw new Error(_t("{file} has no elevation data, so no profile can be made from it.", { file: f.name }));
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
renamer("course", course, _t("Untitled course"));
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
  $("courseSaved").textContent = ok ? _t("Saved in your library.") : _t("Couldn't save: this browser blocks storage. Use a backup file.");
  course.dirty = !ok;
  showLoaded("course", course, _t("Untitled course"));
  renderLibrary();
});
dropZone($("courseDrop"), $("courseFile"), addCourseFile);

// ---------------------------------------------------------------- library view

function libItem(kind, item, meta) {
  return `<li class="lib-item">
    <div><b>${esc(item.name)}</b><span class="small muted">${meta}</span></div>
    <div class="lib-actions">
      <button type="button" class="btn small-btn" data-open="${kind}:${item.id}">${_t("Open")}</button>
      <button type="button" class="btn small-btn" data-copy="${kind}:${item.id}">${_t("Copy text")}</button>
      <button type="button" class="btn small-btn danger" data-delete="${kind}:${item.id}">${_t("Delete")}</button>
    </div></li>`;
}

function renderLibrary() {
  $("libCourses").innerHTML = library.courses.length
    ? library.courses.map((c) => libItem("course", c, _t("{len} · {n} checkpoints · saved {date}", { len: km(c.length), n: c.checkpoints.filter((x) => !x.finish).length, date: dateLabel(c.saved) }))).join("")
    : `<li class="lib-empty small muted">${_t("Nothing saved yet. Make one in step 1 and press “Save in my library”.")}</li>`;
}

$("library").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const id = (b.dataset.open || b.dataset.copy || b.dataset.delete || ":").split(":")[1];
  const list = library.courses;
  const item = list.find((x) => x.id === id);
  if (!item) return;
  if (b.dataset.copy) {
    navigator.clipboard.writeText(item.text).then(() => { b.textContent = _t("Copied") + " ✓"; setTimeout(() => (b.textContent = _t("Copy text")), 1800); },
      () => { b.textContent = _t("Open it to copy"); });
  } else if (b.dataset.delete) {
    if (b.dataset.armed) {
      list.splice(list.indexOf(item), 1);
      saveLibrary();
      renderLibrary();
    } else {
      b.dataset.armed = "1";
      b.textContent = _t("Sure? Delete");
      setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.textContent = _t("Delete"); } }, 3000);
    }
  } else {
    const editable = !!(item.track && item.candidates);
    Object.assign(course, {
      id: item.id, name: item.name, file: item.file, skipped: item.skipped, dirty: false,
      parsed: editable ? { points: expandTrack(item.track), waypoints: [], coursePoints: [] } : null,
      candidates: editable ? item.candidates.map((c) => ({ ...c })) : null, offTrack: item.offTrack || 0,
      view: { step: item.step, text: item.text, profile: item.profile, checkpoints: item.checkpoints, length: item.length, up: item.up },
    });
    $("courseSaved").textContent = _t("Opened from your library.");
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
  $("backupStatus").textContent = _t("Backup file saved to your downloads.");
});
$("backupLoad").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    if (!Array.isArray(data.courses)) throw new Error();
    let added = 0;
    for (const c of data.courses) if (!library.courses.some((x) => x.id === c.id)) { library.courses.push(c); added++; }
    saveLibrary();
    renderLibrary();
    $("backupStatus").textContent = added ? _t("Added {n} items from the backup.", { n: added }) : _t("Everything in that backup is already here.");
  } catch (err) {
    $("backupStatus").textContent = _t("That file isn't a HowFar backup.");
  }
});

renderLibrary();
