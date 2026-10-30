// Sped-up replay of a recorded run through each step of the HowFar prediction
// (all predictions precomputed in demo/torx-s1.js by tools/research/demo_export.py).
(function () {
  "use strict";
  var D = window.HOWFAR_DEMO;
  if (!D) return;

  // frame columns
  var T = 0, CD = 1, ALT = 2, K = 3, DN = 4, ACT = 5, STOPA = 6, STOPNOW = 7, SCALE = 8, FLAT = 9, UP = 10, DOWN = 11, FAT = 12, STOPS = 13, ETA0 = 14;
  var F = D.frames, WP = D.waypoints, PROF = D.profile, C = D.configs;
  var tStart = F[0][T], tEnd = F[F.length - 1][T];
  var startMs = Date.parse(D.start);
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var idx = {};
  C.forEach(function (c, i) { idx[c.id] = i; });

  // the page's language (tools/build_site.py): translated messages and numbers
  var LANG = window.HOWFAR_LANG || "en";
  var _t = window._t || function (s, v) { return v ? s.replace(/\{(\w+)\}/g, function (m, k) { return k in v ? v[k] : m; }) : s; };

  // the watch shows HowFar with the course profile; the error chart shows every line
  var state = { t: tStart + 2.17 * 3600, main: "profile", target: "main", speed: 300, playing: false, last: 0 };
  var $ = function (id) { return document.getElementById(id); };
  var SVGNS = "http://www.w3.org/2000/svg";

  // ---------- formatting
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function dur(s) {
    s = Math.max(0, Math.round(s));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(x) : m + ":" + pad(x);
  }
  // the countdown as the watch shows it (WpUtil.etaText): h:mm in 30-minute steps from four hours
  // out, 15-minute steps from two and 5-minute steps from one, whole minutes from 5 minutes out,
  // m:ss in the last 5
  function etaStep(s) { return s >= 13500 ? 1800 : s >= 6750 ? 900 : s >= 3450 ? 300 : s >= 300 ? 60 : 1; }
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
    var stepMs = (etaStep(e) >= 300 ? etaStep(e) / 60 : 1) * 60000;
    return clockFmt.format(new Date(Math.round((startMs + (raceSec + e) * 1000) / stepMs) * stepMs));
  }
  // time to go under the countdown, as the watch shows it (WpUtil.etaHm)
  function etaHm(s) {
    s = Math.max(0, Math.round(s));
    var step = Math.max(60, etaStep(s)), r = Math.round(s / step) * step;
    return Math.floor(r / 3600) + ":" + pad(Math.floor((r % 3600) / 60));
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
  // the error, stops not counted: to the next main checkpoint, the one the big number counts down
  // to (the readout, and the chart by default), or to the next point, minor ones too (the chart's
  // "every point" switch: the grey "in" times on the watch)
  var EXTRA = ETA0 + C.length + 1;
  function err(f, id) { return eta(f, id) + f[EXTRA][idx[id]] - moving(f); }
  function errTo(f, id) { return state.target === "all" ? eta(f, id) - (f[ACT] - f[STOPA]) : err(f, id); }
  function target(f) { return state.target === "all" ? f[K] : mainFrom(f[K]); }
  function moving(f) {
    var m = mainFrom(f[K]);
    return m === f[K] ? f[ACT] - f[STOPA] : (WP[m].arrive - f[T]) - (WP[m].stops - f[STOPS]);
  }
  function cfg(id) { return C[idx[id]]; }
  // the cases' names, short (chart, table) and next to the choice
  var LABELS = {
    average: _t("Average pace so far"),
    none: _t("HowFar, no course profile"),
    profile: _t("HowFar with the course profile"),
    past: _t("HowFar with the profile and past races")
  };
  function label(id) { return LABELS[id] || cfg(id).label; }
  // the error chart's lines, back to front, and their colours
  var STEPS = ["average", "none", "past", "profile"];
  // HowFar with the profile is drawn once: as a first race or after past races, as the switch says
  function shownSteps() { return STEPS.filter(function (id) { return id !== (state.main === "past" ? "profile" : "past"); }); }
  var COLORS = { average: "var(--line-average)", none: "var(--line-none)", profile: "var(--line-profile)", past: "var(--line-past)" };
  // the results table's rows, top to bottom
  var ROWS = ["average", "none", "profile", "past"];
  var DASHED = { none: true };  // yellow and green are close for some colour-blind readers
  function swatch(id) {
    return '<i style="background:' + (DASHED[id] ? "repeating-linear-gradient(90deg, " + COLORS[id] + " 0 5px, transparent 5px 8px)" : COLORS[id]) + '"></i>';
  }

  function frameAt(t) {
    var lo = 0, hi = F.length - 1;
    while (lo < hi) {
      var mid = (lo + hi + 1) >> 1;
      if (F[mid][T] <= t) lo = mid; else hi = mid - 1;
    }
    return F[lo];
  }

  // ---------- main and minor points: the big number counts down to the next main checkpoint;
  // the watch, a field of its own, also lists the minor ones on the way and the main ones after
  var LEGS = ETA0 + C.length;
  // the same watch after five past races: [its LEGS, distance ratio, speeds flat/up/down, fatigue]
  var PAST = ETA0 + C.length + 2;
  function legs(f) { return state.main === "past" ? f[PAST][0] : f[LEGS]; }
  // what the watch has learned so far: distance ratio, speeds on the flat, up and down 20%, fatigue
  function learned(f) { return state.main === "past" ? f[PAST].slice(1) : [f[SCALE], f[FLAT], f[UP], f[DOWN], f[FAT]]; }
  // HowFar's time from now to checkpoint j (the next one, k, or a later one), unrounded
  function timeTo(f, j) {
    var e = eta(f, state.main);
    return j === f[K] ? e : e + legs(f)[j - f[K] - 1];
  }
  function mainFrom(j) { while (j < WP.length - 1 && WP[j].minor) j++; return j; }
  function points(f) {
    var m = mainFrom(f[K]);
    var vias = [];
    for (var j = f[K]; j < m; j++) if (WP[j].minor) vias.push(j);
    var via = vias.length ? vias[0] : null;
    var then = m < WP.length - 1 ? mainFrom(m + 1) : null;
    var then2 = then != null && then < WP.length - 1 ? mainFrom(then + 1) : null;
    return { main: m, via: via, vias: vias, then: then, then2: then2 };
  }

  // the dot before each time on the watch: green under 45 minutes to go, yellow to 2 hours,
  // red beyond (WpUtil.reliability)
  function dotClass(s) { return s < 2700 ? "g" : s < 7200 ? "y" : "r"; }
  // line: [name part, time part, seconds for the dot]; like the watch, a long name is shortened
  // and the time always shows
  function setLine(node, line) {
    node.replaceChildren();
    if (!line) return;
    if (line[2] != null) {
      var d = document.createElement("span");
      d.className = "dot " + dotClass(line[2]);
      node.appendChild(d);
    }
    var nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = line[0];
    node.appendChild(nm);
    if (line[1]) {
      var tl = document.createElement("span");
      tl.className = "tl";
      tl.textContent = line[1];
      node.appendChild(tl);
    }
  }

  // ---------- watch + readout
  function render() {
    var f = frameAt(state.t);
    var pts = points(f);
    var wp = WP[pts.main];
    var e = shownSec(timeTo(f, pts.main));
    var marker = cfg(state.main).ahead ? "P " : "~ ";

    $("wLabel").textContent = marker + wp.name;
    var shown = etaText(e), learning = f[CD] < 4000; // the watch greys the time for its first ~4 km
    $("wTime").innerHTML = '<span class="dot ' + dotClass(e) + '"></span>' + shown[0] + '<span class="w-side"><span class="w-unit">' + shown[1] + '</span><span class="w-arr">@' + arrival(f[T], e) + "</span></span>";
    $("wTime").classList.toggle("learning", learning);
    // a field of its own, top to bottom in the order you meet them: the minor points on the way
    // (grey, their time from now), the main checkpoint, then the next main ones with their leg's
    // moving time from leaving the checkpoint before (+h:mm: stops there can't be known)
    // two of these small lines fit on this screen (as on a 280-pixel watch): minor points first,
    // the last one shown counting the others, then "then" lines; "(learning)" in a free one
    var leg = function (j, from) { var s = timeTo(f, j) - timeTo(f, from); return [_t("then") + " " + WP[j].name, "+" + etaHm(s), s]; };
    var nm = Math.min(2, pts.vias.length);
    [0, 1].forEach(function (i) {
      var j = pts.vias[i];
      var more = i === nm - 1 && pts.vias.length > nm ? " (+" + (pts.vias.length - nm) + ")" : "";
      setLine($("wMinor" + (i + 1)), i < nm ? [WP[j].name, _t("in") + " " + etaHm(timeTo(f, j)) + more, timeTo(f, j)] : null);
    });
    var thens = [];
    if (pts.then != null) thens.push(leg(pts.then, pts.main));
    if (pts.then2 != null) thens.push(leg(pts.then2, pts.then));
    thens = thens.slice(0, 2 - nm);
    if (learning && nm + thens.length < 2) thens.push([_t("(learning)"), "", null]);
    [0, 1].forEach(function (i) {
      setLine($("wThen" + (i + 1)), thens[i] || null);
      $("wThen" + (i + 1)).classList.toggle("note", !!thens[i] && thens[i][2] == null);
    });

    $("raceClock").textContent = dur(f[T]);
    $("rTime").innerHTML = _t("<b>{time}</b> · {clock} local time", { time: hm(f[T]), clock: clock(f[T]) }) +
      (f[STOPNOW] ? ' <span class="chip quiet">' + _t("Standing still") + "</span>" : "");
    $("rPos").innerHTML = _t("<b>{done}</b> of {total} · {alt} m", { done: km(f[CD]), total: km(WP[WP.length - 1].d), alt: num(f[ALT]) });
    var climb = wp.alt - f[ALT];
    var ahead = wp.d - f[CD];
    $("rNext").innerHTML = "<b>" + wp.name + "</b> · " + (climb >= 0
      ? _t("{dist} ahead, {m} m higher", { dist: km(ahead), m: num(climb) })
      : _t("{dist} ahead, {m} m lower", { dist: km(ahead), m: num(-climb) }));
    $("rSays").innerHTML = _t("<b>{time}</b>, arriving at {clock}", { time: shown[0] + " " + shown[1], clock: arrival(f[T], e) });
    // what it really took to the main checkpoint, and the stops on the way
    var took = pts.main === f[K] ? f[ACT] : wp.arrive - f[T];
    var stopped = pts.main === f[K] ? f[STOPA] : wp.stops - f[STOPS];
    $("rActual").innerHTML = (stopped >= 60
      ? _t("<b>{time}</b>, arrived at {clock}, including {stop} min stopped", { time: dur(took), clock: clock(f[T] + took), stop: Math.round(stopped / 60) })
      : _t("<b>{time}</b>, arrived at {clock}", { time: dur(took), clock: clock(f[T] + took) }));
    var x = err(f, state.main);
    var ok = Math.abs(x) <= 300;
    $("rErr").innerHTML = _t("To {name}: <b>{err}</b> (not counting stops)", { name: WP[pts.main].name, err: signedMin(x) }) + " " +
      (ok ? '<span class="chip good">✓ ' + _t("Within 5 min") + "</span>"
          : '<span class="chip warn">! ' + (x < 0 ? _t("You got there later") : _t("You got there sooner")) + "</span>") +
      (WP[f[K]].minor ? '<br><span class="small muted">' + _t("To {name}: {err}", { name: WP[f[K]].name, err: signedMin(eta(f, state.main) - (f[ACT] - f[STOPA])) }) + "</span>" : "");

    var lr = learned(f), sc = lr[0], fa = lr[4];
    var pct = function (r) { return Math.round(Math.abs(r - 1) * 100) + "%"; };
    $("lScale").innerHTML = sc >= 1
      ? _t("<b>Distance:</b> your watch measures <b>{pct} more</b> than the course map (switchbacks, GPS wobble), so it adjusts the distance left.", { pct: pct(sc) })
      : _t("<b>Distance:</b> your watch measures <b>{pct} less</b> than the course map (switchbacks, GPS wobble), so it adjusts the distance left.", { pct: pct(sc) });
    var perKm = function (v) { var p = Math.round(1000 / v); return Math.floor(p / 60) + ":" + pad(p % 60); };
    // up a 20% slope: metres climbed an hour, the rate HowFar learns for every steep climb
    $("lForm").innerHTML = _t("{flat}/km on the flat, {vam} m of climbing an hour up a 20% slope, {down}/km down one.",
      { flat: perKm(lr[1]), vam: num(Math.round(lr[2] * 0.2 * 360) * 10), down: perKm(lr[3]) });
    $("lFatigue").innerHTML = Math.abs(fa - 1) < 0.01 ? _t("On the pace it expected.")
      : fa > 1 ? _t("<b>{pct} faster</b> than it expected.", { pct: pct(fa) })
      : _t("<b>{pct} slower</b> than it expected.", { pct: pct(fa) });

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
  // axis titles: x centred under the plot, y turned along the left edge
  function axisLabels(svg, M, xLabel, yLabel) {
    txt(svg, M.l + (M.W - M.l - M.r) / 2, M.H - 6, xLabel, { "text-anchor": "middle", fill: "var(--ink-2)" });
    var y = M.t + (M.H - M.t - M.b) / 2;
    txt(svg, 16, y, yLabel, { "text-anchor": "middle", fill: "var(--ink-2)", transform: "rotate(-90 16 " + y + ")" });
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
  var E = { W: 1000, H: 318, l: 72, r: 18, t: 74, b: 48 };
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
      txt(svg, ex(k * 1000), E.H - 28, String(k), { "text-anchor": "middle" });
    }
    axisLabels(svg, E, _t("Distance (km)"), _t("Altitude (m)"));
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
      // main checkpoints filled and in bold, the minor points on the way hollow and grey
      el("circle", w.minor ? { cx: x, cy: y, r: 3.5, fill: "var(--surface)", stroke: "var(--ink-3)", "stroke-width": 1.5 }
                           : { cx: x, cy: y, r: 5, fill: "var(--ink)", stroke: "var(--surface)", "stroke-width": 1.5 }, svg);
      var anchor = x > E.W - 90 ? "end" : x < E.l + 60 ? "start" : "middle";
      txt(svg, x, row ? 42 : 20, w.name.replace("BaseVita-", "Base vita "), w.minor
        ? { "text-anchor": anchor, fill: "var(--ink-3)" } : { "text-anchor": anchor, fill: "var(--ink)", "font-weight": 600 });
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
  // the same distance axis as the elevation chart, so the two line up point for point
  var R = { W: 1000, H: 340, l: E.l, r: E.r, t: 14, b: 50, y0: -30, y1: 30 };  // about 4.6 px a minute: 8 min off is clearly out of the 5 min band
  function rx(d) { return ex(d); }
  function frameAtDist(d) {
    for (var i = 0; i < F.length; i++) if (F[i][CD] >= d) return F[i];
    return F[F.length - 1];
  }
  function ry(m) { m = Math.max(R.y0, Math.min(R.y1, m)); return R.t + ((R.y1 - m) / (R.y1 - R.y0)) * (R.H - R.t - R.b); }
  var errCursor, errDot, errVal;

  function seriesPoints(id) {
    return F.map(function (f) { return rx(f[CD]).toFixed(1) + "," + ry(errTo(f, id) / 60).toFixed(1); }).join(" ");
  }
  // the lines and the checkpoints they count down to, redrawn when the switch changes
  var errSeries;
  function drawSeries() {
    while (errSeries.firstChild) errSeries.removeChild(errSeries.firstChild);
    WP.forEach(function (w, i) {
      if (i < D.firstWaypoint || w.arrive == null || (w.minor && state.target === "main")) return;
      el("line", { x1: rx(w.d), x2: rx(w.d), y1: R.t, y2: R.H - R.b, stroke: "var(--line)", "stroke-width": 1, "stroke-dasharray": w.minor ? "1 4" : "2 4" }, errSeries);
    });
    shownSteps().forEach(function (id) {
      var attrs = { points: seriesPoints(id), fill: "none", stroke: COLORS[id], "stroke-width": id === state.main ? 2 : 1.5, "stroke-linejoin": "round" };
      if (DASHED[id]) attrs["stroke-dasharray"] = "6 4";
      el("polyline", attrs, errSeries);
    });
  }
  function drawLegend() {
    $("errLegend").innerHTML = shownSteps().reverse().map(function (id) {
      return "<span>" + swatch(id) + label(id) + "</span>";
    }).join("");
  }
  function drawError() {
    var svg = $("err");
    el("rect", { x: R.l, y: ry(5), width: R.W - R.l - R.r, height: ry(-5) - ry(5), fill: "var(--band)" }, svg);
    [-30, -15, -5, 0, 5, 15, 30].forEach(function (m) {
      el("line", { x1: R.l, x2: R.W - R.r, y1: ry(m), y2: ry(m), stroke: m === 0 ? "var(--ink-3)" : "var(--line-soft)", "stroke-width": 1 }, svg);
      txt(svg, R.l - 8, ry(m) + 4, (m > 0 ? "+" : m < 0 ? "−" : "") + Math.abs(m), { "text-anchor": "end" });
    });
    // which side of zero means what, before the first checkpoint where there is no line yet
    txt(svg, R.l + 8, ry(0) - 6, _t("earlier"), { fill: "var(--ink-2)" });
    txt(svg, R.l + 8, ry(0) + 15, _t("later"), { fill: "var(--ink-2)" });
    for (var k = 0; k <= maxD / 1000; k += 5) {
      txt(svg, rx(k * 1000), R.H - 30, String(k), { "text-anchor": "middle" });
    }
    axisLabels(svg, R, _t("Distance (km)"), _t("Minutes off"));
    errSeries = el("g", {}, svg);
    drawSeries();
    drawLegend();
    errCursor = el("line", { y1: R.t, y2: R.H - R.b, stroke: "var(--ink)", "stroke-width": 1.25 }, svg);
    // where you are on the main line, with its number: the readout's "HowFar was off by" (or, for
    // every point, its "To ..." line when the next point is a minor one)
    errDot = el("circle", { r: 4, fill: COLORS[state.main], stroke: "var(--surface)", "stroke-width": 2 }, svg);
    errVal = txt(svg, 0, 0, "", { "font-weight": 600, fill: "var(--ink)", stroke: "var(--surface)", "stroke-width": 4, "paint-order": "stroke" });

    var box = $("errBox");
    svg.addEventListener("mousemove", function (evt) {
      var p = svgPoint(svg, evt);
      var f = frameAtDist(((p.x - R.l) / (R.W - R.l - R.r)) * maxD);
      tipShow(box, "<b>" + km(f[CD]) + "</b> · " + _t("<b>{time}</b> · to {name}", { time: hm(f[T]), name: WP[target(f)].name }) +
        shownSteps().reverse().map(function (id) {
          return "<br>" + swatch(id) + label(id) + " " + signedMin(errTo(f, id));
        }).join(""), p.px, p.py);
    });
    svg.addEventListener("mouseleave", function () { tipHide(box); });
    svg.addEventListener("click", function (evt) {
      var p = svgPoint(svg, evt);
      state.t = frameAtDist(((p.x - R.l) / (R.W - R.l - R.r)) * maxD)[T];
      render();
    });
  }

  function moveCursors(f) {
    var x = ex(f[CD]);
    elevCursor.setAttribute("x1", x); elevCursor.setAttribute("x2", x);
    elevDot.setAttribute("cx", x); elevDot.setAttribute("cy", ey(f[ALT]));
    elevDone.setAttribute("width", Math.max(0, x - E.l));
    var xn = ex(WP[mainFrom(f[K])].d);  // to the checkpoint the big number counts down to
    elevAhead.setAttribute("x", x); elevAhead.setAttribute("width", Math.max(0, xn - x));
    var xt = rx(f[CD]);
    errCursor.setAttribute("x1", xt); errCursor.setAttribute("x2", xt);
    var m = errTo(f, state.main) / 60, yd = ry(m);
    errDot.setAttribute("cx", xt); errDot.setAttribute("cy", yd);
    var right = xt < R.W - R.r - 90;
    errVal.textContent = signedMin(m * 60);
    errVal.setAttribute("x", right ? xt + 9 : xt - 9);
    errVal.setAttribute("y", yd < R.t + 16 ? yd + 18 : yd - 9);
    errVal.setAttribute("text-anchor", right ? "start" : "end");
  }

  // ---------- results table
  var SHORT = { TOR: "Tor 330", AW: "Abbots Way", X100: "TORX100", S1: "TORX S1", AN: "La Via di Annibale", STL: "STL25" };
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
      '<th scope="col" class="num" title="' + _t("Average of the races") + '">' + _t("Average") + "</th>" +
      '<th scope="col" class="num" title="' + _t("Out of every 100 times HowFar showed a time, how many were less than 5 minutes off") + '">' + _t("Less than 5 min off") + "</th>" +
      '<th scope="col" class="num" title="' + _t("Out of every 100 times HowFar showed a time, how many were less than 15 minutes off") + '">' + _t("Less than 15 min off") + "</th>" +
      '<th scope="col" class="num" title="' + _t("How far off HowFar was 2 km before each checkpoint") + '">' + _t("Off by, 2 km before") + "</th>";
    var body = table.querySelector("tbody");
    ROWS.forEach(function (id) {
      var v = mean(id, "mae_hour");
      var row = document.createElement("tr");
      if (id === "profile") row.className = "current";
      if (id === "average") row.className = "baseline";
      row.innerHTML = "<td>" + label(id) + "</td>" +
        RACES.map(function (r) { return '<td class="num">' + dec(S[id][r.key].mae_hour, 1) + " min</td>"; }).join("") +
        '<td class="num"><b>' + dec(v, 1) + " min</b></td>" +
        '<td class="num">' + Math.round(mean(id, "within5_hour") * 100) + "%</td>" +
        '<td class="num">' + Math.round(mean(id, "within15_hour") * 100) + "%</td>" +
        '<td class="num">' + dec(mean(id, "mae_2000"), 1) + " min</td>";
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
      var chips = ["<span>" + parts[0] + "</span>", "<span>" + _t("{dist} from the previous checkpoint", { dist: km(+parts[1]) }) + "</span>"];
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
  document.querySelectorAll("[data-main]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.main = b.getAttribute("data-main");
      document.querySelectorAll("[data-main]").forEach(function (o) { o.setAttribute("aria-pressed", o === b); });
      errDot.setAttribute("fill", COLORS[state.main]);
      drawSeries();
      drawLegend();
      render();
    });
  });
  document.querySelectorAll("[data-target]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.target = b.getAttribute("data-target");
      document.querySelectorAll("[data-target]").forEach(function (o) { o.setAttribute("aria-pressed", o === b); });
      drawSeries();
      render();
    });
  });
  $("scrub").addEventListener("input", function () {
    state.t = tStart + (+$("scrub").value / 1000) * (tEnd - tStart);
    render();
  });

  drawElevation();
  drawError();
  // on a narrow screen both charts scroll sideways: keep them scrolled together, km over km
  (function () {
    var boxes = [$("elevBox"), $("errBox")], busy = false;
    boxes.forEach(function (box, i) {
      box.addEventListener("scroll", function () {
        if (busy) return;
        busy = true;
        boxes[1 - i].scrollLeft = box.scrollLeft;
        requestAnimationFrame(function () { busy = false; });
      }, { passive: true });
    });
  })();
  buildTable();
  fillTools();
  render();
  if (!reduceMotion) setPlaying(true);
})();
