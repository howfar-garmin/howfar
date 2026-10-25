// HowFar? race prep, in the browser: reads activities and courses (GPX or FIT), learns pace by
// slope and builds the course profile. A line-by-line copy of tools/wpeta (readers.py, model.py,
// learn.py, profile.py) so the texts it makes are the same as the Python tools'.
// web-tests/ checks that they match.

export const NUM_BINS = 41;
export const MIN_GRADE = -40;
export const MAX_GRADE = 40;
export const BIN_STEP = 2;
export const MODEL_PREFIX = "v1";
export const PROFILE_PREFIX = "p1";
export const FINISH_NAME = "*";
export const STEPS = [25, 50, 100, 200, 400];
export const MAX_WAYPOINT_OFFSET = 200; // metres: farther waypoints aren't on this course
const FINISH_WORDS = /(^|[^\p{L}\p{N}_])(finish|arrivo|arriv[ée]e|ziel|llegada)(?![\p{L}\p{N}_])/iu;

const EARTH_RADIUS = 6371008.8;
const SEMICIRCLE_TO_DEG = 180 / 2 ** 31;

export function clamp(x, lo, hi) {
  return x < lo ? lo : x > hi ? hi : x;
}

// Python's round(): halves go to the even neighbour
export function pyRound(x) {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// Python's f"{x:.2f}"
export function fmt2(x) {
  const s = x.toFixed(2);
  // toFixed rounds exact halves away from zero; Python rounds them to even
  const scaled = x * 100;
  if (Math.abs(scaled - Math.trunc(scaled)) === 0.5) return (pyRound(scaled) / 100).toFixed(2);
  return s;
}

export function haversine(lat1, lon1, lat2, lon2) {
  const rad = (d) => (d * Math.PI) / 180;
  const p1 = rad(lat1), p2 = rad(lat2);
  const dp = p2 - p1;
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS * Math.asin(Math.sqrt(a));
}

// ---------------------------------------------------------------- readers

function fillDistances(points) {
  let total = 0;
  let prev = null;
  for (const p of points) {
    if (prev !== null && p.lat != null && p.lon != null && prev.lat != null && prev.lon != null) {
      total += haversine(prev.lat, prev.lon, p.lat, p.lon);
    }
    p.dist = total;
    prev = p;
  }
}

function project(points, lat, lon) {
  let best = null, bestD = Infinity;
  for (const p of points) {
    if (p.lat == null) continue;
    const d = haversine(lat, lon, p.lat, p.lon);
    if (d < bestD) { bestD = d; best = p; }
  }
  return { dist: best.dist, offset: bestD };
}

function local(el) {
  return el.localName || (el.nodeName || "").split(":").pop();
}

function child(el, name) {
  for (let c = el.firstChild; c; c = c.nextSibling) if (c.nodeType === 1 && local(c) === name) return c;
  return null;
}

function text(el) {
  return el ? (el.textContent || "") : "";
}

/** GPX text -> { points, waypoints }. parseXml(text) returns a DOM Document. */
export function readGpx(xmlText, parseXml) {
  const doc = parseXml(xmlText);
  const root = doc.documentElement;
  let trkpts = Array.from(doc.getElementsByTagNameNS("*", "trkpt"));
  if (!trkpts.length) trkpts = Array.from(doc.getElementsByTagNameNS("*", "rtept"));
  const points = [];
  let t0 = null;
  for (const e of trkpts) {
    const ele = child(e, "ele");
    const tm = child(e, "time");
    let t = null;
    if (tm && text(tm).trim()) {
      const ms = Date.parse(text(tm).trim());
      if (t0 === null) t0 = ms;
      t = (ms - t0) / 1000;
    }
    const eleText = text(ele).trim();
    points.push({
      t,
      dist: 0,
      alt: ele && eleText ? parseFloat(eleText) : null,
      speed: null,
      lat: parseFloat(e.getAttribute("lat")),
      lon: parseFloat(e.getAttribute("lon")),
    });
  }
  fillDistances(points);
  const startTime = t0 !== null ? new Date(t0).toISOString() : null;
  const waypoints = [];
  for (let c = root.firstChild; c; c = c.nextSibling) {
    if (c.nodeType !== 1 || local(c) !== "wpt") continue;
    const n = child(c, "name");
    waypoints.push({ name: n ? text(n).trim() : "", lat: parseFloat(c.getAttribute("lat")), lon: parseFloat(c.getAttribute("lon")) });
  }
  return { points, waypoints, coursePoints: [], startTime };
}

/** Decoded FIT messages (Garmin FIT SDK for JavaScript) -> { points, waypoints, coursePoints }. */
export function readFitMessages(messages) {
  const points = [];
  let t0 = null;
  let hasDist = true;
  for (const r of messages.recordMesgs || []) {
    let t = null;
    if (r.timestamp != null) {
      const ms = new Date(r.timestamp).getTime();
      if (t0 === null) t0 = ms;
      t = (ms - t0) / 1000;
    }
    if (r.distance == null) hasDist = false;
    const alt = r.enhancedAltitude ?? r.altitude;
    const speed = r.enhancedSpeed ?? r.speed;
    points.push({
      t,
      dist: r.distance != null ? Number(r.distance) : 0,
      alt: alt != null ? Number(alt) : null,
      speed: speed != null ? Number(speed) : null,
      lat: r.positionLat != null ? r.positionLat * SEMICIRCLE_TO_DEG : null,
      lon: r.positionLong != null ? r.positionLong * SEMICIRCLE_TO_DEG : null,
    });
  }
  const coursePoints = [];
  const waypoints = [];
  for (const c of messages.coursePointMesgs || []) {
    const name = c.name != null ? String(c.name) : "";
    if (c.distance != null) coursePoints.push({ name, dist: Number(c.distance) });
    else if (c.positionLat != null && c.positionLong != null) {
      waypoints.push({ name, lat: c.positionLat * SEMICIRCLE_TO_DEG, lon: c.positionLong * SEMICIRCLE_TO_DEG });
    }
  }
  if (!hasDist) fillDistances(points);
  return { points, waypoints, coursePoints, startTime: t0 !== null ? new Date(t0).toISOString() : null };
}

/** Course points sorted by distance; waypoints placed at the nearest track point, dropped when
 *  more than MAX_WAYPOINT_OFFSET metres off the track (race files often carry the whole race's).
 *  So is a finish that isn't at the end of the track (another race's finish the course passes
 *  by); a finish near both the start and the end of a loop is put at the end. */
export function courseFrom(parsed, maxOffset = MAX_WAYPOINT_OFFSET) {
  const cps = parsed.coursePoints.slice();
  const skipped = [];
  const pts = parsed.points;
  const length = pts.length ? pts[pts.length - 1].dist : 0;
  for (const w of parsed.waypoints) {
    let { dist, offset } = project(pts, w.lat, w.lon);
    if (offset <= maxOffset && FINISH_WORDS.test(w.name) && dist < length - 1000) {
      const end = pts[pts.length - 1];
      if (end.lat != null && haversine(w.lat, w.lon, end.lat, end.lon) <= maxOffset) dist = length;
      else offset = Infinity;
    }
    if (offset <= maxOffset) cps.push({ name: w.name, dist });
    else skipped.push(w.name);
  }
  cps.sort((a, b) => a.dist - b.dist); // stable, like Python's sort
  return { points: parsed.points, coursePoints: cps, skipped };
}

// ---------------------------------------------------------------- pace model

export function binIndex(gradePct) {
  const g = clamp(gradePct, MIN_GRADE, MAX_GRADE);
  return Math.min(NUM_BINS - 1, Math.trunc((g - MIN_GRADE) / BIN_STEP + 0.5));
}

export function binCenter(i) {
  return MIN_GRADE + i * BIN_STEP;
}

/** Per-bin mean pace (s/m) and weight; strings and speed() use m/s. */
export class Layer {
  constructor(paces, weights) {
    this.paces = paces ? paces.slice() : new Array(NUM_BINS).fill(0);
    this.weights = weights ? weights.slice() : new Array(NUM_BINS).fill(0);
  }
  addPace(i, pace, weight = 1) {
    if (weight <= 0) return;
    const w = this.weights[i] + weight;
    this.paces[i] += ((pace - this.paces[i]) * weight) / w;
    this.weights[i] = w;
  }
  add(i, speed, weight = 1) {
    if (speed > 0) this.addPace(i, 1 / speed, weight);
  }
  speed(i) {
    return this.paces[i] > 0 ? 1 / this.paces[i] : 0;
  }
  totalWeight() {
    return this.weights.reduce((a, b) => a + b, 0);
  }
  /** Adds another layer's observations, as if they had been added one by one. */
  merge(other) {
    for (let i = 0; i < NUM_BINS; i++) this.addPace(i, other.paces[i], other.weights[i]);
  }
  toString() {
    const parts = [MODEL_PREFIX];
    for (let i = 0; i < NUM_BINS; i++) {
      const w = pyRound(this.weights[i]);
      if (w > 0) parts.push(`${binCenter(i)}:${fmt2(this.speed(i))}:${w}`);
    }
    return parts.join(";");
  }
}

/** Turns 1 Hz (time, distance, altitude) samples into (grade, speed) observations. */
export class GradeTracker {
  constructor() {
    this.WINDOW = 60; this.EMIT_EVERY = 25; this.SIZE = 300;
    this.STOP_WINDOW = 60; this.STOP_DIST = 15; this.STOP_SIZE = 90;
    this.MIN_SPEED = 0.2; this.MAX_SPEED = 10;
    this.reset();
  }
  reset() {
    this.d = new Array(this.SIZE).fill(0); this.a = new Array(this.SIZE).fill(0); this.tt = new Array(this.SIZE).fill(0);
    this.head = 0; this.count = 0;
    this.sd = new Array(this.STOP_SIZE).fill(0); this.st = new Array(this.STOP_SIZE).fill(0);
    this.shead = 0; this.scount = 0;
    this.lastEmit = null; this.lastTime = null;
    this.movingTime = 0; this.observations = 0;
    this.lastGrade = 0; this.lastSpeed = 0; this.lastDist = 0;
  }
  isMoving(t, dist) {
    this.sd[this.shead] = dist; this.st[this.shead] = t;
    this.shead = (this.shead + 1) % this.STOP_SIZE;
    if (this.scount < this.STOP_SIZE) this.scount++;
    for (let k = 1; k < this.scount; k++) {
      const idx = (this.shead - 1 - k + this.STOP_SIZE) % this.STOP_SIZE;
      if (this.st[idx] <= t - this.STOP_WINDOW) return dist - this.sd[idx] >= this.STOP_DIST;
    }
    return true;
  }
  update(t, dist, alt) {
    const moving = this.isMoving(t, dist);
    if (this.lastTime !== null) {
      const dt = t - this.lastTime;
      if (dt > 0 && dt < 30 && moving) this.movingTime += dt;
    }
    this.lastTime = t;
    if (!moving) return false;
    this.d[this.head] = dist; this.a[this.head] = alt; this.tt[this.head] = this.movingTime;
    this.head = (this.head + 1) % this.SIZE;
    if (this.count < this.SIZE) this.count++;
    if (this.lastEmit === null) { this.lastEmit = dist; return false; }
    if (dist - this.lastEmit < this.EMIT_EVERY) return false;
    for (let k = 1; k < this.count; k++) {
      const idx = (this.head - 1 - k + this.SIZE) % this.SIZE;
      if (this.d[idx] <= dist - this.WINDOW) {
        const dd = dist - this.d[idx];
        const dt = this.movingTime - this.tt[idx];
        this.lastEmit = dist;
        if (dt <= 0) return false;
        const v = dd / dt;
        if (v < this.MIN_SPEED || v > this.MAX_SPEED) return false;
        this.lastGrade = clamp(((alt - this.a[idx]) / dd) * 100, MIN_GRADE, MAX_GRADE);
        this.lastSpeed = v; this.lastDist = dd;
        this.observations++;
        return true;
      }
    }
    return false;
  }
}

/** An activity's pace layer and a summary for the library. */
export function learnActivity(points) {
  const tracker = new GradeTracker();
  const layer = new Layer();
  for (const p of points) {
    if (p.t == null || p.alt == null) continue;
    if (tracker.update(p.t, p.dist, p.alt)) layer.add(binIndex(tracker.lastGrade), tracker.lastSpeed, 1);
  }
  const up = climb(points);
  const timed = points.filter((p) => p.t != null);
  return {
    layer,
    observations: tracker.observations,
    km: points.length ? points[points.length - 1].dist / 1000 : 0,
    up,
    hours: timed.length ? timed[timed.length - 1].t / 3600 : 0,
    movingHours: tracker.movingTime / 3600,
  };
}

/** Total climb in metres, ignoring wobbles under 3 m (barometer and GPS noise). For display. */
export function climb(points) {
  let up = 0, ref = null;
  for (const p of points) {
    if (p.alt == null) continue;
    if (ref === null) ref = p.alt;
    else if (p.alt - ref >= 3) { up += p.alt - ref; ref = p.alt; }
    else if (ref - p.alt >= 3) ref = p.alt;
  }
  return up;
}

// ---------------------------------------------------------------- course profile

function cleanName(name) {
  const n = Array.from(name).map((ch) => (";|,".includes(ch) ? " " : ch)).join("").trim();
  return n && n !== FINISH_NAME ? n : "?";
}

export class Elevation {
  constructor(points) {
    const pts = points.filter((p) => p.alt != null).map((p) => [p.dist, p.alt]);
    pts.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
    this.d = []; this.a = [];
    for (const [d, a] of pts) {
      if (this.d.length && d <= this.d[this.d.length - 1]) continue;
      this.d.push(d); this.a.push(a);
    }
    if (this.d.length < 2) throw new Error("The course file has no elevation data.");
  }
  get length() { return this.d[this.d.length - 1]; }
  at(dist) {
    if (dist <= this.d[0]) return this.a[0];
    if (dist >= this.d[this.d.length - 1]) return this.a[this.a.length - 1];
    let lo = 0, hi = this.d.length; // bisect_right
    while (lo < hi) { const mid = (lo + hi) >> 1; if (dist < this.d[mid]) hi = mid; else lo = mid + 1; }
    const j = lo;
    const d0 = this.d[j - 1], d1 = this.d[j];
    return this.a[j - 1] + ((this.a[j] - this.a[j - 1]) * (dist - d0)) / (d1 - d0);
  }
}

function segmentGrades(elev, start, end, step) {
  const grades = [];
  let d = start;
  while (d < end - 0.5) {
    const nxt = Math.min(d + step, end);
    const g = ((elev.at(nxt) - elev.at(d)) / (nxt - d)) * 100;
    grades.push(pyRound(clamp(g, MIN_GRADE, MAX_GRADE) * 10));
    d = nxt;
  }
  return grades.length ? grades : [0];
}

export function buildEntries(points, coursePoints, step) {
  const elev = new Elevation(points);
  const entries = [];
  let prev = 0;
  for (const cp of coursePoints) {
    const end = clamp(cp.dist, prev, elev.length);
    entries.push([cleanName(cp.name), Math.max(1, pyRound(end - prev)), segmentGrades(elev, prev, end, step)]);
    prev = end;
  }
  if (elev.length - prev > 10) entries.push([FINISH_NAME, pyRound(elev.length - prev), segmentGrades(elev, prev, elev.length, step)]);
  return entries;
}

export function profileString(entries, step) {
  return [PROFILE_PREFIX, String(step), ...entries.map(([n, len, g]) => `${n}|${len}|${g.join(",")}`)].join(";");
}

/** The profile text at the given step, or at the finest step that fits in maxLen characters. */
export function bestProfile(points, coursePoints, maxLen, step = null) {
  let s, text, entries;
  for (s of step ? [step] : STEPS) {
    entries = buildEntries(points, coursePoints, s);
    text = profileString(entries, s);
    if (step || text.length <= maxLen) break;
  }
  return { step: s, text, entries };
}
