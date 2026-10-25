// HowFar? race prep: points to add to a course's checkpoints. The tops and bottoms of the big
// climbs, found on the course's elevation profile the way UltraTrailMate finds them (resample
// every 40 m with a 50 m median, keep the highs and lows that stand out by the chosen height,
// at least 900 m apart), and named huts and villages from OpenStreetMap next to the track.
// No imports, so web-tests/ can load it as it is; the page passes in what it needs.

export const OVERPASS_URL = "https://overpass-api.de/api/interpreter";

const STEP = 40; // m between profile samples
const WINDOW = 50; // m: median window around each sample
const MIN_SEP = 900; // m between two tops (or two bottoms)
const NEAR_CHECKPOINT = 300; // m: an added point this close to a checkpoint is left out
const NEAR_ADDED = 150; // m: or this close to another added point
const EDGE = 500; // m: nothing this close to the start or the finish
const MAX_OFF_TRACK = 200; // m: huts and villages farther from the track aren't on the way
const PLACE_SEP = 1000; // m between two added huts or villages; the more useful one stays
const PLACE_RANK = { hut: 0, town: 1, village: 2, hamlet: 3 };
const BBOX_BUFFER = 280; // m around the track to search

export const ADDED_LABELS = { top: "top of a climb", bottom: "bottom of a climb", hut: "hut", village: "village" };

function median(xs) {
  const s = xs.slice().sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** [dist, alt] every STEP metres, each the median of the track's altitudes within WINDOW. */
function resample(points) {
  const pts = points.filter((p) => p.alt != null);
  const out = [];
  if (pts.length < 2) return out;
  const total = pts[pts.length - 1].dist;
  let lo = 0, j = 0;
  for (let d = 0; d <= total; d += STEP) {
    while (lo < pts.length && pts[lo].dist < d - WINDOW / 2) lo++;
    const win = [];
    for (let k = lo; k < pts.length && pts[k].dist <= d + WINDOW / 2; k++) win.push(pts[k].alt);
    if (win.length) out.push([d, median(win)]);
    else {
      while (j + 1 < pts.length && pts[j + 1].dist < d) j++;
      const a = pts[j], b = pts[Math.min(j + 1, pts.length - 1)];
      const t = b.dist > a.dist ? (d - a.dist) / (b.dist - a.dist) : 0;
      out.push([d, a.alt + (b.alt - a.alt) * t]);
    }
  }
  return out;
}

/** The track's own altitude at dist (the median smooths sharp tops a little). */
function altAt(pts, dist) {
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pts[mid].dist <= dist) lo = mid; else hi = mid;
  }
  const a = pts[lo], b = pts[hi];
  return b.dist > a.dist ? a.alt + ((b.alt - a.alt) * Math.min(1, Math.max(0, (dist - a.dist) / (b.dist - a.dist)))) : a.alt;
}

/** How far a high stands above the lowest point you must go down to before anything higher. */
function prominence(e, i) {
  let left = e[i], right = e[i];
  for (let j = i - 1; j >= 0 && e[j] < e[i]; j--) left = Math.min(left, e[j]);
  for (let j = i + 1; j < e.length && e[j] < e[i]; j++) right = Math.min(right, e[j]);
  return e[i] - Math.max(left, right);
}

/** How far a low lies below the highest point you must go up to before anything lower. */
function depth(e, i) {
  let left = e[i], right = e[i];
  for (let j = i - 1; j >= 0 && e[j] > e[i]; j--) left = Math.max(left, e[j]);
  for (let j = i + 1; j < e.length && e[j] > e[i]; j++) right = Math.max(right, e[j]);
  return Math.min(left, right) - e[i];
}

function spaced(items) {
  const kept = [];
  for (const it of items.slice().sort((a, b) => b.size - a.size)) {
    if (!kept.some((k) => Math.abs(k.dist - it.dist) < MIN_SEP)) kept.push(it);
  }
  return kept;
}

