// Sped-up replay of a recorded run through each step of the HowFar? prediction
// (all predictions precomputed in demo/torx-s1.js by tools/research/demo_export.py).
(function () {
  "use strict";
  var D = window.HOWFAR_DEMO;
  if (!D) return;

  // frame columns
  var T = 0, CD = 1, ALT = 2, K = 3, DN = 4, ACT = 5, STOPA = 6, STOPNOW = 7, SCALE = 8, FORM = 9, FAT = 10, ETA0 = 11;
  var F = D.frames, WP = D.waypoints, PROF = D.profile, C = D.configs;
  var tStart = F[0][T], tEnd = F[F.length - 1][T];
  var startMs = Date.parse(D.start);
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var idx = {};
  C.forEach(function (c, i) { idx[c.id] = i; });

  var NOTES = {
    cur: "The watch only uses what it has seen of you so far today, and only knows how far and how much higher the checkpoint is (~).",
    past: "Also starts from your pace on every slope in your past races (here: the other three races in the test).",
    ahead: "Also knows every climb and descent to the checkpoint, from the course profile (P).",
    raceday: "Everything: also notices how your day is going compared with past races, whether you've slowed down lately, and the extra distance your watch measures. This is what HowFar? does on your watch."
  };

  var state = { t: tStart + 2.17 * 3600, main: "raceday", cmp: "cur", speed: 300, playing: false, last: 0 };
  var $ = function (id) { return document.getElementById(id); };
  var SVGNS = "http://www.w3.org/2000/svg";

  // ---------- formatting
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function dur(s) {
    s = Math.max(0, Math.round(s));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(x) : m + ":" + pad(x);
  }
  function hm(s) {
    s = Math.max(0, Math.round(s));
    return Math.floor(s / 3600) + " h " + pad(Math.floor((s % 3600) / 60)) + " min";
  }
  var clockFmt;
  try { clockFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" }); }
  catch (e) { clockFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }); }
  function clock(raceSec) { return clockFmt.format(new Date(startMs + raceSec * 1000)); }
  function km(m) { return (m / 1000).toFixed(1) + " km"; }
  function num(n) { return Math.round(n).toLocaleString("en-US"); }
  function signedMin(s) {
    var m = s / 60;
    return (m >= 0 ? "+" : "−") + Math.abs(m).toFixed(1) + " min";
  }
  function eta(f, id) { return f[ETA0 + idx[id]]; }
  function err(f, id) { return eta(f, id) - (f[ACT] - f[STOPA]); }
  function cfg(id) { return C[idx[id]]; }

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
    var e = eta(f, state.main);
    var marker = cfg(state.main).ahead ? "P " : "~ ";

    $("wLabel").textContent = marker + wp.name;
    $("wTime").textContent = dur(e);
    $("wArrive").textContent = "@ " + clock(f[T] + e);

    $("raceClock").textContent = dur(f[T]);
    $("rTime").innerHTML = "<b>" + hm(f[T]) + "</b> · " + clock(f[T]) + " local time" +
      (f[STOPNOW] ? ' <span class="chip quiet">Standing still</span>' : "");
    $("rPos").innerHTML = "<b>" + km(f[CD]) + "</b> of " + km(WP[WP.length - 1].d) + " · " + num(f[ALT]) + " m";
    var climb = wp.alt - f[ALT];
    $("rNext").innerHTML = "<b>" + wp.name + "</b> · " + km(f[DN]) + " ahead, " +
      (climb >= 0 ? num(climb) + " m higher" : num(-climb) + " m lower");
    $("rSays").innerHTML = "<b>" + dur(e) + "</b>, arriving at " + clock(f[T] + e);
    $("rActual").innerHTML = "<b>" + dur(f[ACT]) + "</b>, arrived at " + clock(f[T] + f[ACT]) +
      (f[STOPA] >= 60 ? ", including " + Math.round(f[STOPA] / 60) + " min stopped" : "");
    var x = err(f, state.main);
    var ok = Math.abs(x) <= 300;
    $("rErr").innerHTML = "<b>" + signedMin(x) + "</b> (not counting stops) " +
      (ok ? '<span class="chip good">✓ Within 5 min</span>'
          : '<span class="chip warn">! ' + (x < 0 ? "You got there later" : "You got there sooner") + "</span>");

    var sc = f[SCALE], fo = f[FORM], fa = f[FAT];
    var pct = function (r) { return Math.round(Math.abs(r - 1) * 100) + "%"; };
    $("lScale").innerHTML = "<b>Distance:</b> your watch measures " + (sc >= 1 ? "<b>" + pct(sc) + " more</b>" : "<b>" + pct(sc) + " less</b>") +
      " than the course map (switchbacks, GPS wobble), so it adjusts the distance left.";
    $("lForm").innerHTML = "<b>Today vs. past races:</b> " + (Math.abs(fo - 1) < 0.01 ? "about the same as usual."
      : "<b>" + pct(fo) + (fo > 1 ? " faster" : " slower") + "</b> than usual.");
    $("lFatigue").innerHTML = "<b>Last couple of km:</b> " + (Math.abs(fa - 1) < 0.01 ? "on the pace it expected."
      : "<b>" + pct(fa) + (fa > 1 ? " faster" : " slower") + "</b> than it expected.");

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
      tipShow(box, "<b>" + hm(f[T]) + "</b> · to " + WP[f[K]].name +
        '<br><i style="background:var(--series-p)"></i>' + cfg(state.main).label + " " + signedMin(err(f, state.main)) +
        '<br><i style="background:var(--series-a)"></i>' + cfg(state.cmp).label + " " + signedMin(err(f, state.cmp)), p.px, p.py);
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
    $("legMain").textContent = cfg(state.main).label;
    $("legCmp").textContent = cfg(state.cmp).label;
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
  var STEPS = ["cur", "past", "ahead", "raceday"];
  function fillPicker(sel, value) {
    STEPS.forEach(function (id) {
      var o = document.createElement("option");
      o.value = id; o.textContent = cfg(id).label;
      sel.appendChild(o);
    });
    sel.value = value;
  }
  function setMain(id) { state.main = id; $("pickMain").value = id; updateSeries(); render(); }

  var SHORT = { S1: "TORX S1", S2: "TORX S2", AN: "Annibale", STL: "STL25" };
  function buildTable() {
    var table = $("results");
    var RACES = D.races, S = D.scores;
    var mean = function (id, m) {
      var t = 0;
      RACES.forEach(function (r) { t += S[id][r.key][m]; });
      return t / RACES.length;
    };
    var head = table.querySelector("thead tr");
    head.innerHTML = '<th scope="col">What the watch knows</th>' +
      RACES.map(function (r) { return '<th scope="col" class="num" title="' + r.name + ': average minutes off">' + (SHORT[r.key] || r.name) + "</th>"; }).join("") +
      '<th scope="col" class="num" title="Average of the four races">Average</th><th scope="col" class="bar-col"><span class="sr-only">Average, as a bar</span></th>' +
      '<th scope="col" class="num" title="Out of every 100 times the watch showed a time, how many were less than 5 minutes off">Less than 5 min off</th>' +
      '<th scope="col" class="num" title="How far off the watch was when you were 2 km from each checkpoint">Off by, 2 km before</th>';
    var max = 0, best = STEPS[0];
    STEPS.forEach(function (id) {
      max = Math.max(max, mean(id, "mae_hour"));
      if (mean(id, "mae_hour") < mean(best, "mae_hour")) best = id;
    });
    var body = table.querySelector("tbody");
    STEPS.forEach(function (id) {
      var v = mean(id, "mae_hour");
      var row = document.createElement("tr");
      if (id === "raceday") row.className = "current";
      row.tabIndex = 0;
      row.title = "Show on the watch";
      row.innerHTML = "<td>" + cfg(id).label + "</td>" +
        RACES.map(function (r) { return '<td class="num">' + S[id][r.key].mae_hour.toFixed(1) + " min</td>"; }).join("") +
        '<td class="num"><b>' + v.toFixed(1) + " min</b></td>" +
        '<td><div class="bar' + (id === best ? " best" : "") + '" style="width:' + (v / max * 100).toFixed(1) + '%"></div></td>' +
        '<td class="num">' + Math.round(mean(id, "within5_hour") * 100) + "%</td>" +
        '<td class="num">' + mean(id, "mae_2000").toFixed(1) + " min</td>";
      var pick = function () { setMain(id); $("demo").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" }); };
      row.addEventListener("click", pick);
      row.addEventListener("keydown", function (e) { if (e.key === "Enter") pick(); });
      body.appendChild(row);
    });
  }

  // ---------- speed-by-grade chart (tools section)
  function drawModel() {
    var svg = $("model");
    var M = { W: 640, H: 300, l: 44, r: 70, t: 14, b: 34 };
    var mx = function (g) { return M.l + ((g + 40) / 80) * (M.W - M.l - M.r); };
    var my = function (v) { return M.t + ((2.4 - v) / 2.4) * (M.H - M.t - M.b); };
    [0, 0.6, 1.2, 1.8, 2.4].forEach(function (v) {
      el("line", { x1: M.l, x2: M.W - M.r, y1: my(v), y2: my(v), stroke: "var(--line-soft)" }, svg);
      txt(svg, M.l - 6, my(v) + 4, v.toFixed(1), { "text-anchor": "end" });
    });
    [-40, -20, 0, 20, 40].forEach(function (g) { txt(svg, mx(g), M.H - 12, (g > 0 ? "+" : "") + g + "%", { "text-anchor": "middle" }); });
    txt(svg, M.l + 4, M.t + 8, "m/s", { "text-anchor": "start" });
    var series = [[1, 2, "var(--series-s1)", "Section 1"], [3, 4, "var(--series-s2)", "Section 2"]];
    var labels = [];
    series.forEach(function (s) {
      var pts = [], last = null;
      D.model.forEach(function (b) { if (b[s[1]] >= 3) { pts.push(mx(b[0]).toFixed(1) + "," + my(b[s[0]]).toFixed(1)); last = b; } });
      el("polyline", { points: pts.join(" "), fill: "none", stroke: s[2], "stroke-width": 2, "stroke-linejoin": "round" }, svg);
      if (last) labels.push({ y: my(last[s[0]]) + 4, s: s[3] });
    });
    labels.sort(function (a, b) { return a.y - b.y; });
    for (var i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 15);
    labels.forEach(function (l) { txt(svg, M.W - M.r + 6, l.y, l.s, { fill: "var(--ink-2)" }); });

    var cross = el("line", { y1: M.t, y2: M.H - M.b, stroke: "var(--ink-3)", "stroke-width": 1, visibility: "hidden" }, svg);
    var box = $("modelBox");
    svg.addEventListener("mousemove", function (evt) {
      var p = svgPoint(svg, evt);
      var g = Math.round(((p.x - M.l) / (M.W - M.l - M.r)) * 80 - 40);
      var b = D.model[Math.max(0, Math.min(40, Math.round((g + 40) / 2)))];
      cross.setAttribute("x1", mx(b[0])); cross.setAttribute("x2", mx(b[0])); cross.setAttribute("visibility", "visible");
      function line(i, w, color, label) {
        if (b[w] < 3) return '<br><i style="background:' + color + '"></i>' + label + ": too few samples";
        var pace = 1000 / b[i];
        return '<br><i style="background:' + color + '"></i>' + label + ": " + b[i].toFixed(2) + " m/s · " +
          Math.floor(pace / 60) + ":" + pad(Math.round(pace % 60)) + "/km";
      }
      tipShow(box, "<b>" + (b[0] > 0 ? "+" : "") + b[0] + "% grade</b>" + line(1, 2, "var(--series-s1)", "Section 1") + line(3, 4, "var(--series-s2)", "Section 2"), p.px, p.py);
    });
    svg.addEventListener("mouseleave", function () { tipHide(box); cross.setAttribute("visibility", "hidden"); });
  }

  function fillTools() {
    $("modelString").textContent = D.modelString;
    $("profileString").textContent = D.profileString;
    $("profileMeta").textContent = "T1 course profile, one value per " + D.profileStep + " m · " + num(D.profileString.length) + " characters";
    var entry = D.profileString.split(";").filter(function (e) { return e.indexOf("Col d'Arp|") === 0; })[0];
    if (entry) {
      var parts = entry.split("|"), grades = parts[2].split(",").slice(0, 6);
      $("decodeTitle").innerHTML = "How to read one entry: <code>" + parts[0] + "|" + parts[1] + "|" + grades.join(",") + ",…</code>";
      var chips = ["<span>" + parts[0] + "</span>", "<span>" + km(+parts[1]) + " from the previous waypoint</span>"];
      grades.forEach(function (g) { chips.push("<span>" + D.profileStep + " m at " + (g >= 0 ? "+" : "") + (g / 10).toFixed(1) + "%</span>"); });
      chips.push("<span>…</span>");
      $("decode").innerHTML = chips.join("");
    }
    document.querySelectorAll("[data-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var pre = $(b.getAttribute("data-copy"));
        var done = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500); };
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
    $("play").textContent = on ? "❚❚ Pause" : "▶ Play";
    $("play").setAttribute("aria-label", on ? "Pause" : "Play");
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
  fillPicker($("pickMain"), state.main);
  fillPicker($("pickCmp"), state.cmp);
  $("pickMain").addEventListener("change", function () { setMain(this.value); });
  $("pickCmp").addEventListener("change", function () { state.cmp = this.value; updateSeries(); render(); });

  drawElevation();
  drawError();
  updateSeries();
  buildTable();
  drawModel();
  fillTools();
  render();
  if (!reduceMotion) setPlaying(true);
})();
