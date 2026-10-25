// Checks docs/js/howfar-core.js against the Python tools: same speed-model and course-profile texts.
// Fixtures and expected texts come from tools/tests/make_web_fixtures.py. Run: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DOMParser } from "@xmldom/xmldom";
import { Decoder, Stream } from "@garmin/fitsdk";
import * as core from "../docs/js/howfar-core.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const parseXml = (t) => new DOMParser().parseFromString(t, "text/xml");

function read(file) {
  if (file.toLowerCase().endsWith(".fit")) {
    const { messages, errors } = new Decoder(Stream.fromBuffer(fs.readFileSync(file))).read();
    assert.equal(errors.length, 0, `FIT errors in ${file}`);
    return core.readFitMessages(messages);
  }
  return core.readGpx(fs.readFileSync(file, "utf8"), parseXml);
}

function model(files) {
  const layer = new core.Layer();
  for (const f of files) layer.merge(core.learnActivity(read(f).points).layer);
  return layer.toString();
}

function profile(file) {
  const course = core.courseFrom(read(file));
  const { step, text } = core.bestProfile(course.points, course.coursePoints, 4000);
  return { step, text, skipped: course.skipped };
}

function check(expected, findFile) {
  for (const [name, want] of Object.entries(expected.models)) {
    test(`speed model: ${name}`, () => {
      assert.equal(model(name.split("+").map(findFile)), want);
    });
  }
  for (const [name, want] of Object.entries(expected.profiles)) {
    test(`course profile: ${name}`, () => {
      assert.deepEqual(profile(findFile(name)), want);
    });
  }
}

check(JSON.parse(fs.readFileSync(path.join(HERE, "fixtures/expected.json"), "utf8")), (n) => path.join(HERE, "fixtures", n));

// the private race files, when present on this computer (they are not in git)
const priv = path.join(HERE, "private-expected.json");
if (fs.existsSync(priv)) {
  check(JSON.parse(fs.readFileSync(priv, "utf8")), (n) => {
    for (const dir of ["samples", "courses"]) {
      const p = path.join(ROOT, dir, n);
      if (fs.existsSync(p)) return p;
    }
    throw new Error(`missing ${n}`);
  });
}

test("Python-style rounding", () => {
  assert.equal(core.pyRound(2.5), 2);
  assert.equal(core.pyRound(3.5), 4);
  assert.equal(core.pyRound(-48.5), -48);
  assert.equal(core.pyRound(-47.5), -48);
  assert.equal(core.fmt2(0.125), "0.12");
  assert.equal(core.fmt2(0.375), "0.38");
  assert.equal(core.fmt2(3.14159), "3.14");
});