/** Same place: one name contains the other ("La Thuile" and "La Thuile - Arpy"). */
function sameName(a, b) {
  a = a.toLowerCase().trim();
  b = b.toLowerCase().trim();
  return a.length >= 4 && b.length >= 4 && (a.includes(b) || b.includes(a));
}

function farFrom(dist, checkpoints, added) {
  return !checkpoints.some((c) => Math.abs(c.dist - dist) < NEAR_CHECKPOINT)
    && !added.some((c) => Math.abs(c.dist - dist) < NEAR_ADDED);
}

/** The tops and bottoms of the climbs with at least minClimb metres of climbing, as
 *  { name, dist, added: "top" | "bottom" }, leaving out those next to the given points. */
export function climbPoints(points, minClimb, checkpoints = [], added = []) {
  const withAlt = points.filter((p) => p.alt != null);
  const prof = resample(withAlt);
  if (prof.length < 3) return [];
  const e = prof.map((p) => p[1]);
  const total = prof[prof.length - 1][0];
  const tops = [], bottoms = [];
  for (let i = 1; i < e.length - 1; i++) {
    if (e[i] > e[i - 1] && e[i] >= e[i + 1]) {
      const size = prominence(e, i);
      if (size >= minClimb) tops.push({ dist: prof[i][0], alt: e[i], size, added: "top" });
    } else if (e[i] < e[i - 1] && e[i] <= e[i + 1]) {
      const size = depth(e, i);
      if (size >= minClimb) bottoms.push({ dist: prof[i][0], alt: e[i], size, added: "bottom" });
    }
  }
  return spaced(tops).concat(spaced(bottoms))
    .filter((p) => p.dist >= EDGE && p.dist <= total - EDGE && farFrom(p.dist, checkpoints, added))
    .sort((a, b) => a.dist - b.dist)
    .map((p) => ({ name: `${p.added === "top" ? "Top" : "Bottom"} ${Math.round(altAt(withAlt, p.dist))}m`, dist: p.dist, added: p.added }));
}

/** The Overpass question for named huts, shelters and villages around the track. Only the
 *  corners of this rectangle are sent, not the track. */
export function overpassQuery(points) {
  const ll = points.filter((p) => p.lat != null);
  const lats = ll.map((p) => p.lat), lons = ll.map((p) => p.lon);
  const dLat = BBOX_BUFFER / 111320;
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const dLon = BBOX_BUFFER / (111320 * Math.cos((midLat * Math.PI) / 180));
  const f = (x) => x.toFixed(5);
  const bbox = `${f(Math.min(...lats) - dLat)},${f(Math.min(...lons) - dLon)},${f(Math.max(...lats) + dLat)},${f(Math.max(...lons) + dLon)}`;
  return `[out:json][timeout:60];
(
  nwr["tourism"~"^(alpine_hut|wilderness_hut)$"]["name"](${bbox});
  nwr["amenity"="shelter"]["name"](${bbox});
  node["place"~"^(town|village|hamlet)$"]["name"](${bbox});
);
out center;`;
}

/** Overpass's answer as { name, dist, added: "hut" | "village" } on the track, using the
 *  page's project(points, lat, lon) -> { dist, offset }. */
export function placePoints(data, points, project, checkpoints = [], added = []) {
  const total = points.length ? points[points.length - 1].dist : 0;
  const found = [];
  for (const el of (data && data.elements) || []) {
    const tags = el.tags || {};
    const name = (tags.name || "").trim();
    const lat = el.lat != null ? el.lat : el.center && el.center.lat;
    const lon = el.lon != null ? el.lon : el.center && el.center.lon;
    if (!name || lat == null || lon == null) continue;
    const hut = /^(alpine_hut|wilderness_hut)$/.test(tags.tourism || "") || tags.amenity === "shelter";
    const village = /^(town|village|hamlet)$/.test(tags.place || "");
    if (!hut && !village) continue;
    const { dist, offset } = project(points, lat, lon);
    if (offset > MAX_OFF_TRACK || dist < EDGE || dist > total - EDGE) continue;
    found.push({ name, dist, added: hut ? "hut" : "village", rank: PLACE_RANK[hut ? "hut" : tags.place] });
  }
  // huts first, then towns, villages and hamlets; along the course within each
  found.sort((a, b) => a.rank - b.rank || a.dist - b.dist);
  const out = [];
  for (const p of found) {
    if (out.some((o) => o.name === p.name)) continue; // a village is often mapped more than once
    if (checkpoints.some((c) => sameName(c.name, p.name))) continue; // already a checkpoint
    if (out.some((o) => Math.abs(o.dist - p.dist) < PLACE_SEP)) continue;
    if (farFrom(p.dist, checkpoints, added)) out.push(p);
  }
  return out.sort((a, b) => a.dist - b.dist).map(({ name, dist, added: kind }) => ({ name, dist, added: kind }));
}

