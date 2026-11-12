/* LED watch simulator: three.js board view + glue to the firmware compiled to WebAssembly.
 * The firmware logic (and every firmware number shown) comes from watch.wasm; geometry comes from
 * board-geometry.json (generated from the PCB). This file only draws and relays inputs. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var qa = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

  // ---------------------------------------------------------------- simulation (wasm)
  // Order of sim_const(id): must match projects/watch-sim/wasm/sim.c.
  var CONST_NAMES = ["UI_SHOW_MS", "UI_SET_HOLD_MS", "UI_SET_IDLE_MS", "UI_FIRST_SET_MS", "UI_AFTER_SET_MS",
    "UI_LOWBAT_MS", "VBAT_EMPTY_MV", "VBAT_FRESH_MV", "FRAME_TICKS", "LED_COUNT", "LED_LINES", "TICK_HZ", "UI_STEP_MS",
    "UI_SLEEP", "UI_SHOW", "UI_SET", "UI_LOWBAT", "DISPLAY_OFF", "DISPLAY_TIME", "DISPLAY_LOWBAT", "LED_MINUTE_FIRST", "LED_HOUR_FIRST", "LED_NONE"];
  // Names for the enum values; the numeric values themselves come from the firmware (sim_const).
  function stateName(c, v) { return v === c.UI_SLEEP ? "Idle, about to sleep" : v === c.UI_SHOW ? "Showing the time" : v === c.UI_SET ? "Setting the time (hands blink)" : v === c.UI_LOWBAT ? "Low battery" : "?"; }
  function dispName(c, v) { return v === c.DISPLAY_OFF ? "Nothing (LEDs off)" : v === c.DISPLAY_TIME ? "Hour and minute hands" : v === c.DISPLAY_LOWBAT ? "Low-battery blink at 12" : "?"; }

  async function loadSim() {
    var res = await fetch("watch.wasm");
    if (!res.ok) throw new Error("watch.wasm: HTTP " + res.status);
    var mod = await WebAssembly.compile(await res.arrayBuffer());
    var imports = {};
    WebAssembly.Module.imports(mod).forEach(function (i) {
      if (i.kind !== "function") throw new Error("unsupported wasm import " + i.module + "." + i.name);
      (imports[i.module] = imports[i.module] || {})[i.name] = function () { return 0; };
    });
    var inst = await WebAssembly.instantiate(mod, imports);
    var x = inst.exports;
    if (x._initialize) x._initialize();
    var consts = {};
    CONST_NAMES.forEach(function (n, id) { consts[n] = x.sim_const(id); });
    x.sim_init();
    return { x: x, c: consts };
  }

  // ---------------------------------------------------------------- UI helpers
  function fmtS(ms) { return (ms / 1000).toFixed(ms % 1000 ? 1 : 0) + " s"; }
  function fmtMv(mv) { return (mv / 1000).toFixed(1) + " V"; }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function fillConsts(c) {
    qa(".c").forEach(function (e) {
      var v = c[e.getAttribute("data-c")], f = e.getAttribute("data-fmt");
      e.textContent = f === "s" ? fmtS(v) : f === "mv" ? fmtMv(v) : String(v);
    });
  }

  // ---------------------------------------------------------------- scene
  var COLORS = { amber: 0xffa800, red: 0xff2a1a };
  var stage = $("stage");
  var renderer, scene, camera, ledMeshes = [], glowSprites = [], pressables = [], target = new THREE.Vector3();
  var orbit = { theta: 0.55, phi: 0.85, dist: 70 }, goal = null; // spherical, y up

  function mm2v(x, y, z) { return new THREE.Vector3(x, z, -y); } // board (x right, y 12 o'clock) -> three (y up)

  function labelSprite(text, size) {
    var cv = document.createElement("canvas"); cv.width = cv.height = 128;
    var g = cv.getContext("2d");
    g.fillStyle = "rgba(0,0,0,0.0)"; g.fillRect(0, 0, 128, 128);
    g.fillStyle = "#e8eaee"; g.font = "bold 84px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(text, 64, 70);
    var t = new THREE.CanvasTexture(cv);
    var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false }));
    s.scale.set(size, size, 1);
    return s;
  }

  var glowTex;
  function makeGlowTexture() {
    var cv = document.createElement("canvas"); cv.width = cv.height = 64;
    var g = cv.getContext("2d"), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.25, "rgba(255,255,255,0.45)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(cv);
  }

  function box(w, h, d, color, opts) {
    var m = new THREE.Mesh(new THREE.BoxGeometry(w, d, h),
      new THREE.MeshStandardMaterial(Object.assign({ color: color, roughness: 0.6, metalness: 0.1 }, opts || {})));
    return m;
  }

  function buildScene(geo) {
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false }); }
    catch (e) { build2d(geo); return; }
    scene = new THREE.Scene();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x0b0d11, 1);
    stage.insertBefore(renderer.domElement, stage.firstChild);
    camera = new THREE.PerspectiveCamera(32, 1, 0.5, 500);
    camera.up.set(0, 0, -1);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x303844, 0.75));
    var sun = new THREE.DirectionalLight(0xffffff, 0.7); sun.position.set(30, 60, 20); scene.add(sun);
    var fill = new THREE.DirectionalLight(0xaabbff, 0.35); fill.position.set(-30, -60, -20); scene.add(fill);
    glowTex = makeGlowTexture();

    var R = geo.board.diameter / 2, T = geo.board.thickness, top = T / 2, bot = -T / 2;
    var disc = new THREE.Mesh(new THREE.CylinderGeometry(R, R, T, 96),
      new THREE.MeshStandardMaterial({ color: 0x14231d, roughness: 0.55, metalness: 0.05 }));
    scene.add(disc);
    var rim = new THREE.Mesh(new THREE.TorusGeometry(R, 0.06, 6, 96), new THREE.MeshStandardMaterial({ color: 0xb08d3c, roughness: 0.4, metalness: 0.8 }));
    rim.rotation.x = Math.PI / 2; rim.position.y = top + 0.001; scene.add(rim);
    var rim2 = rim.clone(); rim2.position.y = bot - 0.001; scene.add(rim2);

    // Part origin + rotation (CCW seen from the top, as in the PCB); the body box sits at its own offset.
    function place(mesh, p, h) {
      var side = p.side === "bottom" ? -1 : 1, g = new THREE.Group();
      mesh.position.set(p.offset_x || 0, side > 0 ? top + h / 2 : bot - h / 2, -(p.offset_y || 0));
      g.add(mesh);
      g.position.set(p.x, 0, -p.y);
      g.rotation.y = (p.rotation_deg || 0) * Math.PI / 180;
      scene.add(g);
      mesh.userData.group = g;
      return mesh;
    }
    function worldPos(m) { return m.getWorldPosition(new THREE.Vector3()); }

    // LEDs
    geo.leds.forEach(function (l) {
      var small = l.package === "0402", w = small ? 1.0 : 1.6, d = small ? 0.5 : 0.8, h = small ? 0.35 : 0.5;
      var col = COLORS[l.colour] || COLORS.amber;
      var m = box(w, d, h, 0x2a2018, { emissive: col, emissiveIntensity: 0, roughness: 0.4 });
      m.material.userData.color = col;
      place(m, l, h);
      var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: col, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
      sp.scale.set(small ? 3.0 : 4.2, small ? 3.0 : 4.2, 1);
      sp.position.copy(worldPos(m)).add(new THREE.Vector3(0, 0.35, 0));
      scene.add(sp);
      ledMeshes[l.index] = m; glowSprites[l.index] = sp;
    });

    // other parts
    var KIND = { mcu: 0x16181c, accel: 0x1c1e24, crystal: 0xc9ccd1, resistor: 0x1a1a1a, cap: 0x9a7b4f, fet: 0x1c1e24 };
    (geo.parts || []).forEach(function (p) {
      var h = p.height || 0.4, k = String(p.kind || "").split("_")[0].replace("capacitor", "cap").replace("accelerometer", "accel");
      place(box(p.w, p.h, h, KIND[k] || 0x555a63, { metalness: k === "crystal" ? 0.7 : 0.1 }), p, h);
    });
    (geo.pads || []).forEach(function (p) {
      var m = new THREE.Mesh(new THREE.CylinderGeometry(p.diameter / 2, p.diameter / 2, 0.05, 24), new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.9, roughness: 0.35 }));
      var side = p.side === "bottom" ? -1 : 1;
      m.position.copy(mm2v(p.x, p.y, side > 0 ? top + 0.025 : bot - 0.025)); scene.add(m);
    });

    // battery holder (bottom): holder ring + cell
    if (geo.battery) {
      var b = geo.battery, cellH = b.cell_height || 3.2, cd = b.cell_diameter || 20;
      var cell = new THREE.Mesh(new THREE.CylinderGeometry(cd / 2, cd / 2, cellH, 64), new THREE.MeshStandardMaterial({ color: 0xc8ccd2, metalness: 0.9, roughness: 0.35 }));
      cell.position.copy(mm2v(b.x, b.y, bot - cellH / 2 - 0.8)); scene.add(cell);
      var lab = labelSprite("CR2032", 5); lab.position.copy(cell.position).add(new THREE.Vector3(0, -cellH / 2 - 0.3, 0)); scene.add(lab);
      var clip = new THREE.Mesh(new THREE.TorusGeometry((b.holder_w || 23) / 2, 0.25, 8, 64), new THREE.MeshStandardMaterial({ color: 0xb8a060, metalness: 0.9, roughness: 0.4 }));
      clip.rotation.x = Math.PI / 2; clip.position.copy(cell.position); scene.add(clip);
    }

    // buttons (pressable)
    (geo.buttons || []).forEach(function (bt) {
      var h = bt.height || 1.2;
      var m = box(bt.w, bt.h, h, 0x23262d, { roughness: 0.4 });
      place(m, bt, h);
      m.userData.button = bt.name;
      pressables.push(m);
      var s = labelSprite(bt.name, 3.2);
      s.position.copy(worldPos(m)).add(new THREE.Vector3(0, (bt.side === "bottom" ? -1 : 1) * (h / 2 + 0.6), 0));
      scene.add(s);
    });

    // 12 o'clock mark on the top
    var tick = labelSprite("12", 3.4); tick.position.copy(mm2v(0, R - 1.1, top + 0.4)); scene.add(tick);
    onResize();
  }

  // ---- 2D top-view fallback when WebGL is unavailable ----
  var fb = null;
  function build2d(geo) {
    var cv = document.createElement("canvas"); stage.insertBefore(cv, stage.firstChild);
    fb = { cv: cv, g: cv.getContext("2d"), geo: geo, duty: [] };
    qa("[data-view]").forEach(function (b) { b.style.display = "none"; });
    stage.querySelector(".hint").textContent = "3D view needs WebGL, which is not available here: showing a flat top view. The simulation works the same.";
    onResize();
  }
  function draw2d() {
    var g = fb.g, cv = fb.cv, w = cv.width, h = cv.height, sc = Math.min(w, h) / (fb.geo.board.diameter + 4);
    g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = "#0b0d11"; g.fillRect(0, 0, w, h);
    g.translate(w / 2, h / 2); g.scale(sc, -sc);
    g.fillStyle = "#14231d"; g.beginPath(); g.arc(0, 0, fb.geo.board.diameter / 2, 0, 7); g.fill();
    g.strokeStyle = "#b08d3c"; g.lineWidth = 0.12; g.stroke();
    (fb.geo.parts || []).forEach(function (p) {
      g.save(); g.translate(p.x, p.y); g.rotate((p.rotation_deg || 0) * Math.PI / 180);
      g.fillStyle = p.side === "bottom" ? "#252a33" : "#3a3f4a"; g.fillRect((p.offset_x || 0) - p.w / 2, (p.offset_y || 0) - p.h / 2, p.w, p.h); g.restore();
    });
    fb.geo.leds.forEach(function (l) {
      var d = sim ? Math.min(1, sim.x.sim_led_duty(l.index) / sim.c.FRAME_TICKS * 2.6) : 0;
      var col = l.colour === "red" ? "255,42,26" : "255,168,0";
      if (d > 0) { var gr = g.createRadialGradient(l.x, l.y, 0, l.x, l.y, 2.2); gr.addColorStop(0, "rgba(" + col + "," + d + ")"); gr.addColorStop(1, "rgba(" + col + ",0)"); g.fillStyle = gr; g.beginPath(); g.arc(l.x, l.y, 2.2, 0, 7); g.fill(); }
      g.fillStyle = "rgb(" + col + ")"; g.globalAlpha = 0.25 + 0.75 * d; g.beginPath(); g.arc(l.x, l.y, l.package === "0402" ? 0.45 : 0.7, 0, 7); g.fill(); g.globalAlpha = 1;
    });
    (fb.geo.buttons || []).forEach(function (b) {
      var on = (b.name === "A" && input.a) || (b.name === "B" && input.b);
      g.fillStyle = on ? "#5b6ee0" : "#555d6b"; g.beginPath(); g.arc(b.x * 1.0, b.y * 1.0, 1.2, 0, 7); g.fill();
      g.save(); g.scale(1, -1); g.fillStyle = "#e8eaee"; g.font = "1.3px sans-serif"; g.textAlign = "center"; g.fillText(b.name + " (bottom)", b.x * 0.82, -b.y * 0.82 + 2.4); g.restore();
    });
  }

  function onResize() {
    if (fb) { var r = window.devicePixelRatio || 1; fb.cv.width = stage.clientWidth * r; fb.cv.height = stage.clientHeight * r; return; }
    var w = stage.clientWidth, h = stage.clientHeight;
    if (!renderer || !w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }

  function updateCamera() {
    var sp = Math.sin(orbit.phi), cp = Math.cos(orbit.phi);
    camera.position.set(target.x + orbit.dist * sp * Math.sin(orbit.theta), target.y + orbit.dist * cp, target.z + orbit.dist * sp * Math.cos(orbit.theta));
    camera.lookAt(target);
  }

  var VIEWS = { top: { theta: 0, phi: 0.001, dist: 66 }, bottom: { theta: 0, phi: Math.PI - 0.001, dist: 66 }, angle: { theta: 0.55, phi: 0.85, dist: 70 } };

  function setupOrbit() {
    var el = renderer.domElement, ptrs = {}, last = 0, moved = 0;
    function count() { return Object.keys(ptrs).length; }
    var ray = new THREE.Raycaster(), held = null;
    function pick(e) {
      var r = el.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
      var hit = ray.intersectObjects(pressables, false)[0];
      return hit ? hit.object.userData.button : null;
    }
    el.addEventListener("pointerdown", function (e) {
      el.setPointerCapture(e.pointerId);
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      moved = 0; goal = null;
      if (count() === 1) {
        var b = pick(e);
        if (b) { held = { id: e.pointerId, name: b }; pressInput(b, true); }
      }
      if (count() === 2) { var k = Object.keys(ptrs); last = Math.hypot(ptrs[k[0]].x - ptrs[k[1]].x, ptrs[k[0]].y - ptrs[k[1]].y); }
    });
    el.addEventListener("pointermove", function (e) {
      var p = ptrs[e.pointerId]; if (!p) return;
      var dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
      if (held && held.id === e.pointerId) return;
      moved += Math.abs(dx) + Math.abs(dy);
      if (count() === 1) {
        orbit.theta -= dx * 0.008;
        orbit.phi = Math.min(Math.PI - 0.001, Math.max(0.001, orbit.phi - dy * 0.008));
      } else if (count() === 2) {
        var k = Object.keys(ptrs), d = Math.hypot(ptrs[k[0]].x - ptrs[k[1]].x, ptrs[k[0]].y - ptrs[k[1]].y);
        if (last) orbit.dist = Math.min(160, Math.max(28, orbit.dist * last / d));
        last = d;
      }
    });
    function up(e) {
      if (held && held.id === e.pointerId) { pressInput(held.name, false); held = null; }
      delete ptrs[e.pointerId]; last = 0;
    }
    el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", function (e) {
      e.preventDefault();
      orbit.dist = Math.min(160, Math.max(28, orbit.dist * Math.exp(e.deltaY * 0.0012)));
    }, { passive: false });
    qa("[data-view]").forEach(function (b) {
      b.addEventListener("click", function () { goal = VIEWS[b.getAttribute("data-view")]; });
    });
  }

  // ---------------------------------------------------------------- inputs
  var input = { a: 0, b: 0 }, sim = null;
  function pressInput(name, down) {
    if (name === "A" || name === "AB") input.a = down ? 1 : 0;
    if (name === "B" || name === "AB") input.b = down ? 1 : 0;
    syncButtons();
  }
  var uiHolds = { A: 0, B: 0, AB: 0 };
  function syncButtons() {
    $("btnA").classList.toggle("down", !!input.a);
    $("btnB").classList.toggle("down", !!input.b);
    $("btnAB").classList.toggle("down", !!(input.a && input.b));
    if (sim) sim.x.sim_set_inputs(input.a, input.b);
    pressables.forEach(function (m) {
      var on = (m.userData.button === "A" && input.a) || (m.userData.button === "B" && input.b);
      m.material.color.setHex(on ? 0x5b6ee0 : 0x23262d);
    });
  }
  function bindHold(id, name) {
    var el = $(id);
    el.addEventListener("pointerdown", function (e) { e.preventDefault(); el.setPointerCapture(e.pointerId); pressInput(name, true); });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (ev) { el.addEventListener(ev, function () { pressInput(name, false); }); });
    el.addEventListener("keydown", function (e) { if (e.key === " " || e.key === "Enter") { e.preventDefault(); if (!e.repeat) pressInput(name, true); } });
    el.addEventListener("keyup", function (e) { if (e.key === " " || e.key === "Enter") pressInput(name, false); });
  }
  bindHold("btnA", "A"); bindHold("btnB", "B"); bindHold("btnAB", "AB");
  window.addEventListener("keydown", function (e) {
    if (e.repeat || e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.ctrlKey || e.metaKey) return;
    var k = e.key.toLowerCase(); if (k === "a") pressInput("A", true); if (k === "b") pressInput("B", true);
  });
  window.addEventListener("keyup", function (e) { var k = e.key.toLowerCase(); if (k === "a") pressInput("A", false); if (k === "b") pressInput("B", false); });

  // LIS2DH12 scale (datasheet, not firmware): +-2 g range, 16 mg per count (see tilt.h).
  var COUNTS_PER_G = 1000 / 16;
  function pushTilt() {
    var deg = +$("tilt").value, r = deg * Math.PI / 180;
    $("tiltVal").textContent = deg + "°" + (deg === 90 ? " (arm down)" : deg === 0 ? " (face up, level)" : "");
    if (!sim) return;
    var x = Math.round(Math.sin(r) * COUNTS_PER_G), z = Math.round(Math.cos(r) * COUNTS_PER_G);
    sim.x.sim_set_accel(Math.max(-128, Math.min(127, x)), 0, Math.max(-128, Math.min(127, z)));
  }
  function pushVbat() {
    var mv = +$("vbat").value; $("vbatVal").textContent = fmtMv(mv);
    if (sim) sim.x.sim_set_vbat_mv(mv);
  }
  $("restart").addEventListener("click", function () {
    if (!sim) return;
    input.a = input.b = 0; sim.x.sim_init(); simRemainder = 0;
    syncButtons(); pushTilt(); pushVbat();
  });
  $("tilt").addEventListener("input", pushTilt);
  $("vbat").addEventListener("input", pushVbat);

  // ---------------------------------------------------------------- status panel
  function buildLines(c) {
    var box = $("lines"); box.textContent = "";
    for (var i = 0; i < c.LED_LINES; i++) {
      var d = document.createElement("div"); d.className = "line z";
      var pin = i < 5 ? "PA" + (i + 3) : "PB" + (12 - i); // from board.h
      d.innerHTML = "<b>L" + i + "</b><span>" + pin + "</span>";
      box.appendChild(d);
    }
    var f = $("frame"); f.textContent = "";
    f.style.gridTemplateColumns = "repeat(" + c.FRAME_TICKS + ", 1fr)";
    for (var k = 0; k < c.FRAME_TICKS; k++) { var t = document.createElement("div"); t.className = "tick"; t.textContent = "–"; f.appendChild(t); }
    $("frameInfo").textContent = "(" + c.FRAME_TICKS + " ticks at " + c.TICK_HZ + " Hz)";
  }
  var lineEls, tickEls;
  function updatePanel(c) {
    var x = sim.x;
    $("sTime").textContent = pad2(x.sim_hour() || 12) + ":" + pad2(x.sim_minute()) + ":" + pad2(x.sim_second());
    $("sAwake").textContent = x.sim_awake() ? "Awake (scanning LEDs)" : "Asleep (LEDs off)";
    $("sState").textContent = stateName(c, x.sim_state());
    $("sDisp").textContent = dispName(c, x.sim_display());
    var lit = [];
    for (var i = 0; i < c.LED_COUNT; i++) if (x.sim_led_duty(i) > 0) lit.push(i < c.LED_HOUR_FIRST ? "min " + (i - c.LED_MINUTE_FIRST) : "hr " + (i - c.LED_HOUR_FIRST));
    $("sLeds").textContent = lit.length ? lit.join(", ") : "none";
    var dir = x.sim_line_dir(), out = x.sim_line_out();
    lineEls = lineEls || qa("#lines .line");
    for (var l = 0; l < c.LED_LINES; l++) {
      var driven = (dir >> l) & 1, hi = (out >> l) & 1;
      lineEls[l].className = "line " + (driven ? (hi ? "h" : "l") : "z");
    }
    tickEls = tickEls || qa("#frame .tick");
    // last FRAME_TICKS ticks, oldest on the left; the newest tick is highlighted
    for (var k = 0; k < c.FRAME_TICKS; k++) {
      var led = x.sim_tick_log(c.FRAME_TICKS - 1 - k), none = led === c.LED_NONE;
      tickEls[k].textContent = none ? "–" : String(led);
      tickEls[k].className = "tick" + (none ? "" : " on") + (k === c.FRAME_TICKS - 1 ? " cur" : "");
    }
  }

  function updateLeds(c) {
    var x = sim.x, boost = 2.6;
    for (var i = 0; i < ledMeshes.length; i++) {
      if (!ledMeshes[i]) continue;
      var d = x.sim_led_duty(i) / c.FRAME_TICKS, v = Math.min(1, d * boost);
      ledMeshes[i].material.emissiveIntensity = v * 2.2;
      glowSprites[i].material.opacity = v * 0.9;
    }
  }

  // ---------------------------------------------------------------- main loop
  var lastT = 0, simRemainder = 0, panelT = 0;
  function frame(t) {
    requestAnimationFrame(frame);
    var dt = Math.min(0.1, (t - lastT) / 1000 || 0); lastT = t;
    if (sim) {
      var speed = +$("speed").value, ms = dt * 1000 * speed + simRemainder, whole = Math.floor(ms);
      simRemainder = ms - whole;
      // advance in slices so very fast speeds still step the UI machine properly
      while (whole > 0) { var s = Math.min(whole, 250); sim.x.sim_advance_ms(s); whole -= s; }
      if (!fb) updateLeds(sim.c);
      if (t - panelT > 80) { panelT = t; updatePanel(sim.c); }
    }
    if (goal) {
      var k = 1 - Math.pow(0.001, dt);
      var dth = goal.theta - orbit.theta; dth = Math.atan2(Math.sin(dth), Math.cos(dth));
      orbit.theta += dth * k; orbit.phi += (goal.phi - orbit.phi) * k; orbit.dist += (goal.dist - orbit.dist) * k;
      if (Math.abs(dth) + Math.abs(goal.phi - orbit.phi) + Math.abs(goal.dist - orbit.dist) < 0.002) goal = null;
    }
    if (fb) { draw2d(); return; }
    updateCamera();
    renderer.render(scene, camera);
  }

  function showError(msg) {
    var l = $("loading"); l.className = "error"; l.textContent = msg; l.style.display = "grid";
  }

  async function start() {
    try {
      var results = await Promise.all([
        fetch("board-geometry.json").then(function (r) { if (!r.ok) throw new Error("board-geometry.json: HTTP " + r.status); return r.json(); }),
        loadSim()
      ]);
      var geo = results[0]; sim = results[1];
      if (typeof THREE === "undefined") throw new Error("three.js did not load (CDN blocked?)");
      fillConsts(sim.c);
      var v = $("vbat"); v.min = Math.min(2000, sim.c.VBAT_EMPTY_MV - 300); v.max = sim.c.VBAT_FRESH_MV + 200; v.value = sim.c.VBAT_FRESH_MV;
      buildLines(sim.c);
      buildScene(geo); if (!fb) setupOrbit();
      pushVbat(); pushTilt(); syncButtons();
      $("loading").style.display = "none";
      window.addEventListener("resize", onResize);
      if (window.ResizeObserver) new ResizeObserver(onResize).observe(stage);
      requestAnimationFrame(frame);
      window.__watchSim = { sim: sim, press: pressInput }; // handy for tests
    } catch (e) {
      showError("Could not start the simulator: " + e.message);
    }
  }
  start();
})();
