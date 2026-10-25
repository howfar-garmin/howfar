// HowFar race prep, in the browser: reads activities and courses (GPX or FIT), learns pace by
// slope and builds the course profile. A line-by-line copy of tools/wpeta (readers.py, model.py,
// learn.py, profile.py) so the texts it makes are the same as the Python tools'.
// web-tests/ checks that they match.

export const MIN_GRADE = -40;
export const MAX_GRADE = 40;
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

export function project(points, lat, lon) {
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

function nearBothEnds(points, lat, lon, maxOffset) {
  const first = points[0], end = points[points.length - 1];
  if (!first || first.lat == null || end.lat == null) return false;
  return haversine(lat, lon, first.lat, first.lon) <= maxOffset && haversine(lat, lon, end.lat, end.lon) <= maxOffset;
}

/** Course points sorted by distance; waypoints placed at the nearest track point, dropped when
 *  more than MAX_WAYPOINT_OFFSET metres off the track (race files often carry the whole race's).
 *  So is a finish that isn't at the end of the track (another race's finish the course passes
 *  by). On a loop, a finish near both the start and the end is put at the end, and any other
 *  point near both at the start. */
export function courseFrom(parsed, maxOffset = MAX_WAYPOINT_OFFSET) {
  const cps = parsed.coursePoints.slice();
  const skipped = [];
  const otherFinishes = []; // also in skipped; with their place, for the race prep page
  const pts = parsed.points;
  const length = pts.length ? pts[pts.length - 1].dist : 0;
  for (const w of parsed.waypoints) {
    let { dist, offset } = project(pts, w.lat, w.lon);
    if (offset <= maxOffset && FINISH_WORDS.test(w.name) && dist < length - 1000) {
      const end = pts[pts.length - 1];
      if (end.lat != null && haversine(w.lat, w.lon, end.lat, end.lon) <= maxOffset) dist = length;
      else {
        otherFinishes.push({ name: w.name, dist });
        offset = Infinity;
      }
    } else if (offset <= maxOffset && !FINISH_WORDS.test(w.name) && nearBothEnds(pts, w.lat, w.lon, maxOffset)) {
      dist = 0; // a loop's start: the nearest track point may be the one the run ended on
    }
    if (offset <= maxOffset) cps.push({ name: w.name, dist });
    else skipped.push(w.name);
  }
  cps.sort((a, b) => a.dist - b.dist); // stable, like Python's sort
  return { points: parsed.points, coursePoints: cps, skipped, otherFinishes };
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