const COURSE_POINT_TYPE = { top: "summit", bottom: "valley", hut: "shelter", village: "generic" };
const SEMI = 2 ** 31 / 180;

/** Garmin course names hold 15 bytes of UTF-8: cut by bytes, not letters ("Géants"). */
function fitName(s) {
  const bytes = (t) => new TextEncoder().encode(t).length;
  let out = s;
  while (bytes(out) > 15) out = out.slice(0, -1);
  return out;
}

/** A FIT course file (Uint8Array) with the track and the given checkpoints as course points,
 *  for loading on the watch instead of the original. fit is Garmin's FIT SDK module (it has
 *  Encoder and Profile); points need lat, lon and dist; checkpoints are { name, dist, added? }.
 *  Times are made up at 3 m/s, as courses need them. */
export function courseFit(fit, name, points, checkpoints) {
  const { Encoder, Profile } = fit;
  const M = Profile.MesgNum;
  const pts = points.filter((p) => p.lat != null);
  const start = new Date(Date.UTC(2026, 0, 1, 6, 0, 0));
  const at = (dist) => new Date(start.getTime() + Math.round(dist / 3) * 1000);
  const semi = (deg) => Math.round(deg * SEMI);
  const where = (dist) => {
    let i = 0;
    while (i + 1 < pts.length && pts[i + 1].dist < dist) i++;
    const a = pts[i], b = pts[Math.min(i + 1, pts.length - 1)];
    const t = b.dist > a.dist ? Math.min(1, Math.max(0, (dist - a.dist) / (b.dist - a.dist))) : 0;
    return { lat: a.lat + (b.lat - a.lat) * t, lon: a.lon + (b.lon - a.lon) * t };
  };
  const first = pts[0], last = pts[pts.length - 1];
  const enc = new Encoder();
  enc.onMesg(M.FILE_ID, { type: "course", manufacturer: "development", product: 0, serialNumber: 1, timeCreated: start });
  enc.onMesg(M.COURSE, { name: fitName(name), sport: "running" });
  enc.onMesg(M.LAP, {
    timestamp: at(last.dist), startTime: start, totalElapsedTime: last.dist / 3, totalTimerTime: last.dist / 3,
    totalDistance: last.dist, startPositionLat: semi(first.lat), startPositionLong: semi(first.lon),
    endPositionLat: semi(last.lat), endPositionLong: semi(last.lon),
  });
  enc.onMesg(M.EVENT, { timestamp: start, event: "timer", eventType: "start", eventGroup: 0 });
  for (const p of pts) {
    const rec = { timestamp: at(p.dist), positionLat: semi(p.lat), positionLong: semi(p.lon), distance: p.dist };
    if (p.alt != null) rec.enhancedAltitude = p.alt;
    enc.onMesg(M.RECORD, rec);
  }
  for (const c of checkpoints) {
    const ll = where(c.dist);
    enc.onMesg(M.COURSE_POINT, {
      timestamp: at(c.dist), positionLat: semi(ll.lat), positionLong: semi(ll.lon), distance: c.dist,
      type: c.added ? COURSE_POINT_TYPE[c.added] : "checkpoint", name: fitName(c.name),
    });
  }
  enc.onMesg(M.EVENT, { timestamp: at(last.dist), event: "timer", eventType: "stopAll", eventGroup: 0 });
  return enc.close();
}
