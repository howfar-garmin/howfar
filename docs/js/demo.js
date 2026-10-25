// Sped-up replay of a recorded run through each step of the HowFar prediction
// (all predictions precomputed in demo/torx-s1.js by tools/research/demo_export.py).
(function () {
  "use strict";
  var D = window.HOWFAR_DEMO;
  if (!D) return;

  // frame columns
  var T = 0, CD = 1, ALT = 2, K = 3, DN = 4, ACT = 5, STOPA = 6, STOPNOW = 7, SCALE = 8, FLAT = 9, UP = 10, DOWN = 11, FAT = 12, ETA0 = 13;
  var F = D.frames, WP = D.waypoints, PROF = D.profile, C = D.configs;
  var tStart = F[0][T], tEnd = F[F.length - 1][T];
  var startMs = Date.parse(D.start);
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var idx = {};
  C.forEach(function (c, i) { idx[c.id] = i; });

  // the page's language (tools/build_site.py): translated messages and numbers
  var LANG = window.HOWFAR_LANG || "en";
  var _t = window._t || function (s, v) { return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s; };

  var NOTES = {
    none: _t("Your first race with HowFar, nothing pasted in its settings. It learns your pace on every slope from today's run as you go, and knows only how far away the checkpoint is and how much higher or lower (~)."),
    profile: _t("Your first race with HowFar, with the course profile pasted in its settings: it knows every climb and descent to the checkpoint (P). It learns your pace on every slope from today's run as you go.")
  };

  var state = { t: tStart + 2.17 * 3600, main: "profile", cmp: "average", speed: 300, playing: false, last: 0 };
  var $ = function (id) { return document.getElementById(id); };
  var SVGNS = "http://www.w3.org/2000/svg";

  // ---------- formatting
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function dur(s) {
    s = Math.max(0, Math.round(s));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(x) : m + ":" + pad(x);
  }
  // the countdown as the watch shows it (WpUtil.etaText): h:mm in 5-minute steps from an hour
  // out, whole minutes from 5 minutes out, m:ss in the last 5 minutes
  function etaStep(s) { return s >= 3450 ? 300 : s >= 300 ? 60 : 1; }
  function shownSec(s) {
    s = Math.max(0, Math.round(s));
    return Math.round(s / etaStep(s)) * etaStep(s);
  }
  function etaText(s) {
    var r = shownSec(s);
    if (r >= 3600) return [Math.floor(r / 3600) + ":" + pad(Math.floor((r % 3600) / 60)), "h"];
    if (r >= 300) return [String(Math.round(r / 60)), "min"];
    return [Math.floor(r / 60) + ":" + pad(r % 60), "min"];
  }
  // arrival clock, rounded like the countdown
  function arrival(raceSec, e) {
    var stepMs = (etaStep(e) >= 300 ? 5 : 1) * 60000;
    return clockFmt.format(new Date(Math.round((startMs + (raceSec + e) * 1000) / stepMs) * stepMs));
  }
  function hm(s) {
    s = Math.max(0, Math.round(s));
    return Math.floor(s / 3600) + " h " + pad(Math.floor((s % 3600) / 60)) + " min";
  }
  var clockFmt;
  try { clockFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" }); }
  catch (e) { clockFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }); }
  function clock(raceSec) { return clockFmt.format(new Date(startMs + raceSec * 1000)); }
  function dec(x, n) { return x.toLocaleString(LANG, { minimumFractionDigits: n, maximumFractionDigits: n }); }
  function km(m) { return dec(m / 1000, 1) + " km"; }
  function num(n) { return Math.round(n).toLocaleString(LANG); }
  function signedMin(s) {
    var m = s / 60;
    return (m >= 0 ? "+" : "−") + dec(Math.abs(m), 1) + " min";
  }
  // the prediction before rounding (the chart), and as the watch shows it (watch and readout)
  function eta(f, id) { return f[ETA0 + idx[id]]; }
  function err(f, id) { return eta(f, id) - (f[ACT] - f[STOPA]); }
  function shownEta(f, id) { return shownSec(eta(f, id)); }
  function shownErr(f, id) { return shownEta(f, id) - (f[ACT] - f[STOPA]); }
  function cfg(id) { return C[idx[id]]; }
  // the cases' names, short (chart, table) and next to the choice
  var LABELS = {
    average: [_t("Average pace so far"), ""],
    none: [_t("HowFar, no course profile"), _t("Nothing")],
    profile: [_t("HowFar with the course profile"), _t("The course profile")]
  };
  function label(id) { return LABELS[id] ? LABELS[id][0] : cfg(id).label; }

  function frameAt(t) {
    var lo = 0, hi = F.length - 1;
    while (lo < hi) {
      var mid = (lo + hi + 1) >> 1;
      if (F[mid][T] <= t) lo = mid; else hi = mid - 1;
    }
    return F[lo];
  }

  // ---------- watch + readout
  function render() {
    var f = frameAt(state.t);
    var wp = WP[f[K]];
    var e = shownEta(f, state.main);
    var marker = cfg(state.main).ahead ? "P " : "~ ";

    $("wLabel").textContent = marker + wp.name;
    var shown = etaText(e), learning = f[CD] < 4000; // the watch greys the time for its first ~4 km
    $("wTime").innerHTML = shown[0] + '<span class="w-unit">' + shown[1] + "</span>";
    $("wTime").classList.toggle("learning", learning);
    $("wArrive").textContent = "@ " + arrival(f[T], e) + (learning ? " " + _t("(learning)") : "");

    $("raceClock").textContent = dur(f[T]);
    $("rTime").innerHTML = _t("<b>{time}</b> · {clock} local time", { time: hm(f[T]), clock: clock(f[T]) }) +
      (f[STOPNOW] ? ' <span class="chip quiet">' + _t("Standing still") + "</span>" : "");
    $("rPos").innerHTML = _t("<b>{done}</b> of {total} · {alt} m", { done: km(f[CD]), total: km(WP[WP.length - 1].d), alt: num(f[ALT]) });
    var climb = wp.alt - f[ALT];
    $("rNext").innerHTML = "<b>" + wp.name + "</b> · " + (climb >= 0
      ? _t("{dist} ahead, {m} m higher", { dist: km(f[DN]), m: num(climb) })
      : _t("{dist} ahead, {m} m lower", { dist: km(f[DN]), m: num(-climb) }));
    $("rSays").innerHTML = _t("<b>{time}</b>, arriving at {clock}", { time: shown[0] + " " + shown[1], clock: arrival(f[T], e) });
    $("rActual").innerHTML = (f[STOPA] >= 60
      ? _t("<b>{time}</b>, arrived at {clock}, including {stop} min stopped", { time: dur(f[ACT]), clock: clock(f[T] + f[ACT]), stop: Math.round(f[STOPA] / 60) })
      : _t("<b>{time}</b>, arrived at {clock}", { time: dur(f[ACT]), clock: clock(f[T] + f[ACT]) }));
    var x = shownErr(f, state.main);
    var ok = Math.abs(x) <= 300;
    $("rErr").innerHTML = _t("<b>{err}</b> (not counting stops)", { err: signedMin(x) }) + " " +
      (ok ? '<span class="chip good">✓ ' + _t("Within 5 min") + "</span>"
          : '<span class="chip warn">! ' + (x < 0 ? _t("You got there later") : _t("You got there sooner")) + "</span>");

    var sc = f[SCALE], fa = f[FAT];
    var pct = function (r) { return Math.round(Math.abs(r - 1) * 100) + "%"; };
    $("lScale").innerHTML = sc >= 1
      ? _t("<b>Distance:</b> your watch measures <b>{pct} more</b> than the course map (switchbacks, GPS wobble), so it adjusts the distance left.", { pct: pct(sc) })
      : _t("<b>Distance:</b> your watch measures <b>{pct} less</b> than the course map (switchbacks, GPS wobble), so it adjusts the distance left.", { pct: pct(sc) });
    var perKm = function (v) { var p = Math.round(1000 / v); return Math.floor(p / 60) + ":" + pad(p % 60); };
    $("lForm").innerHTML = _t("<b>Your pace today:</b> {flat}/km on the flat, {up}/km up a 20% slope, {down}/km down one.",
      { flat: perKm(f[FLAT]), up: perKm(f[UP]), down: perKm(f[DOWN]) });
    $("lFatigue").innerHTML = Math.abs(fa - 1) < 0.01 ? _t("<b>Last couple of km:</b> on the pace it expected.")
      : fa > 1 ? _t("<b>Last couple of km:</b> <b>{pct} faster</b> than it expected.", { pct: pct(fa) })
      : _t("<b>Last couple of km:</b> <b>{pct} slower</b> than it expected.", { pct: pct(fa) });

    $("scrub").value = Math.round(((f[T] - tStart) / (tEnd - tStart)) * 1000);
    moveCursors(f);
  }

  // ---------- svg helpers
  function el(name, attrs, parent) {
    var n = document.createElementNS(SVGNS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function txt(parent, x, y, s, attrs) {
    var t = el("text", Object.assign({ x: x, y: y, fill: "var(--ink-3)", "font-size": 12, "font-family": "var(--font-body)" }, attrs || {}), parent);
    t.textContent = s;
    return t;
  }
  function tipShow(box, html, px, py) {
    var tip = box.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; box.appendChild(tip); }
    tip.innerHTML = html;
    tip.hidden = false;
    var bw = box.clientWidth, tw = tip.offsetWidth;
    tip.style.left = Math.min(Math.max(8, px + 14), bw - tw - 8) + "px";
    tip.style.top = Math.max(4, py - 10) + "px";
  }
  function tipHide(box) { var tip = box.querySelector(".tip"); if (tip) tip.hidden = true; }
  function svgPoint(svg, evt) {
    var r = svg.getBoundingClientRect();
    var vb = svg.viewBox.baseVal;
    return { x: ((evt.clientX - r.left) / r.width) * vb.width, y: ((evt.clientY - r.top) / r.height) * vb.height, px: evt.clientX - r.left, py: evt.clientY - r.top };
  }

  // ---------- elevation chart
  var E = { W: 1000, H: 300, l: 52, r: 18, t: 74, b: 30 };
  var maxD = WP[WP.length - 1].d;
  var elevAlts = PROF.map(function (p) { return p[1]; });
  E.y0 = Math.floor((Math.min.apply(null, elevAlts) - 100) / 200) * 200;
  E.y1 = Math.ceil((Math.max.apply(null, elevAlts) + 100) / 200) * 200;
  function ex(d) { return E.l + (d / maxD) * (E.W - E.l - E.r); }
  function ey(a) { return E.H - E.b - ((a - E.y0) / (E.y1 - E.y0)) * (E.H - E.t - E.b); }
  var elevCursor, elevAhead, elevDone, elevDot;

  function drawElevation() {
    var svg = $("elev");
    for (var a = E.y0; a <= E.y1; a += 400) {
      el("line", { x1: E.l, x2: E.W - E.r, y1: ey(a), y2: ey(a), stroke: "var(--line-soft)", "stroke-width": 1 }, svg);
      txt(svg, E.l - 8, ey(a) + 4, num(a), { "text-anchor": "end" });
    }
    for (var k = 0; k <= maxD / 1000; k += 5) {
      txt(svg, ex(k * 1000), E.H - 10, k + " km", { "text-anchor": "middle" });
    }
    var pts = PROF.map(function (p) { return ex(p[0]).toFixed(1) + "," + ey(p[1]).toFixed(1); });
    el("polygon", { points: ex(0) + "," + ey(E.y0) + " " + pts.join(" ") + " " + ex(PROF[PROF.length - 1][0]) + "," + ey(E.y0), fill: "var(--terrain)" }, svg);
    el("polyline", { points: pts.join(" "), fill: "none", stroke: "var(--ink-3)", "stroke-width": 1.5 }, svg);

    var defs = el("defs", {}, svg);
    elevDone = el("rect", { x: E.l, y: 0, width: 0, height: E.H }, el("clipPath", { id: "doneClip" }, defs));
    el("polyline", { points: pts.join(" "), fill: "none", stroke: "var(--ink)", "stroke-width": 2, "clip-path": "url(#doneClip)" }, svg);
    elevAhead = el("rect", { x: 0, y: 0, width: 0, height: E.H }, el("clipPath", { id: "aheadClip" }, defs));
    el("polyline", { points: pts.join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 3.5, "stroke-linecap": "round", "clip-path": "url(#aheadClip)" }, svg);

    var row = 0;
    WP.forEach(function (w, i) {
      if (i < D.firstWaypoint) return;
      var x = ex(w.d), y = ey(w.alt);
      el("line", { x1: x, x2: x, y1: y - 4, y2: row ? 46 : 26, stroke: "var(--line)", "stroke-width": 1, "stroke-dasharray": "2 3" }, svg);
      el("circle", { cx: x, cy: y, r: 4, fill: "var(--surface)", stroke: "var(--ink-2)", "stroke-width": 1.5 }, svg);
      var anchor = x > E.W - 90 ? "end" : x < E.l + 60 ? "start" : "middle";
      txt(svg, x, row ? 42 : 20, w.name.replace("BaseVita-", "Base vita "), { "text-anchor": anchor, fill: "var(--ink-2)" });
      row = 1 - row;
    });

    elevCursor = el("line", { y1: E.t - 6, y2: E.H - E.b, stroke: "var(--accent)", "stroke-width": 1, "stroke-dasharray": "3 3" }, svg);
    elevDot = el("circle", { r: 6, fill: "var(--accent)", stroke: "var(--surface)", "stroke-width": 2 }, svg);

    var box = $("elevBox");
    svg.addEventListener("mousemove", function (evt) {
      var p = svgPoint(svg, evt);
      var d = Math.min(maxD, Math.max(0, ((p.x - E.l) / (E.W - E.l - E.r)) * maxD));
      var alt = PROF[Math.min(PROF.length - 1, Math.round(d / 100))][1];
      tipShow(box, "<b>" + km(d) + "</b> · " + num(alt) + " m", p.px, p.py);
    });
    svg.addEventListener("mouseleave", function () { tipHide(box); });
    svg.addEventListener("click", function (evt) {
      var p = svgPoint(svg, evt);
      var d = ((p.x - E.l) / (E.W - E.l - E.r)) * maxD;
      for (var i = 0; i < F.length; i++) if (F[i][CD] >= d) { state.t = F[i][T]; break; }
      render();
    });
  }

  // ---------- error chart
  var R = { W: 1000, H: 270, l: 52, r: 44, t: 14, b: 32, y0: -45, y1: 25 };
  function rx(t) { return R.l + ((t - tStart) / (tEnd - tStart)) * (R.W - R.l - R.r); }
  function ry(m) { m = Math.max(R.y0, Math.min(R.y1, m)); return R.t + ((R.y1 - m) / (R.y1 - R.y0)) * (R.H - R.t - R.b); }
  var errCursor, lineMain, lineCmp;

  function seriesPoints(id) {
    return F.map(function (f) { return rx(f[T]).toFixed(1) + "," + ry(err(f, id) / 60).toFixed(1); }).join(" ");
  }
  function drawError() {
    var svg = $("err");
    el("rect", { x: R.l, y: ry(5), width: R.W - R.l - R.r, height: ry(-5) - ry(5), fill: "var(--band)" }, svg);
    [-40, -20, -5, 0, 5, 20].forEach(function (m) {
      el("line", { x1: R.l, x2: R.W - R.r, y1: ry(m), y2: ry(m), stroke: m === 0 ? "var(--ink-3)" : "var(--line-soft)", "stroke-width": 1 }, svg);
      txt(svg, R.l - 8, ry(m) + 4, (m > 0 ? "+" : m < 0 ? "−" : "") + Math.abs(m), { "text-anchor": "end" });
    });
    txt(svg, R.W - R.r + 6, ry(0) + 4, "min", {});
    for (var h = 0; h <= (tEnd - tStart) / 3600; h += 2) {
      txt(svg, rx(tStart + h * 3600), R.H - 10, h + " h", { "text-anchor": "middle" });
    }
    WP.forEach(function (w, i) {
      if (i < D.firstWaypoint || w.arrive == null) return;
      el("line", { x1: rx(w.arrive), x2: rx(w.arrive), y1: R.t, y2: R.H - R.b, stroke: "var(--line)", "stroke-width": 1, "stroke-dasharray": "2 4" }, svg);
    });
    lineCmp = el("polyline", { fill: "none", stroke: "var(--series-a)", "stroke-width": 1.75, "stroke-linejoin": "round" }, svg);
    lineMain = el("polyline", { fill: "none", stroke: "var(--series-p)", "stroke-width": 1.75, "stroke-linejoin": "round" }, svg);
    errCursor = el("line", { y1: R.t, y2: R.H - R.b, stroke: "var(--ink)", "stroke-width": 1.25 }, svg);

    var box = $("errBox");
    svg.addEventListener("mousemove", function (evt) {
      var p = svgPoint(svg, evt);
      var f = frameAt(tStart + ((p.x - R.l) / (R.W - R.l - R.r)) * (tEnd - tStart));
      tipShow(box, _t("<b>{time}</b> · to {name}", { time: hm(f[T]), name: WP[f[K]].name }) +
        '<br><i style="background:var(--series-p)"></i>' + label(state.main) + " " + signedMin(err(f, state.main)) +
        '<br><i style="background:var(--series-a)"></i>' + label(state.cmp) + " " + signedMin(err(f, state.cmp)), p.px, p.py);
    });
    svg.addEventListener("mouseleave", function () { tipHide(box); });
    svg.addEventListener("click", function (evt) {
      var p = svgPoint(svg, evt);
      state.t = Math.min(tEnd, Math.max(tStart, tStart + ((p.x - R.l) / (R.W - R.l - R.r)) * (tEnd - tStart)));
      render();
    });
  }
  function updateSeries() {
    lineMain.setAttribute("points", seriesPoints(state.main));
    lineCmp.setAttribute("points", seriesPoints(state.cmp));
    $("legMain").textContent = label(state.main);
    $("modeNote").textContent = NOTES[state.main] || "";
  }

  function moveCursors(f) {
    var x = ex(f[CD]);
    elevCursor.setAttribute("x1", x); elevCursor.setAttribute("x2", x);
    elevDot.setAttribute("cx", x); elevDot.setAttribute("cy", ey(f[ALT]));
    elevDone.setAttribute("width", Math.max(0, x - E.l));
    var xn = ex(WP[f[K]].d);
    elevAhead.setAttribute("x", x); elevAhead.setAttribute("width", Math.max(0, xn - x));
    var xt = rx(f[T]);
    errCursor.setAttribute("x1", xt); errCursor.setAttribute("x2", xt);
  }

  // ---------- method pickers and results table
  var STEPS = ["average", "none", "profile"], CHOICES = ["none", "profile"];
  function fillPicker(sel, value) {
    STEPS.forEach(function (id) {
      var o = document.createElement("option");
      o.value = id; o.textContent = label(id);
      sel.appendChild(o);
    });
    sel.value = value;
  }
  // the choice under the watch: one radio button per case
  function fillChoice(box, value) {
    CHOICES.forEach(function (id) {
      var l = document.createElement("label");
      var r = document.createElement("input");
      r.type = "radio"; r.name = "prepChoice"; r.value = id; r.checked = id === value;
      r.addEventListener("change", function () { if (r.checked) setMain(id); });
      l.appendChild(r);
      l.appendChild(document.createTextNode(" " + (LABELS[id] ? LABELS[id][1] : cfg(id).long)));
      box.appendChild(l);
    });
  }
  function setMain(id) {
    state.main = id;
    var r = document.querySelector('input[name="prepChoice"][value="' + id + '"]');
    if (r) r.checked = true;
    updateSeries(); render();
  }

  var SHORT = { TOR: "Tor 330", AW: "Abbots Way", S1: "TORX S1", AN: "La Via di Annibale", STL: "STL25" };
  function buildTable() {
    var table = $("results");
    var RACES = D.races, S = D.scores;
    var mean = function (id, m) {
      var t = 0;
      RACES.forEach(function (r) { t += S[id][r.key][m]; });
      return t / RACES.length;
    };
    var head = table.querySelector("thead tr");
    head.innerHTML = '<th scope="col">' + _t("Prediction") + "</th>" +
      RACES.map(function (r) { return '<th scope="col" class="num" title="' + _t("{race}: average minutes off", { race: r.name }) + '"><span class="race-name">' + (SHORT[r.key] || r.name) + "</span>" +
        (r.km ? ' <span class="race-km">(' + r.km.toLocaleString(LANG, { maximumFractionDigits: 1 }) + " km)</span>" : "") + "</th>"; }).join("") +
      '<th scope="col" class="num" title="' + _t("Average of the races") + '">' + _t("Average") + '</th><th scope="col" class="bar-col"><span class="sr-only">' + _t("Average, as a bar") + "</span></th>" +
      '<th scope="col" class="num" title="' + _t("Out of every 100 times the watch showed a time, how many were less than 5 minutes off") + '">' + _t("Less than 5 min off") + "</th>" +
      '<th scope="col" class="num" title="' + _t("Out of every 100 times the watch showed a time, how many were less than 15 minutes off") + '">' + _t("Less than 15 min off") + "</th>" +
      '<th scope="col" class="num" title="' + _t("How far off the watch was when you were 2 km from each checkpoint") + '">' + _t("Off by, 2 km before") + "</th>";
    var max = 0, best = STEPS[0];
    STEPS.forEach(function (id) {
      max = Math.max(max, mean(id, "mae_hour"));
      if (mean(id, "mae_hour") < mean(best, "mae_hour")) best = id;
    });
    var body = table.querySelector("tbody");
    STEPS.forEach(function (id) {
      var v = mean(id, "mae_hour");
      var row = document.createElement("tr");
      if (id === "profile") row.className = "current";
      var onWatch = CHOICES.indexOf(id) >= 0;
      if (onWatch) { row.tabIndex = 0; row.title = _t("Show on the watch"); } else row.className = "baseline";
      row.innerHTML = "<td>" + label(id) + "</td>" +
        RACES.map(function (r) { return '<td class="num">' + dec(S[id][r.key].mae_hour, 1) + " min</td>"; }).join("") +
        '<td class="num"><b>' + dec(v, 1) + " min</b></td>" +
        '<td><div class="bar' + (id === best ? " best" : "") + '" style="width:' + (v / max * 100).toFixed(1) + '%"></div></td>' +
        '<td class="num">' + Math.round(mean(id, "within5_hour") * 100) + "%</td>" +
        '<td class="num">' + Math.round(mean(id, "within15_hour") * 100) + "%</td>" +
        '<td class="num">' + dec(mean(id, "mae_2000"), 1) + " min</td>";
      var pick = function () { setMain(id); $("demo").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" }); };
      if (onWatch) {
        row.addEventListener("click", pick);
        row.addEventListener("keydown", function (e) { if (e.key === "Enter") pick(); });
      }
      body.appendChild(row);
    });
  }

  function fillTools() {
    $("profileString").textContent = D.profileString;
    $("profileMeta").textContent = _t("T1 course profile, one value per {step} m · {n} characters", { step: D.profileStep, n: num(D.profileString.length) });
    var entry = D.profileString.split(";").filter(function (e) { return e.indexOf("Col d'Arp|") === 0; })[0];
    if (entry) {
      var parts = entry.split("|"), grades = parts[2].split(",").slice(0, 6);
      $("decodeTitle").innerHTML = _t("How to read one entry:") + " <code>" + parts[0] + "|" + parts[1] + "|" + grades.join(",") + ",…</code>";
      var chips = ["<span>" + parts[0] + "</span>", "<span>" + _t("{dist} from the previous waypoint", { dist: km(+parts[1]) }) + "</span>"];
      grades.forEach(function (g) { chips.push("<span>" + _t("{step} m at {grade}%", { step: D.profileStep, grade: (g >= 0 ? "+" : "") + dec(g / 10, 1) }) + "</span>"); });
      chips.push("<span>…</span>");
      $("decode").innerHTML = chips.join("");
    }
    document.querySelectorAll("[data-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var pre = $(b.getAttribute("data-copy"));
        var done = function () { b.textContent = _t("Copied"); setTimeout(function () { b.textContent = _t("Copy"); }, 1500); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(pre.textContent).then(done, function () { selectText(pre); });
        } else selectText(pre);
      });
    });
  }
  function selectText(node) {
    var r = document.createRange(); r.selectNodeContents(node);
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }

  // ---------- playback
  function tick(now) {
    if (!state.playing) return;
    var dt = state.last ? (now - state.last) / 1000 : 0;
    state.last = now;
    state.t += dt * state.speed;
    if (state.t >= tEnd) { state.t = tEnd; setPlaying(false); }
    render();
    if (state.playing) requestAnimationFrame(tick);
  }
  function setPlaying(on) {
    state.playing = on;
    state.last = 0;
    $("play").textContent = on ? "❚❚ " + _t("Pause") : "▶ " + _t("Play");
    $("play").setAttribute("aria-label", on ? _t("Pause") : _t("Play"));
    if (on) {
      if (state.t >= tEnd) state.t = tStart;
      requestAnimationFrame(tick);
    }
  }

  $("play").addEventListener("click", function () { setPlaying(!state.playing); });
  document.querySelectorAll("[data-speed]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.speed = +b.getAttribute("data-speed");
      document.querySelectorAll("[data-speed]").forEach(function (o) { o.setAttribute("aria-pressed", o === b); });
    });
  });
  $("scrub").addEventListener("input", function () {
    state.t = tStart + (+$("scrub").value / 1000) * (tEnd - tStart);
    render();
  });
  fillChoice($("pickMain"), state.main);
  fillPicker($("pickCmp"), state.cmp);
  $("pickCmp").addEventListener("change", function () { state.cmp = this.value; updateSeries(); render(); });

  drawElevation();
  drawError();
  updateSeries();
  buildTable();
  fillTools();
  render();
  if (!reduceMotion) setPlaying(true);
})();
