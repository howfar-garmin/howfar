// Checks docs/js/extra-points.js: climb tops and bottoms, and huts and villages from an
// OpenStreetMap answer. Run: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import * as core from "../docs/js/howfar-core.js";
import * as extra from "../docs/js/extra-points.js";

// 20 km, north along a meridian: up 600 m to km 5, down 400 m to km 9, up 300 m to km 14,
// then down to the finish, with a 20 m bump at km 17 that is no climb
function course() {
  const knots = [[0, 1000], [5000, 1600], [9000, 1200], [14000, 1500], [16800, 1300], [17000, 1320], [17200, 1300], [20000, 1100]];
  const pts = [];
  for (let d = 0; d <= 20000; d += 10) {
    let j = 0;
    while (j + 1 < knots.length - 1 && knots[j + 1][0] <= d) j++;
    const [d0, a0] = knots[j], [d1, a1] = knots[j + 1];
    pts.push({ dist: d, alt: a0 + ((a1 - a0) * (d - d0)) / (d1 - d0), lat: 45 + d / 111320, lon: 7 });
  }
  return pts;
}

test("climb tops and bottoms", () => {
  const found = extra.climbPoints(course(), 200);
  assert.deepEqual(found.map((p) => [p.name, Math.round(p.dist / 100) / 10, p.added]), [
    ["Top 1600m", 5, "top"],
    ["Bottom 1200m", 9, "bottom"],
    ["Top 1500m", 14, "top"],
  ]);
  // a bigger size keeps only the big climb; a checkpoint next to a top leaves it out
  assert.deepEqual(extra.climbPoints(course(), 450).map((p) => p.name), ["Top 1600m"]);
  assert.deepEqual(extra.climbPoints(course(), 200, [{ name: "Col", dist: 5100 }]).map((p) => p.name), ["Bottom 1200m", "Top 1500m"]);
});

test("huts and villages along the course", () => {
  const pts = course();
  const at = (d, offLon = 0) => ({ lat: 45 + d / 111320, lon: 7 + offLon });
  const data = {
    elements: [
      { type: "node", ...at(5000), tags: { tourism: "alpine_hut", name: "Rifugio Alto" } },
      { type: "way", center: at(12000, 0.001), tags: { amenity: "shelter", name: "Bivacco" } }, // ~80 m off
      { type: "node", ...at(9000, 0.01), tags: { place: "village", name: "Far Away" } }, // ~790 m off
      { type: "node", ...at(16000), tags: { place: "hamlet", name: "Borgo" } },
      { type: "node", ...at(16100), tags: { place: "hamlet", name: "Borgo" } }, // mapped twice
      { type: "node", ...at(16600), tags: { place: "hamlet", name: "Vicino" } }, // too close to Borgo
      { type: "node", ...at(11800), tags: { place: "village", name: "Paese" } }, // too close to the hut
      { type: "node", ...at(7000), tags: { place: "village", name: "Alto" } }, // the checkpoint "Rif. Alto" already has the name
      { type: "node", ...at(3000), tags: { tourism: "alpine_hut" } }, // no name
    ],
  };
  const found = extra.placePoints(data, pts, core.project, [{ name: "Rif. Alto", dist: 5050 }]);
  assert.deepEqual(found.map((p) => [p.name, p.added]), [["Bivacco", "hut"], ["Borgo", "village"]]);
});

test("the OpenStreetMap question holds only a rectangle", () => {
  const q = extra.overpassQuery(course());
  const boxes = [...q.matchAll(/\(([\d.,-]+)\)/g)].map((m) => m[1]);
  assert.equal(new Set(boxes).size, 1);
  const [s, w, n, e] = boxes[0].split(",").map(Number);
  assert.ok(s < 45 && n > 45 + 20000 / 111320 && w < 7 && e > 7);
});

test("the FIT course carries every checkpoint as a course point", async () => {
  const fit = await import("@garmin/fitsdk");
  const pts = course();
  const cps = [{ name: "Rifugio Alto", dist: 5000 }, { name: "Start Tor des Géants", dist: 100 }, { name: "Bottom 1200m", dist: 9000, added: "bottom" }, { name: "Finish", dist: 20000 }];
  const bytes = extra.courseFit(fit, "Test course", pts, cps);
  const { messages, errors } = new fit.Decoder(fit.Stream.fromByteArray(Array.from(bytes))).read();
  assert.equal(errors.length, 0);
  assert.equal(messages.fileIdMesgs[0].type, "course");
  assert.equal(messages.recordMesgs.length, pts.length);
  assert.deepEqual(messages.coursePointMesgs.map((c) => [c.name, Math.round(c.distance), c.type]),
    [["Rifugio Alto", 5000, "checkpoint"], ["Start Tor des G", 100, "checkpoint"], ["Bottom 1200m", 9000, "valley"], ["Finish", 20000, "checkpoint"]]);
  // and the page reads it back as the same course
  const back = core.courseFrom(core.readFitMessages(messages));
  assert.deepEqual(back.coursePoints.map((c) => c.name), ["Start Tor des G", "Rifugio Alto", "Bottom 1200m", "Finish"]);
});
