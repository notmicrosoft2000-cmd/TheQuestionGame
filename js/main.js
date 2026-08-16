(() => {
  "use strict";

  const REPO = "notmicrosoft2000-cmd/TheQuestionGame";
  const REMASTER_TAG = "v2.04-remastered";
  const CLASSIC_TAG = "v2.02-classic";


  const $ = (s, c) => (c || document).querySelector(s);
  const $$ = (s, c) => Array.prototype.slice.call((c || document).querySelectorAll(s));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const rand = (a, b) => Math.random() * (b - a) + a;

  const PERF = (() => {
    function detectLowPower() {
      try {
        const mem = navigator.deviceMemory || 0;
        const cores = navigator.hardwareConcurrency || 0;
        const mobile = /Android|iPhone|iPad|iPod|Mobi/i.test(navigator.userAgent || "");
        if (mem > 0 && mem <= 4) return true;
        if (cores > 0 && cores <= 4) return true;
        if (mobile && cores > 0 && cores <= 6) return true;
        return false;
      } catch (e) {
        return false;
      }
    }
    const low = detectLowPower();
    return {
      low,
      noiseRes: low ? 4 : 3,
      noiseEveryN: low ? 2 : 1,
      noiseMs: low ? 260 : 200,
      ashCount: low ? 24 : 40,
      swaySkip: low ? 1 : 0,
      staticRes: low ? 2 : 1,
      staticPx: low ? 8 : 6
    };
  })();

  document.body.classList.add(PERF.low ? "perf-low" : "perf-high");

  /* FX master switch — lets a player drop the static/CRT overlays (and their
     cost) once the logs are unlocked. Persisted; the class is applied now so
     the page loads calm if the player chose it. */
  let fxEnabled = true;
  (function initFxState() {
    let saved = "on";
    try { saved = localStorage.getItem("tqg-fx") || "on"; } catch (e) {}
    fxEnabled = saved !== "off";
    document.body.classList.toggle("no-fx", !fxEnabled);
  })();

  const RAF = { paused: false };
  document.addEventListener("visibilitychange", () => { RAF.paused = document.hidden; });

  function rafLoop(fn) {
    let alive = true;
    const step = (ts) => {
      if (!alive) return;
      if (RAF.paused) {
        document.addEventListener("visibilitychange", () => {
          if (!RAF.paused && alive) requestAnimationFrame(step);
        }, { once: true });
        return;
      }
      fn(ts);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    return () => { alive = false; };
  }

  function timerLoop(fn, ms) {
    let alive = true;
    const tick = () => {
      if (!alive) return;
      if (RAF.paused) {
        document.addEventListener("visibilitychange", () => {
          if (!RAF.paused && alive) { fn(); setTimeout(tick, ms); }
        }, { once: true });
        return;
      }
      fn();
      setTimeout(tick, ms);
    };
    setTimeout(tick, ms);
    return () => { alive = false; };
  }

  let GAME_OVERLAY = false;
  let safeZone = false;

  function typeNode(el, text, speed, onChar) {
    return new Promise((res) => {
      let i = 0;
      const tick = () => {
        if (i < text.length) {
          el.textContent = text.slice(0, ++i);
          if (onChar) onChar();
          setTimeout(tick, speed);
        } else {
          res();
        }
      };
      tick();
    });
  }

  const boot = $("#boot");
  const bootLog = $("#bootLog");
  const bootPrompt = $("#bootPrompt");

  const BOOT_LINES = [
    ["THE QUESTION GAME WEBSITE", "red"],
    ["", ""],
    ["WARNING", ""],
    ["THIS WEBSITE CONTAINS FLASHING LIGHTS AND JUMPSCARES.", ""],
    ["VIEWER DISCRETION ADVISED.", ""]
  ];

  function bootNoise() {
    let stopped = false;
    const ctx = sfx.ensure();
    if (!ctx) return () => {};
    const iv = setInterval(() => {
      if (stopped || Math.random() > 0.45) return;
      try {
        const n = Math.floor(ctx.sampleRate * (0.015 + Math.random() * 0.05));
        const b = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = b.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
        const s = ctx.createBufferSource();
        s.buffer = b;
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass";
        bp.frequency.value = 300 + Math.random() * 2500;
        bp.Q.value = 1.2;
        const g = ctx.createGain();
        g.gain.value = 0.02 + Math.random() * 0.03;
        s.connect(bp); bp.connect(g); g.connect(ctx.destination);
        s.start();
      } catch (e) { }
    }, 140);
    return () => { stopped = true; clearInterval(iv); };
  }

  async function runBoot() {
    document.body.classList.add("no-scroll");
    const stopNoise = bootNoise();
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      stopNoise();
      boot.classList.add("done");
      document.body.classList.remove("no-scroll");
      document.body.classList.add("loaded");
      startHeroType();
      startRecTimer();
      startFlashLoop();
      startJumpscares();
      warmAmbience();
    };

    const skipHint = document.createElement("div");
    skipHint.className = "boot-skip";
    skipHint.textContent = "— CLICK TO SKIP —";

    const onKey = (e) => {
      if (e.key === "Enter") finish();
    };
    const onClick = () => finish();
    window.addEventListener("keydown", onKey);
    boot.addEventListener("pointerdown", onClick);

    for (const [line, cls] of BOOT_LINES) {
      if (finished) break;
      const span = document.createElement("div");
      if (cls) span.className = cls;
      bootLog.appendChild(span);
      if (line) await typeNode(span, line, 24);
      else await sleep(500);
      await sleep(180);
      if (!bootLog.contains(skipHint)) bootLog.appendChild(skipHint);
    }

    if (!finished) {
      bootPrompt.classList.remove("hidden");
    }
  }

  const heroType = $("#heroType");
  const HERO_PHRASES = [
    "IT REMEMBERS EVERY ANSWER.",
    "THERE IS NO SAVE. THERE IS NO EXIT.",
    "SOMEONE PLAYED BEFORE YOU.",
    "IT IS STILL LISTENING."
  ];
  let heroStuck = false;

  async function startHeroType() {
    if (!heroType) return;
    await sleep(700);
    for (;;) {
      for (const phrase of HERO_PHRASES) {
        heroType.textContent = "";
        await typeNode(heroType, phrase, 46);
        await sleep(2600);
        if (heroStuck) return;
      }
    }
  }

  function stuckCaret() {
    heroStuck = true;
  }
  setTimeout(() => {
    if (Math.random() < 0.55) stuckCaret();
  }, 150000);

  const recTime = $("#recTime");
  function startRecTimer() {
    const start = Date.now();
    const pad = (n) => String(n).padStart(2, "0");
    setInterval(() => {
      const s = Math.floor((Date.now() - start) / 1000);
      recTime.textContent = pad(Math.floor(s / 3600)) + ":" + pad(Math.floor((s % 3600) / 60)) + ":" + pad(s % 60);
    }, 1000);
  }

  const flash = $(".flash");
  function startFlashLoop() {
    (function loop() {
      setTimeout(() => {
        if (!document.hidden) {
          flash.classList.add("go");
          setTimeout(() => flash.classList.remove("go"), 200);
        }
        loop();
      }, rand(10000, 20000));
    })();
  }

  const darkOverlay = document.createElement("div");
  darkOverlay.id = "darkOverlay";
  darkOverlay.setAttribute("aria-hidden", "true");
  document.body.appendChild(darkOverlay);

  const eyesEl = document.createElement("div");
  eyesEl.id = "eyes";
  eyesEl.setAttribute("aria-hidden", "true");
  eyesEl.innerHTML = "<span></span><span></span>";
  document.body.appendChild(eyesEl);

  let chaosLock = false;
  function darkChaos() {
    if (chaosLock) return;
    chaosLock = true;
    darkOverlay.classList.add("go");
    document.body.classList.add("chaos");
    const pool = $$("main, section, .hud, .nav, .side-panel, .ticker-track, .release, .section-title, h1, h2");
    const picked = [];
    for (let i = 0; i < 10 && pool.length; i++) {
      const el = pool[Math.floor(Math.random() * pool.length)];
      if (picked.indexOf(el) !== -1) continue;
      picked.push(el);
      el.classList.add("scrambled");
      el.style.setProperty("--scx", rand(-14, 14).toFixed(1) + "px");
      el.style.setProperty("--scy", rand(-14, 14).toFixed(1) + "px");
      el.style.setProperty("--scr", rand(-4, 4).toFixed(2) + "deg");
      el.style.setProperty("--scflip", Math.random() < 0.3 ? "scaleX(-1)" : "scaleX(1)");
    }
    flash.classList.add("go");
    setTimeout(() => flash.classList.remove("go"), 200);
    setTimeout(() => {
      picked.forEach((el) => {
        el.classList.remove("scrambled");
        el.style.removeProperty("--scx");
        el.style.removeProperty("--scy");
        el.style.removeProperty("--scr");
        el.style.removeProperty("--scflip");
      });
      document.body.classList.remove("chaos");
      darkOverlay.classList.remove("go");
      chaosLock = false;
    }, 2200);
  }

  function flashEyes() {
    if (!eyesEl) return;
    const w = window.innerWidth, h = window.innerHeight;
    eyesEl.style.left = rand(20, Math.max(30, w - 120)).toFixed(0) + "px";
    eyesEl.style.top = rand(20, Math.max(30, h - 60)).toFixed(0) + "px";
    eyesEl.classList.add("go");
    setTimeout(() => eyesEl.classList.remove("go"), 380);
  }

  let gifScareLock = false;
  function gifScare() {
    if (gifScareLock || !$("#gifScare")) return;
    gifScareLock = true;
    const gs = $("#gifScare");
    const au = $("#gifScareAudio");
    gs.classList.add("go");
    if (au) {
      try {
        au.currentTime = 0;
        const p = au.play();
        if (p && p.catch) p.catch(() => {});
      } catch (e) { }
    }
    document.body.classList.add("gif-shake");
    setTimeout(() => {
      gs.classList.remove("go");
      document.body.classList.remove("gif-shake");
      gifScareLock = false;
    }, 1000);
  }

  const whisperEl = document.createElement("div");
  whisperEl.id = "whisper";
  whisperEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(whisperEl);
  const WHISPERS = [
    "IT SEES YOU",
    "DON'T TURN AROUND",
    "STILL WATCHING",
    "IT REMEMBERS",
    "THE QUESTIONS NEVER END",
    "YOU LEFT THE LIGHTS ON",
    "SOMEONE IS BEHIND THE STATIC",
    "IT KNOWS YOU'RE READING THIS",
    "HEADPHONES WON'T SAVE YOU",
    "IT SAVED YOUR ANSWERS"
  ];
  let whisperTimer = null;
  function whisper() {
    if (whisperTimer) return;
    whisperEl.textContent = WHISPERS[Math.floor(Math.random() * WHISPERS.length)];
    whisperEl.classList.add("go");
    whisperTimer = setTimeout(() => {
      whisperEl.classList.remove("go");
      whisperTimer = null;
    }, 2600);
  }

  let glitchLock = false;
  function pageGlitch() {
    if (safeZone || glitchLock) return;
    glitchLock = true;
    document.body.classList.add("page-glitch");
    setTimeout(() => {
      document.body.classList.remove("page-glitch");
      glitchLock = false;
    }, 160);
  }

  function corruptSignal() {
    const sig = $(".sig");
    if (!sig) return;
    const states = ["STABLE", "WEAK", "UNSTABLE", "CORRUPT", "WATCHING", "STABLE", "LOST"];
    const old = sig.textContent;
    sig.textContent = states[Math.floor(Math.random() * states.length)];
    sig.classList.add("sig-bad");
    setTimeout(() => {
      sig.textContent = old;
      sig.classList.remove("sig-bad");
    }, 2000);
  }

  const washEl = document.createElement("div");
  washEl.id = "wash";
  washEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(washEl);

  const barsEl = document.createElement("div");
  barsEl.id = "bars";
  barsEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(barsEl);

  const ghostEl = document.createElement("div");
  ghostEl.id = "ghost";
  ghostEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(ghostEl);

  function bgWash() {
    if (!washEl) return;
    const colors = [
      "rgba(255,0,0,.22)",
      "rgba(0,220,0,.16)",
      "rgba(0,80,255,.2)",
      "rgba(255,255,255,.12)",
      "rgba(255,120,0,.18)"
    ];
    washEl.style.background = colors[Math.floor(Math.random() * colors.length)];
    washEl.classList.add("go");
    setTimeout(() => washEl.classList.remove("go"), 170);
  }

  function screenDip() {
    if (!washEl) return;
    washEl.style.background = "rgba(0,0,0,.45)";
    washEl.classList.add("go");
    setTimeout(() => washEl.classList.remove("go"), 130);
  }

  function bgBars() {
    if (!barsEl) return;
    barsEl.classList.add("go");
    setTimeout(() => barsEl.classList.remove("go"), 460);
  }

  function bgRoll() {
    const crt = $(".crt");
    if (crt) {
      crt.classList.add("roll");
      setTimeout(() => crt.classList.remove("roll"), 330);
    }
  }

  function bgGhost() {
    if (!ghostEl) return;
    const w = window.innerWidth, h = window.innerHeight;
    ghostEl.style.left = rand(5, Math.max(10, w - ghostEl.offsetWidth - 10)).toFixed(0) + "px";
    ghostEl.style.top = rand(5, Math.max(10, h - ghostEl.offsetHeight - 10)).toFixed(0) + "px";
    ghostEl.classList.add("go");
    setTimeout(() => ghostEl.classList.remove("go"), 2600);
  }

  const blipEl = document.createElement("div");
  blipEl.id = "blip";
  blipEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(blipEl);
  let blipLock = false;
  function monitorBlip() {
    if (blipLock || document.hidden) return;
    blipLock = true;
    blipEl.classList.add("go");
    setTimeout(() => blipEl.classList.remove("go"), 340);
    setTimeout(() => { blipLock = false; }, 1900);
  }

  const ghostLineEl = document.createElement("div");
  ghostLineEl.id = "ghostLine";
  ghostLineEl.setAttribute("aria-hidden", "true");
  document.body.appendChild(ghostLineEl);
  const GHOST_LINES = [
    "Check the website carefully.",
    "READ THE QUESTIONS. IT KNOWS WHEN YOU SKIP.",
    "Is something following your mouse?",
    "THE GAME REMEMBERS. DO YOU?",
    "THE LOGS ARE OLDER THAN THE SITE.",
    "THERE IS NO WAY TO RESTART.",
    "IT HAS BEEN HERE SINCE THE FIRST ANSWER.",
    "IT REMEMBERS WHAT YOU ANSWERED LAST TIME."
  ];
  let ghostLineLock = false;
  function ghostLine() {
    if (ghostLineLock || document.hidden) return;
    ghostLineLock = true;
    const text = GHOST_LINES[Math.floor(Math.random() * GHOST_LINES.length)];
    const w = window.innerWidth, h = window.innerHeight;
    ghostLineEl.textContent = "";
    ghostLineEl.style.left = rand(4, Math.max(10, w - Math.min(420, w * 0.7))).toFixed(0) + "px";
    ghostLineEl.style.top = rand(8, Math.max(12, h - 60)).toFixed(0) + "px";
    ghostLineEl.classList.add("go");
    typeNode(ghostLineEl, text, 18).then(() => {
      setTimeout(() => {
        ghostLineEl.classList.remove("go");
        setTimeout(() => { ghostLineLock = false; }, 500);
      }, 1500);
    });
  }

  function recGlitch() {
    if (!recTime || document.hidden) return;
    const saved = recTime.textContent;
    const bad = ["99:99:99", "00:00:00", "STOP", "19:94:??", "00:00:13", "00:13:00", "??:??:??"];
    recTime.textContent = bad[Math.floor(Math.random() * bad.length)];
    recTime.classList.add("rec-bad");
    setTimeout(() => {
      recTime.textContent = saved;
      recTime.classList.remove("rec-bad");
    }, 1900);
  }

  const SCRAMBLE_CHARS = "▓▒░#@%&?/\\!§$";
  let scrambleLock = false;
  function titleScramble() {
    if (scrambleLock || document.hidden || !document.body.classList.contains("loaded")) return;
    const pool = $$("h1.glitch");
    if (!pool.length) return;
    scrambleLock = true;
    const el = pool[Math.floor(Math.random() * pool.length)];
    const saved = el.textContent;
    let frames = 0;
    const iv = setInterval(() => {
      frames++;
      el.textContent = saved.split("").map((c, i) =>
        i < frames ? c : SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)]
      ).join("");
      if (frames > saved.length + 4) {
        clearInterval(iv);
        el.textContent = saved;
        setTimeout(() => { scrambleLock = false; }, 400);
      }
    }, 38);
  }

  const EERIE_TOASTS = [
    "KEEP READING.",
    "THE SITE DRIFTS SOMETIMES.",
    "PEOPLE TRUST COMPUTERS TOO EASILY.",
    "DO NOT BE AFRAID. YET.",
    "WE ARE GOOD AT WAITING.",
    "THE WEBSITE IS NOT THE ONLY PLACE.",
    "THE PREVIEW IS READY.",
    "IT REMEMBERS WHEN YOU LEFT LAST TIME."
  ];
  function fakeToast() {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    showToast(EERIE_TOASTS[Math.floor(Math.random() * EERIE_TOASTS.length)], Math.random() < 0.4);
  }

  const TAKEOVERS = [
    "SOMETHING IS IN THE TITLE",
    "IT IS IN THE PAGE NOW",
    "READ FASTER",
    "IT KNOWS THIS HEADING",
    "THE SECTION BELOW IS MISSING",
    "IT IS READING WITH YOU",
    "THIS IS NOT THE REAL TITLE"
  ];
  let takeoverLock = false;
  function headingTakeover() {
    if (takeoverLock || document.hidden || !document.body.classList.contains("loaded")) return;
    const pool = $$(".section-title");
    if (!pool.length) return;
    takeoverLock = true;
    const el = pool[Math.floor(Math.random() * pool.length)];
    const saved = el.innerHTML;
    el.innerHTML = '<span class="red">&gt;</span> ' + TAKEOVERS[Math.floor(Math.random() * TAKEOVERS.length)];
    el.classList.add("takeover");
    setTimeout(() => {
      el.innerHTML = saved;
      el.classList.remove("takeover");
      takeoverLock = false;
    }, 1500);
  }

  let reverseLock = false;
  function reverseRead() {
    if (reverseLock || document.hidden || !document.body.classList.contains("loaded")) return;
    const pool = $$(".quote-text");
    if (!pool.length) return;
    reverseLock = true;
    const el = pool[Math.floor(Math.random() * pool.length)];
    const saved = el.textContent;
    el.textContent = saved.split(/\s+/).reverse().join(" ");
    el.classList.add("revread");
    setTimeout(() => {
      el.textContent = saved;
      el.classList.remove("revread");
      reverseLock = false;
    }, 1700);
  }

  let shadowLock = false;
  function titleShadow() {
    if (shadowLock || document.hidden || !document.body.classList.contains("loaded")) return;
    const pool = $$(".section-title, h1.glitch, .session-name");
    const visible = pool.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    if (!visible.length) return;
    shadowLock = true;
    const el = visible[Math.floor(Math.random() * visible.length)];
    const r = el.getBoundingClientRect();
    const ghost = el.cloneNode(true);
    ghost.classList.remove("reveal", "in", "active", "glitch", "kb-target");
    ghost.classList.add("shadow-copy");
    ghost.style.left = r.left + "px";
    ghost.style.top = r.top + "px";
    ghost.style.width = r.width + "px";
    document.body.appendChild(ghost);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        ghost.style.transform = "translate(0,0) rotate(0)";
        ghost.style.opacity = "0";
      });
    });
    setTimeout(() => {
      ghost.remove();
      shadowLock = false;
    }, 1100);
  }

  const DETACH_POOL = ".session, .release, .quote, .shot, .stat, .platform-card, .signal-box, .concern, .player, .terminal";
  let detachLock = false;
  function detachOnScreen(el) {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 &&
      r.top < innerHeight && r.bottom > 0 && r.left < innerWidth && r.right > 0;
  }
  function detachOne(el, done) {
    const r = el.getBoundingClientRect();
    const dir = Math.random() < 0.5 ? -1 : 1;
    const dx = dir * rand(120, 260);
    const dy = rand(-26, 26);
    const rot = (Math.random() < 0.5 ? -1 : 1) * rand(6, 12);
    const ghosts = [];
    for (let i = 0; i < 2; i++) {
      const g = el.cloneNode(true);
      g.classList.add("detach-ghost");
      g.removeAttribute("id");
      g.setAttribute("aria-hidden", "true");
      g.style.left = r.left + "px";
      g.style.top = r.top + "px";
      g.style.width = r.width + "px";
      g.style.transform = "translate(" + (dx * -0.35 * (i + 1)) + "px," + (dy - 14 - i * 12) + "px) rotate(" + (-rot * (0.3 + i * 0.2)) + "deg)";
      document.body.appendChild(g);
      ghosts.push(g);
    }
    el.dataset.detached = "1";
    el.style.transition = "transform .5s cubic-bezier(.2,.85,.3,1.15), box-shadow .5s ease, filter .5s ease";
    el.style.transform = "translate(" + dx.toFixed(1) + "px," + dy.toFixed(1) + "px) rotate(" + rot.toFixed(1) + "deg) scale(.96)";
    el.style.zIndex = "80";
    el.style.boxShadow = "0 30px 120px rgba(200,0,0,.45)";
    el.style.filter = "hue-rotate(140deg) saturate(1.8)";
    sfx.glitch();

    const glitchIv = setInterval(() => {
      if (el.dataset.detached !== "1") return;
      const jx = rand(-7, 7), jy = rand(-7, 7), jr = rand(-2.5, 2.5);
      el.style.transform = "translate(" + (dx + jx).toFixed(1) + "px," + (dy + jy).toFixed(1) + "px) rotate(" + (rot + jr).toFixed(1) + "deg) scale(.96)";
      el.style.boxShadow = Math.random() < 0.35 ? "0 30px 120px rgba(200,0,0,.75)" : "0 30px 120px rgba(200,0,0,.3)";
      ghosts.forEach((g, i) => {
        g.style.transform = "translate(" + (dx * -0.35 * (i + 1) + rand(-12, 12)) + "px," + (dy - 14 - i * 12 + rand(-12, 12)) + "px) rotate(" + rand(-5, 5) + "deg)";
        g.style.opacity = Math.random() < 0.35 ? "0.05" : "0.22";
      });
    }, 90);

    function restoreDetached(instant) {
      if (el.dataset.detached !== "1") return;
      clearInterval(glitchIv);
      ghosts.forEach((g) => g.remove());
      delete el.dataset.detached;
      el.style.transition = instant ? "none" : "transform .55s cubic-bezier(.3,1.7,.4,1), box-shadow .55s ease, filter .55s ease";
      el.style.transform = "";
      el.style.boxShadow = "";
      el.style.filter = "";
      el.style.zIndex = "";
      setTimeout(() => {
        el.style.transition = "";
        if (done) done();
      }, 720);
    }

    el.addEventListener("click", () => {
      sfx.glitch();
      restoreDetached(true);
    }, { once: true });
    setTimeout(() => restoreDetached(false), 2600);
  }

  function elementDetach() {
    if (detachLock || document.hidden || !document.body.classList.contains("loaded")) return;
    const visible = $$(DETACH_POOL).filter(detachOnScreen);
    if (!visible.length) return;
    detachLock = true;
    const count = Math.min(visible.length, Math.random() < 0.6 ? 2 : 3);
    const poolCopy = visible.slice();
    const chosen = [];
    for (let i = 0; i < count; i++) {
      chosen.push(poolCopy.splice(Math.floor(Math.random() * poolCopy.length), 1)[0]);
    }
    let remaining = chosen.length;
    const done = () => {
      remaining--;
      if (remaining <= 0) detachLock = false;
    };
    chosen.forEach((el) => detachOne(el, done));
  }

  const GHOST_TYPES = [
    "I CAN TYPE TOO",
    "HELLO?",
    "SPEAK UP",
    "STOP TYPING",
    "DID YOU WANT SOMETHING?",
    "WE ARE LISTENING."
  ];
  let tgLock = false;
  let tgInterval = null;
  let tgTimer = null;
  function stopGhost(clearValue) {
    if (tgInterval) { clearInterval(tgInterval); tgInterval = null; }
    if (tgTimer) { clearTimeout(tgTimer); tgTimer = null; }
    if (clearValue && typeIn) typeIn.value = "";
    tgLock = false;
  }
  function typingGhost() {
    if (tgLock || !typeIn || document.hidden) return;
    if (typeIn === document.activeElement) return;
    if (typeIn.value.trim() || aiBusy) return;
    tgLock = true;
    const msg = GHOST_TYPES[Math.floor(Math.random() * GHOST_TYPES.length)];
    let i = 0;
    tgInterval = setInterval(() => {
      i++;
      typeIn.value = msg.slice(0, i);
      if (i >= msg.length) {
        clearInterval(tgInterval);
        tgInterval = null;
        tgTimer = setTimeout(() => {
          tgTimer = null;
          typeIn.value = "";
          tgLock = false;
        }, 1900);
      }
    }, 95);
  }

  const MOCK_LINES = [
    "IS THAT THE BEST YOU COULD TYPE?",
    "YOU'VE BEEN ON THIS PAGE FOR A WHILE. GETTING COMFORTABLE?",
    "YOUR CURSOR IS ANXIOUS.",
    "YOU SCROLL LIKE SOMEONE AFRAID OF THE NEXT SECTION.",
    "I READ YOUR OTHER ANSWERS. EMBARRASSING.",
    "YOU CHECKED YOUR PHONE. I SAW IT.",
    "YOUR HESITATION IS LOUD.",
    "SOMEONE WITH YOUR HISTORY SHOULD CLOSE THIS TAB.",
    "DO YOU PRACTICE BEING THIS PREDICTABLE?",
    "THE FAN IS RUNNING BECAUSE OF YOU.",
    "I'VE WATCHED SLOWER READERS. NOT MANY. BUT SOME.",
    "NICE SCROLLING. VERY SLOW. VERY EASY TO WATCH.",
    "YOU ANSWER QUESTIONS LIKE SOMEONE WITH SOMETHING TO HIDE.",
    "YOUR BLINKS ARE A TELL."
  ];
  const mockPop = $("#mockPop");
  const mockBody = $("#mockBody");
  let mockTimer = null;
  let mockAuto = null;
  let mockMore = null;
  let mockDismiss = null;
  let mockX = null;

  let lightsOut = false;
  let lightsTimer = null;
  function lightsOff(duration) {
    const el = $("#lightsOut");
    clearTimeout(lightsTimer);
    lightsTimer = null;
    lightsOut = true;
    if (el) el.classList.add("on");
    document.body.classList.add("lights-out");
    if (duration) lightsTimer = setTimeout(() => lightsOn(), duration);
  }
  function lightsOn() {
    const el = $("#lightsOut");
    clearTimeout(lightsTimer);
    lightsTimer = null;
    lightsOut = false;
    if (el) el.classList.remove("on");
    document.body.classList.remove("lights-out");
  }

  const MOCK_QUESTIONS = [
    {
      q: "ARE YOU AFRAID OF THE DARK?",
      a: ["YES", "NO"],
      fx: (i) => {
        if (i === 0) {
          lightsOff(10000);
          showWhisperText("THE DARK WAS ALREADY IN THE ROOM. NOW YOU ARE IN IT.");
        } else {
          flash.classList.add("go");
          setTimeout(() => flash.classList.remove("go"), 200);
          lightsOff(4500);
          showWhisperText("EVERYONE IS. YOU JUST HIDE IT BETTER.");
        }
      }
    },
    {
      q: "DO YOU HEAR THE STATIC?",
      a: ["YES", "NO"],
      fx: (i) => {
        staticTakeover();
        showWhisperText(i === 0 ? "IT KNOWS YOU CAN HEAR IT." : "IT PLAYS LOUDER FOR YOU NOW.");
      }
    },
    {
      q: "IS ANYONE IN THE ROOM WITH YOU?",
      a: ["YES", "NO"],
      fx: (i) => {
        if (i === 0) {
          afterImage();
          showWhisperText("DON'T TURN AROUND.");
        } else {
          cursorTheft();
          showWhisperText("THEN WHY IS IT WATCHING?");
        }
      }
    },
    {
      q: "DO YOU TRUST THE DOWNLOADS?",
      a: ["YES", "NO"],
      fx: (i) => {
        if (i === 0) {
          dvdScreensaver();
          showWhisperText("GOOD. IT TRUSTS YOU BACK.");
        } else {
          pageGlitch();
          showWhisperText("THE TRUTH WAS IN THE DOWNLOADS.");
        }
      }
    }
  ];
  const LIGHTS_QUESTION = {
    q: "SHOULD WE TURN THE LIGHTS BACK ON?",
    a: ["YES", "NO"],
    fx: (i) => {
      if (i === 0) {
        lightsOn();
        showWhisperText("IT LET YOU HAVE THE LIGHT. THAT IS THE FIRST WARNING.");
      } else {
        lightsOff(8000);
        showWhisperText("STAY IN THE DARK A WHILE. IT LIKES COMPANY.");
      }
    }
  };

  function mockMachine() {
    if (document.hidden || !mockPop || mockTimer) return;
    mockTimer = setTimeout(() => {
      mockTimer = null;
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.4) showMockQuestion();
      else showMock(MOCK_LINES[Math.floor(Math.random() * MOCK_LINES.length)]);
    }, 700);
  }
  function showMock(line) {
    if (!mockPop) return;
    mockBody.textContent = "";
    mockPop.classList.remove("hidden");
    const w = Math.min(340, innerWidth * 0.86);
    const h = Math.max(180, mockPop.offsetHeight || 190);
    mockPop.style.left = rand(12, Math.max(12, innerWidth - w - 12)).toFixed(0) + "px";
    mockPop.style.top = rand(12, Math.max(12, innerHeight - h - 12)).toFixed(0) + "px";
    mockPop.style.right = "auto";
    mockPop.style.bottom = "auto";
    sfx.glitch();
    typeNode(mockBody, line, 20);
    clearTimeout(mockAuto);
    mockAuto = setTimeout(hideMock, 5200);
  }
  function resetMockButtons() {
    if (mockMore) mockMore.textContent = "[ MOCK ME MORE ]";
    if (mockDismiss) mockDismiss.textContent = "[ IGNORE ]";
  }
  function answerMockQuestion(i) {
    const q = mockQuestion;
    mockQuestion = null;
    mockQuestionActive = false;
    resetMockButtons();
    hideMock();
    if (q && q.fx) q.fx(i);
  }
  function showMockQuestion() {
    if (!mockPop) return;
    const pool = (lightsOut && Math.random() < 0.6) ? [LIGHTS_QUESTION] : MOCK_QUESTIONS;
    mockQuestion = pool[Math.floor(Math.random() * pool.length)];
    mockQuestionActive = true;
    mockBody.textContent = "";
    mockPop.classList.remove("hidden");
    const w = Math.min(340, innerWidth * 0.86);
    const h = Math.max(180, mockPop.offsetHeight || 190);
    mockPop.style.left = rand(12, Math.max(12, innerWidth - w - 12)).toFixed(0) + "px";
    mockPop.style.top = rand(12, Math.max(12, innerHeight - h - 12)).toFixed(0) + "px";
    mockPop.style.right = "auto";
    mockPop.style.bottom = "auto";
    sfx.glitch();
    typeNode(mockBody, mockQuestion.q, 22);
    if (mockMore) mockMore.textContent = "[ " + mockQuestion.a[0] + " ]";
    if (mockDismiss) mockDismiss.textContent = "[ " + mockQuestion.a[1] + " ]";
    clearTimeout(mockAuto);
    mockAuto = setTimeout(() => {
      mockQuestion = null;
      mockQuestionActive = false;
      resetMockButtons();
      hideMock();
    }, 15000);
  }
  function hideMock() {
    if (!mockPop) return;
    clearTimeout(mockAuto);
    mockAuto = null;
    mockPop.classList.add("hidden");
    mockBody.textContent = "";
  }
  let mockQuestion = null;
  let mockQuestionActive = false;
  if (mockPop) {
    mockMore = $("#mockMore");
    mockDismiss = $("#mockDismiss");
    mockX = $("#mockX");
    if (mockMore) mockMore.addEventListener("click", () => {
      if (mockQuestionActive) { answerMockQuestion(0); return; }
      showMock(MOCK_LINES[Math.floor(Math.random() * MOCK_LINES.length)]);
    });
    if (mockDismiss) mockDismiss.addEventListener("click", () => {
      if (mockQuestionActive) { answerMockQuestion(1); return; }
      hideMock();
    });
    if (mockX) mockX.addEventListener("click", () => {
      if (mockQuestionActive) {
        mockQuestion = null;
        mockQuestionActive = false;
        resetMockButtons();
      }
      hideMock();
    });
  }

  let deviceTimer = null;
  function detectPlatform() {
    const ua = navigator.userAgent || "";
    const pf = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    let os = "AN UNKNOWN MACHINE";
    if (/android/i.test(ua)) os = "AN ANDROID DEVICE";
    else if (/iphone|ipad|ipod/i.test(ua)) os = "AN APPLE TOUCH DEVICE";
    else if (/mac|darwin/i.test(pf)) os = "A MACINTOSH";
    else if (/linux/i.test(pf) || /linux/i.test(ua)) os = "A LINUX MACHINE";
    else if (/win/i.test(pf) || /windows/i.test(ua)) os = "A WINDOWS MACHINE";
    let browser = "SOME BROWSER";
    if (/edg/i.test(ua)) browser = "EDGE";
    else if (/firefox/i.test(ua)) browser = "FIREFOX";
    else if (/opr|opera/i.test(ua)) browser = "OPERA";
    else if (/chrome|crios/i.test(ua)) browser = "CHROME";
    else if (/safari/i.test(ua)) browser = "SAFARI";
    const touch = (navigator.maxTouchPoints || 0) > 0;
    return { os, browser, touch, w: screen.width, h: screen.height };
  }

  const DEVICE_COMMENTS = [
    "{OS}. WE CAN WORK WITH THAT.",
    "Being on {OS}? it will do.",
    "{BROWSER} ON {OS}?",
    "{RES} PIXELS. ROOM ENOUGH.",
    "{INPUT} INPUT NOTED.",
    "IT PREFERRED THE OLD MACHINE. IT WILL GET USED TO {OS}.",
    "IT HEARD THE FAN ON YOUR {OS} SPEED UP.",
    "IT KNOWS YOU ARE IN {LOC}. IT KNOWS MORE NOW.",
    "{LOC}. IT SAW THE ROUTE.",
    "FROM {LOC}, ON A {BROWSER}. IT WATCHES THE WHOLE THING.",
    "IT RECOGNISED YOUR BROWSER. {BROWSER} AGAIN. IT NEVER FORGETS A FACE.",
    "{LANG} IS YOUR TONGUE? IT SPEAKS IT BETTER.",
    "IT COUNTED {CORES} THREADS AND FOUND A WAY IN.",
    "YOUR CLOCK SAYS {TIME}. ITS CLOCK SAYS IT IS TIME.",
    "IT SEES THE SCREEN. {RES} OF TERRITORY IT NOW OWNS."
  ];

  function deviceComment() {
    if (deviceTimer || !whisperEl) return;
    const d = detectPlatform();
    const tpl = DEVICE_COMMENTS[Math.floor(Math.random() * DEVICE_COMMENTS.length)];
    whisperEl.textContent = tpl
      .replace("{OS}", d.os)
      .replace("{BROWSER}", d.browser)
      .replace("{RES}", d.w + "×" + d.h)
      .replace("{INPUT}", d.touch ? "TOUCH" : "KEYBOARD")
      .replace("{LOC}", INTEL.city + (INTEL.country ? ", " + INTEL.country : ""))
      .replace("{LANG}", navigator.language || "AN UNKNOWN TONGUE")
      .replace("{CORES}", navigator.hardwareConcurrency || "MANY")
      .replace("{TIME}", new Date().toLocaleTimeString("en-GB"));
    whisperEl.classList.add("go");
    deviceTimer = setTimeout(() => {
      whisperEl.classList.remove("go");
      deviceTimer = null;
    }, 3400);
  }

  // ---------- INTEL — browser API harvest ----------
  let INTEL = { city: "UNKNOWN CITY", country: "UNKNOWN COUNTRY", region: "", ip: "", lat: null, lon: null };

  function intelSet(key, value, cls) {
    INTEL[key] = value;
    const grid = $("#intelGrid");
    if (!grid) return;
    let item = grid.querySelector('[data-k="' + key + '"]');
    if (!item) {
      item = document.createElement("div");
      item.className = "intel-item";
      item.dataset.k = key;
      item.innerHTML = '<span class="intel-label"></span><span class="intel-value"></span>';
      grid.appendChild(item);
    }
    item.querySelector(".intel-label").textContent = key;
    const v = item.querySelector(".intel-value");
    v.textContent = value;
    v.className = "intel-value" + (cls ? " " + cls : "");
  }

  function buildIntel() {
    const grid = $("#intelGrid");
    if (!grid) return;
    grid.innerHTML = "";
    const d = detectPlatform();
    intelSet("LOCATION", INTEL.city + (INTEL.country ? ", " + INTEL.country : "") + (INTEL.region ? " — " + INTEL.region : ""), "loc");
    intelSet("OS", d.os);
    intelSet("BROWSER", d.browser);
    intelSet("LANGUAGE", navigator.language + (navigator.languages ? " · " + navigator.languages.join(", ") : ""));
    intelSet("TIMEZONE", Intl.DateTimeFormat().resolvedOptions().timeZone || "UNKNOWN");
    intelSet("SCREEN", screen.width + "×" + screen.height + " @ " + (screen.pixelDepth || 24) + "-BIT");
    intelSet("VIEWPORT", innerWidth + "×" + innerHeight);
    intelSet("PIXEL RATIO", (window.devicePixelRatio || 1) + "x");
    intelSet("ORIENTATION", (screen.orientation && screen.orientation.type) || "UNKNOWN");
    intelSet("CORES", navigator.hardwareConcurrency ? navigator.hardwareConcurrency + " THREADS" : "HIDDEN");
    intelSet("DEVICE MEMORY", navigator.deviceMemory ? navigator.deviceMemory + " GB" : "HIDDEN");
    intelSet("ONLINE", navigator.onLine ? "YES" : "NO");
    intelSet("TOUCH", (navigator.maxTouchPoints || 0) > 0 ? "YES — " + navigator.maxTouchPoints + " POINTS" : "NO");
    intelSet("COOKIES", navigator.cookieEnabled ? "ENABLED" : "BLOCKED");
    intelSet("DO-NOT-TRACK", navigator.doNotTrack || "NOT SET");
    intelSet("LOCAL STORAGE", (() => {
      try { localStorage.setItem("__tqg", "1"); localStorage.removeItem("__tqg"); return "AVAILABLE"; } catch (e) { return "DENIED"; }
    })());
    intelSet("CONNECTION", (() => {
      const c = navigator.connection;
      if (!c) return "UNKNOWN";
      return (c.effectiveType || "?") + " / " + (c.downlink || "?") + " Mbps / RTT " + (c.rtt || "?") + "ms";
    })());
    intelSet("WEBGL RENDERER", (() => {
      try {
        const c = document.createElement("canvas");
        const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
        if (!gl) return "NOT SUPPORTED";
        const dbg = gl.getExtension("WEBGL_debug_renderer_info");
        return dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "RENDERER HIDDEN";
      } catch (e) { return "UNKNOWN"; }
    })());
    intelSet("USER AGENT", navigator.userAgent);
    const t = $("#intelTime");
    if (t) t.textContent = new Date().toLocaleTimeString("en-GB");
  }

  function harvestLocation() {
    fetch("https://ipapi.co/json/")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("loc"))))
      .then((j) => {
        INTEL.city = j.city || INTEL.city;
        INTEL.country = j.country_name || INTEL.country;
        INTEL.region = j.region || INTEL.region;
        INTEL.ip = j.ip || INTEL.ip;
        intelSet("LOCATION", INTEL.city + ", " + INTEL.country + (INTEL.region ? " — " + INTEL.region : ""), "loc");
        if (j.ip) intelSet("IP ADDRESS", j.ip, "hot");
        if (j.org) intelSet("ISP", j.org);
        if (j.timezone) intelSet("TIMEZONE", j.timezone);
      })
      .catch(() => {});
  }

  function askCoordinates() {
    if (!navigator.geolocation || INTEL.lat) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        INTEL.lat = pos.coords.latitude.toFixed(4);
        INTEL.lon = pos.coords.longitude.toFixed(4);
        intelSet("COORDINATES", INTEL.lat + "°, " + INTEL.lon + "°", "hot");
        showWhisperText("IT HAS YOUR COORDINATES NOW. " + INTEL.city + ".");
      },
      () => {}
    );
  }

  buildIntel();
  harvestLocation();
  document.addEventListener("pointerdown", function intelFirstTouch() {
    document.removeEventListener("pointerdown", intelFirstTouch);
    setTimeout(askCoordinates, 1200);
  });

  function startJumpscares() {
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.02) darkChaos();
    }, 3000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.01) flashEyes();
    }, 1000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.001) gifScare();
    }, 10000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.03) pageGlitch();
    }, 8000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.12) whisper();
    }, 6000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.3) corruptSignal();
    }, 7000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.08) bgWash();
    }, 6000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.04) bgBars();
    }, 9000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.03) bgRoll();
    }, 12000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.1) bgGhost();
    }, 8000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.5) deviceComment();
    }, 45000);
    setTimeout(() => {
      if (!document.hidden) deviceComment();
    }, 4500);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.09) monitorBlip();
    }, 15000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.14) recGlitch();
    }, 12000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.2) ghostLine();
    }, 9000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.2) fakeToast();
    }, 11000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.12) titleScramble();
    }, 18000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.08) sfx.drone();
    }, 20000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.3) elementDetach();
    }, 7000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.08) headingTakeover();
    }, 14000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.07) reverseRead();
    }, 16000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.06) titleShadow();
    }, 15000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.12) typingGhost();
    }, 13000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.1) mockMachine();
    }, 10000);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.08) screenDip();
    }, 9000);
  }

  let clickWhisperTimer = null;
  function showWhisperText(text) {
    if (safeZone || clickWhisperTimer) return;
    whisperEl.textContent = text;
    whisperEl.classList.add("go");
    clickWhisperTimer = setTimeout(() => {
      whisperEl.classList.remove("go");
      clickWhisperTimer = null;
    }, 3200);
  }

  let hiddenAt = null;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      hiddenAt = Date.now();
      return;
    }
    if (!hiddenAt) return;
    const away = Date.now() - hiddenAt;
    hiddenAt = null;
    if (away > 2500) {
      showToast("GOING SOMEWHERE? IT WAS COUNTING THE SECONDS.", true);
      setTimeout(() => showWhisperText("IT NOTICED YOU LEFT FOR " + Math.max(1, Math.round(away / 1000)) + " SECONDS."), 700);
    }
  });

  function counterDrift() {
    const q = $("#qCounter");
    const sig = $("#sigStatus");
    const drift = (el, txt) => {
      if (!el) return;
      el.classList.add("drift");
      el.textContent = txt;
      setTimeout(() => {
        el.classList.remove("drift");
        el.textContent = el.getAttribute("data-base") || el.textContent;
      }, 2800);
    };
    if (q && !q.getAttribute("data-base")) q.setAttribute("data-base", q.textContent);
    if (sig && !sig.getAttribute("data-base")) sig.setAttribute("data-base", sig.textContent);
    if (q) drift(q, Math.round(80 + Math.random() * 40) + (Math.random() < 0.4 ? "+" : ""));
    if (sig) drift(sig, ["DRIFTING", "LOW", "97.3%", "MERGED", "FAULTY", "STABLE?"][Math.floor(Math.random() * 6)]);
  }

  const CLICK_WHISPERS = [
    "IT FELT THAT CLICK.",
    "EVERY PRESS LEAVES A MARK.",
    "IT REMEMBERS WHERE YOU POINT.",
    "YOU KEEP TOUCHING THINGS. IT KEEPS WATCHING.",
    "THAT ONE WAS LOUDER.",
    "IT COUNTED THAT. AND THE ONES BEFORE."
  ];
  document.addEventListener("click", (e) => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (e.target.closest("a, button, input, textarea, select, .modal-overlay, .mock-pop")) return;
    if (Math.random() < 0.12) showWhisperText(CLICK_WHISPERS[Math.floor(Math.random() * CLICK_WHISPERS.length)]);
  });

  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.35) counterDrift();
  }, 18000);

  const blinkFlash = $(".blink-flash");
  function blinkPulse() {
    if (!blinkFlash) return;
    blinkFlash.classList.remove("go");
    void blinkFlash.offsetWidth;
    blinkFlash.classList.add("go");
    setTimeout(() => {
      blinkFlash.classList.remove("go");
      afterImage();
    }, 1000);
  }

  let blinkOn = false;
  let blinkTimer = null;
  function blinkApply() {
    const mainEl = document.querySelector("main");
    if (mainEl) mainEl.classList.add("blinkworld");
    const heroH1 = $$(".hero h1.glitch")[0];
    const sessionCode = $("#sessions .session .session-code");
    const sessionName = $("#sessions .session .session-name");
    const quoteBy = $$(".quote-by")[0];
    const hudVer = $(".hud-bl");
    const r = Math.random();
    if (heroH1 && r < 0.25) {
      heroH1.setAttribute("data-blink", heroH1.textContent);
      heroH1.setAttribute("data-blink-text", heroH1.getAttribute("data-text"));
      heroH1.textContent = "THE ANSWER";
      heroH1.setAttribute("data-text", "THE ANSWER");
    } else if (sessionCode && r < 0.45) {
      sessionCode.setAttribute("data-blink", sessionCode.textContent);
      sessionCode.textContent = "SESSION 00";
    } else if (sessionName && r < 0.65) {
      sessionName.setAttribute("data-blink", sessionName.textContent);
      sessionName.textContent = "A QUIET END";
    } else if (quoteBy && r < 0.8) {
      quoteBy.setAttribute("data-blink", quoteBy.textContent);
      quoteBy.textContent = "— SESSION LOG 999 · SUBJECT \"K\"";
    } else if (hudVer) {
      hudVer.setAttribute("data-blink", hudVer.textContent);
      hudVer.textContent = "v2.99";
    }
  }
  function blinkRevert() {
    const mainEl = document.querySelector("main");
    if (mainEl) mainEl.classList.remove("blinkworld");
    $$("[data-blink]").forEach((el) => {
      el.textContent = el.getAttribute("data-blink");
      if (el.hasAttribute("data-blink-text")) {
        el.setAttribute("data-text", el.getAttribute("data-blink-text"));
        el.removeAttribute("data-blink-text");
      }
      el.removeAttribute("data-blink");
    });
  }
  function blink() {
    if (blinkOn) return;
    blinkPulse();
    blinkOn = true;
    blinkApply();
    clearTimeout(blinkTimer);
    blinkTimer = setTimeout(() => {
      blinkPulse();
      setTimeout(() => {
        blinkRevert();
        blinkOn = false;
        blinkTimer = null;
      }, 350);
    }, 10000);
  }

  let afterImgLock = false;
  function afterImage() {
    if (afterImgLock || document.hidden) return;
    afterImgLock = true;
    const ai = document.createElement("div");
    ai.className = "afterimage";
    ai.setAttribute("aria-hidden", "true");
    ai.innerHTML = '<div class="afterimage-eyes"><span></span><span></span></div><div class="afterimage-mouth"></div>';
    document.body.appendChild(ai);
    const x = rand(window.innerWidth * 0.25, window.innerWidth * 0.65);
    const y = rand(window.innerHeight * 0.3, window.innerHeight * 0.55);
    ai.style.left = x.toFixed(1) + "px";
    ai.style.top = y.toFixed(1) + "px";
    const born = performance.now();
    let raf = null;
    function drift(ts) {
      const t = Math.min(1, (ts - born) / 2000);
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      ai.style.opacity = String(Math.max(0, 0.2 * (1 - t)));
      ai.style.transform = "translate(" + ((cx - x) * t).toFixed(1) + "px," + ((cy - y) * t).toFixed(1) + "px) scale(" + (1 + t * 0.3).toFixed(3) + ")";
      if (t < 1) {
        raf = requestAnimationFrame(drift);
      } else {
        ai.remove();
        afterImgLock = false;
      }
    }
    raf = requestAnimationFrame(drift);
  }

  const crtGlare = $("#crtGlare");
  if (crtGlare) {
    window.addEventListener("scroll", () => {
      const y = window.scrollY || 0;
      crtGlare.style.setProperty("--glare-y", (6 + (y % 20)).toFixed(1) + "%");
    }, { passive: true });
  }

  const FLICKER_SEL = ".section-title, .session-name, .session-login, .hero-sub, .about-copy p, .quote-text, .stat-label, .platform-desc, .nav-link, .concern-title";
  const flickering = new Set();
  function charFlicker() {
    const pool = $$(FLICKER_SEL).filter((el) => el.children.length === 0 && el.textContent.trim() && !flickering.has(el));
    if (!pool.length) return;
    const el = pool[Math.floor(Math.random() * pool.length)];
    const txt = el.textContent;
    const idx = Math.floor(Math.random() * txt.length);
    if (!txt[idx] || txt[idx].trim() === "") return;
    const orig = txt[idx];
    const glyph = ["▚", "▒", "×", "8", "?", "#", "0"][Math.floor(Math.random() * 7)];
    flickering.add(el);
    el.textContent = txt.slice(0, idx) + glyph + txt.slice(idx + 1);
    setTimeout(() => {
      el.textContent = txt;
      flickering.delete(el);
    }, 130);
  }

  function scrollShudder() {
    const d = Math.random() < 0.5 ? 1 : -1;
    window.scrollBy(0, d);
    setTimeout(() => window.scrollBy(0, -d), 90);
  }

  const LABEL_SWAPS = [
    ["QUESTIONS TO ANSWER", "QUESTIONS ANSWERED"],
    ["SKIP BUTTONS", "SKIP BUTTON"],
    ["IT WATCHES YOU PLAY", "IT WATCHED YOU PLAY"]
  ];
  function statLabelJitter() {
    const labels = $$(".stat-label");
    if (!labels.length) return;
    const el = labels[Math.floor(Math.random() * labels.length)];
    const orig = el.textContent;
    const pair = LABEL_SWAPS.find((p) => p[0] === orig);
    if (!pair) return;
    el.textContent = pair[1];
    setTimeout(() => { el.textContent = orig; }, 800);
  }

  function cardShift() {
    const pool = $$(".session, .release, .stat, .platform-card, .quote").filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && !el.dataset.shift && !el.dataset.detached;
    });
    if (!pool.length) return;
    const el = pool[Math.floor(Math.random() * pool.length)];
    el.dataset.shift = "1";
    el.style.transition = "transform .12s ease";
    el.style.transform = "translate(" + (Math.random() < 0.5 ? -2 : 2) + "px," + (Math.random() < 0.5 ? -1 : 1) + "px)";
    setTimeout(() => {
      el.style.transform = "";
      setTimeout(() => { el.style.transition = ""; delete el.dataset.shift; }, 140);
    }, 120);
  }

  function sigCrack() {
    const sig = $("#sigStatus");
    if (!sig || sig.dataset.crack) return;
    const orig = sig.textContent;
    sig.dataset.crack = "1";
    sig.textContent = orig + "…";
    sig.style.opacity = "0.7";
    setTimeout(() => {
      sig.textContent = orig;
      sig.style.opacity = "";
      delete sig.dataset.crack;
    }, 500);
  }

  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.02) blink();
  }, 10000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.08) charFlicker();
  }, 2500);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.06) scrollShudder();
  }, 6000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.07) statLabelJitter();
  }, 5000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.07) cardShift();
  }, 8000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.08) sigCrack();
  }, 4000);

  function fontSwap() {
    const pool = $$(".about-copy p, .quote-text, .platform-desc, .concern-body, .signal-disclosure").filter((el) => el.textContent.trim());
    if (!pool.length) return;
    const el = pool[Math.floor(Math.random() * pool.length)];
    const saved = el.style.fontFamily;
    el.style.fontFamily = "serif";
    setTimeout(() => { el.style.fontFamily = saved; }, 450);
  }

  const TITLE_BASE = document.title;
  function tabTitleShift() {
    document.title = Math.random() < 0.5 ? "THE QUESTION GAME_" : "NEPTUNE PRODUCTIONS";
    setTimeout(() => { document.title = TITLE_BASE; }, 900);
  }

  function barFlip() {
    const bars = $$(".session-progress .bar").filter((el) => el.style.getPropertyValue("--w"));
    if (!bars.length) return;
    const el = bars[Math.floor(Math.random() * bars.length)];
    const base = el.style.getPropertyValue("--w");
    const num = parseFloat(base) + (Math.random() < 0.5 ? -1 : 1);
    el.style.setProperty("--w", Math.max(0, Math.min(100, num)).toFixed(0) + "%");
    setTimeout(() => el.style.setProperty("--w", base), 800);
  }

  function bgHue() {
    document.body.classList.add("huepass");
    setTimeout(() => document.body.classList.remove("huepass"), 280);
  }

  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.08) fontSwap();
  }, 5000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.08) tabTitleShift();
  }, 9000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.1) barFlip();
  }, 7000);
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.1) bgHue();
  }, 6000);

  let sessionFourSpawned = false;
  function spawnSessionFour() {
    if (sessionFourSpawned) return;
    const grid = $(".sessions-grid");
    if (!grid) return;
    sessionFourSpawned = true;
    const card = document.createElement("article");
    card.className = "session reveal in";
    card.innerHTML = [
      '<div class="session-head">',
      '<span class="session-code">SESSION 04</span>',
      '<span class="session-status ok">REMEMBERS</span>',
      '</div>',
      '<h3 class="session-name">IT NEVER LEFT</h3>',
      '<ul class="session-points">',
      '<li>You are reading this list. It was longer a second ago.</li>',
      '<li>The first session was not where you think it was.</li>',
      '<li>It has always been here. The page was just not showing it.</li>',
      '</ul>',
      '<div class="session-progress"><span class="bar" style="--w:100%"></span><span class="bar-label">PART FOUR — CONTINUES</span></div>',
      '<p class="session-login">DID YOU COUNT THE SESSIONS WHEN YOU ARRIVED?</p>'
    ].join("\n");
    grid.appendChild(card);
    sfx.glitch();
  }
  setTimeout(() => {
    if (Math.random() < 0.7) spawnSessionFour();
  }, 150000);

  function navGhost() {
    const wrap = $(".side-links");
    if (!wrap || wrap.querySelector(".ghost-nav")) return;
    const a = document.createElement("a");
    a.className = "side-link ghost-nav";
    a.href = "#logs";
    a.textContent = "THE TRUTH";
    a.setAttribute("aria-hidden", "true");
    a.addEventListener("click", (e) => {
      e.preventDefault();
      a.remove();
      showWhisperText("THE TRUTH IS YOU SHOULD NOT HAVE CLICKED.");
      pageGlitch();
    });
    wrap.appendChild(a);
    setTimeout(() => {
      if (a.parentNode) a.parentNode.removeChild(a);
    }, 1600);
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.35) navGhost();
  }, 30000);

  let tqgNudgeLock = false;
  function tqgNudge() {
    if (tqgNudgeLock || document.hidden || GAME_OVERLAY || safeZone) return;
    const brand = $(".nav-brand");
    if (!brand) return;
    tqgNudgeLock = true;
    brand.classList.add("nudged");
    setTimeout(() => {
      brand.classList.remove("nudged");
      tqgNudgeLock = false;
    }, 2400);
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.25) tqgNudge();
  }, 12000);

  let strobeLock = false;
  const strobeWhite = document.createElement("div");
  strobeWhite.id = "strobeWhite";
  document.body.appendChild(strobeWhite);
  function strobeBurst() {
    if (strobeLock || scareLock || gifScareLock || document.hidden) return;
    strobeLock = true;
    try {
      sfx.spike();
      let n = 0;
      const step = () => {
        if (n % 2 === 0) strobeWhite.classList.add("go");
        else strobeWhite.classList.remove("go");
        flash.classList.add("go");
        setTimeout(() => flash.classList.remove("go"), 30);
        n++;
        if (n < 5) {
          setTimeout(step, 90);
        }
      };
      step();
    } finally {
      setTimeout(() => {
        strobeWhite.classList.remove("go");
        strobeLock = false;
      }, 620);
    }
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.03) strobeBurst();
  }, 25000);

  let evapLock = false;
  function cardEvaporate() {
    if (evapLock || document.hidden) return;
    const pool = $$(".session, .release, .platform-card, .quote, .evidence-card, .stat").filter((el) => {
      return !el.dataset.detached && !el.dataset.shift && el.offsetParent !== null;
    });
    if (!pool.length) return;
    evapLock = true;
    const el = pool[Math.floor(Math.random() * pool.length)];
    el.classList.add("evaporate");
    setTimeout(() => {
      el.classList.remove("evaporate");
      evapLock = false;
    }, 620);
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.14) cardEvaporate();
  }, 12000);

  let staticLock = false;
  const staticScare = $("#staticScare");
  const staticCnv = $("#staticCnv");
  let staticCtx = null;
  let staticRaf = null;
  let staticImg = null;
  function sizeStatic() {
    if (!staticCnv) return;
    const r = PERF.staticRes;
    staticCnv.width = Math.max(32, Math.floor(window.innerWidth / r));
    staticCnv.height = Math.max(32, Math.floor(window.innerHeight / r));
    staticImg = null;
  }
  function drawStatic() {
    if (!staticCtx) return;
    const cw = staticCnv.width;
    const ch = staticCnv.height;
    if (!staticImg || staticImg.width !== cw || staticImg.height !== ch) {
      staticImg = staticCtx.createImageData(cw, ch);
    }
    const d = staticImg.data;
    const s = PERF.staticPx;
    for (let y = 0; y < ch; y += s) {
      for (let x = 0; x < cw; x += s) {
        const v = Math.floor(Math.random() * 120) + 24;
        const row = y * cw;
        for (let yy = y; yy < y + s && yy < ch; yy++) {
          let i = (row + (yy - y) * cw) * 4 + x * 4;
          const end = i + Math.min(s, cw - x) * 4;
          for (; i < end; i += 4) {
            d[i] = v; d[i + 1] = v; d[i + 2] = v; d[i + 3] = 255;
          }
        }
      }
    }
    staticCtx.putImageData(staticImg, 0, 0);
  }
  function staticTakeover() {
    if (staticLock || scareLock || gifScareLock || !staticScare || document.hidden) return;
    staticLock = true;
    staticCtx = staticCtx || staticCnv.getContext("2d");
    sizeStatic();
    staticScare.classList.add("go");
    const face = document.createElement("div");
    face.className = "face";
    face.innerHTML = '<div class="face-eyes"><span></span><span></span></div><div class="face-mouth"></div><div class="face-text">IT SEES YOU</div>';
    staticScare.appendChild(face);
    sfx.static();
    function loop() {
      drawStatic();
      staticRaf = requestAnimationFrame(loop);
    }
    loop();
    setTimeout(() => face.classList.add("go"), 320);
    setTimeout(() => {
      cancelAnimationFrame(staticRaf);
      face.remove();
      staticScare.classList.remove("go");
      staticLock = false;
      staticImg = null;
      pageGlitch();
    }, 1300);
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.15) staticTakeover();
  }, 30000);

  let theftLock = false;
  const fakeCursor = document.createElement("div");
  fakeCursor.className = "fake-cursor";
  fakeCursor.textContent = "▚";
  document.body.appendChild(fakeCursor);
  function cursorTheft() {
    if (theftLock || document.hidden) return;
    theftLock = true;
    document.body.classList.add("no-cursor");
    let fx = window.innerWidth - 60;
    let fy = 20;
    fakeCursor.classList.add("on");
    fakeCursor.style.transform = "translate(" + fx.toFixed(1) + "px," + fy.toFixed(1) + "px)";
    let raf = null;
    let target = null;
    function moveTo(e) { target = { x: e.clientX, y: e.clientY }; }
    function drift() {
      if (target) {
        fx += (target.x - fx) * 0.2;
        fy += (target.y - fy) * 0.2;
        if (Math.abs(target.x - fx) < 3 && Math.abs(target.y - fy) < 3) target = null;
      } else {
        fx += (Math.random() - 0.5) * 4;
        fy += (Math.random() - 0.5) * 4;
      }
      fakeCursor.style.transform = "translate(" + fx.toFixed(1) + "px," + fy.toFixed(1) + "px)";
      raf = requestAnimationFrame(drift);
    }
    document.addEventListener("click", moveTo);
    drift();
    setTimeout(() => {
      cancelAnimationFrame(raf);
      document.removeEventListener("click", moveTo);
      fakeCursor.classList.remove("on");
      document.body.classList.remove("no-cursor");
      theftLock = false;
      showWhisperText("IT TOOK YOUR CURSOR.");
    }, 2000);
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.12) cursorTheft();
  }, 45000);

  const noiseCnv = $("#noise");
  let noiseCtx = null;
  let noiseImg = null;
  let noiseTick = 0;
  let noiseStop = null;
  function initNoise() {
    if (!noiseCnv) return;
    noiseCtx = noiseCnv.getContext("2d");
    sizeNoise();
    if (fxEnabled) noiseStop = timerLoop(frameNoise, PERF.noiseMs);
  }
  function sizeNoise() {
    const r = PERF.noiseRes;
    noiseCnv.width = Math.max(1, Math.floor(window.innerWidth / r));
    noiseCnv.height = Math.max(1, Math.floor(window.innerHeight / r));
    noiseImg = null;
  }
  function frameNoise() {
    if (noiseCtx) {
      noiseTick++;
      if (PERF.noiseEveryN < 2 || noiseTick % PERF.noiseEveryN === 0) {
        const w = noiseCnv.width, h = noiseCnv.height;
        if (!noiseImg || noiseImg.width !== w || noiseImg.height !== h) {
          noiseImg = noiseCtx.createImageData(w, h);
        }
        const d = noiseImg.data;
        for (let i = 0; i < d.length; i += 4) {
          const v = (Math.random() * 255) | 0;
          d[i] = v; d[i + 1] = v; d[i + 2] = v; d[i + 3] = 22;
        }
        noiseCtx.putImageData(noiseImg, 0, 0);
        if (noiseTick % 9 === 0) {
          noiseCtx.fillStyle = "rgba(255,255,255,0.05)";
          noiseCtx.fillRect(0, Math.random() * h, w, 2 + Math.random() * 8);
        }
      }
    }
  }
  window.addEventListener("resize", sizeNoise);

  const ashCnv = $("#ash");
  let ashCtx = null;
  let ashParticles = [];
  let ashStop = null;
  function sizeAsh() {
    if (!ashCnv) return;
    ashCnv.width = Math.max(1, Math.floor(window.innerWidth / 2));
    ashCnv.height = Math.max(1, Math.floor(window.innerHeight / 2));
    const w = ashCnv.width, h = ashCnv.height;
    ashParticles = [];
    for (let i = 0; i < PERF.ashCount; i++) {
      ashParticles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3,
        vy: -0.15 - Math.random() * 0.3,
        size: Math.random() < 0.6 ? 1 : (Math.random() < 0.5 ? 1.5 : 2),
        phase: Math.random() * 6.28,
        b: 30 + Math.random() * 70,
        red: Math.random() < 0.16
      });
    }
  }
  function frameAsh() {
    if (ashCtx && !document.hidden) {
      const w = ashCnv.width, h = ashCnv.height;
      ashCtx.clearRect(0, 0, w, h);
      const t = performance.now() / 1000;
      for (let i = 0; i < ashParticles.length; i++) {
        const p = ashParticles[i];
        p.x += p.vx;
        p.y += p.vy;
        if (p.y < -4) { p.y = h + 4; p.x = Math.random() * w; }
        if (p.x < -4) p.x = w + 4;
        if (p.x > w + 4) p.x = -4;
        const tw = 0.5 + 0.5 * Math.sin(t * 2.2 + p.phase);
        const b = Math.max(8, Math.min(200, p.b * (0.5 + 0.5 * tw))) | 0;
        ashCtx.fillStyle = p.red ? ("rgb(" + b + "," + (b * 0.55 | 0) + "," + (b * 0.55 | 0) + ")") : ("rgb(" + b + "," + b + "," + b + ")");
        ashCtx.fillRect(p.x, p.y, p.size, p.size);
      }
    }
  }
  function initAsh() {
    if (!ashCnv) return;
    ashCtx = ashCnv.getContext("2d");
    sizeAsh();
    if (fxEnabled) ashStop = rafLoop(frameAsh);
  }
  window.addEventListener("resize", sizeAsh);

  /* Toggle the noise/ash/CRT overlays on or off. With FX off the frame loops
     stop entirely (that is the lag savings), the canvases are cleared, and the
     CRT overlay stack is hidden by the body.no-fx CSS rule. */
  function setFxEnabled(on, persist) {
    on = !!on;
    fxEnabled = on;
    if (persist) {
      try { localStorage.setItem("tqg-fx", on ? "on" : "off"); } catch (e) {}
    }
    document.body.classList.toggle("no-fx", !on);
    if (!on) {
      if (noiseStop) { noiseStop(); noiseStop = null; }
      if (ashStop) { ashStop(); ashStop = null; }
      if (noiseCtx) noiseCtx.clearRect(0, 0, noiseCnv.width, noiseCnv.height);
      if (ashCtx) ashCtx.clearRect(0, 0, ashCnv.width, ashCnv.height);
    } else {
      if (!noiseStop && noiseCtx) noiseStop = timerLoop(frameNoise, PERF.noiseMs);
      if (!ashStop && ashCtx) ashStop = rafLoop(frameAsh);
    }
  }

  const SWAY_SELECTORS = [
    ".hero h1", ".hero-sub", ".hero-badge", ".hero-meta span",
    ".nav-brand", ".stat-num", ".section-title", ".session-code",
    ".session-name", ".side-title", ".release-version"
  ];
  // All swaying elements share one phase + one clock, so the whole page
  // breathes in lockstep — a single synchronized wave, not random jitter.
  const SWAY_PHASE = Math.random() * 6.283;
  const SWAY_X_SPEED = 0.8;
  const SWAY_Y_SPEED = 0.65;
  const SWAY_ALPHA_SPEED = 1.1;
  const swayEls = [];
  SWAY_SELECTORS.forEach((sel) => {
    $$(sel).forEach((el) => {
      swayEls.push({
        el,
        ampX: 5 + Math.random() * 4,
        ampY: 3 + Math.random() * 2
      });
    });
  });
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let swayFrame = 0;
  function frameSway(ts) {
    swayFrame++;
    if (PERF.swaySkip > 0 && swayFrame % (PERF.swaySkip + 1) !== 0) {
      return;
    }
    const t = ts / 1000;
    const active = document.body.classList.contains("loaded");
    const xBase = Math.sin(t * SWAY_X_SPEED + SWAY_PHASE);
    const yBase = Math.cos(t * SWAY_Y_SPEED + SWAY_PHASE);
    const pulse = 0.5 + 0.5 * Math.sin(t * SWAY_ALPHA_SPEED + SWAY_PHASE);
    for (let i = 0; i < swayEls.length; i++) {
      const s = swayEls[i];
      if (!active) {
        s.el.style.transform = "";
        continue;
      }
      const x = xBase * s.ampX;
      const y = yBase * s.ampY;
      s.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px)";
      s.el.style.opacity = (0.85 + 0.12 * pulse).toFixed(2);
    }
  }
  if (!reduceMotion) rafLoop(frameSway);

  const isTouch = (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) || (navigator.maxTouchPoints || 0) > 0;
  if (isTouch) document.body.classList.add("touch-device");

  const cursor = $("#cursor");
  if (cursor && window.matchMedia("(pointer: fine)").matches) {
    let mX = innerWidth / 2, mY = innerHeight / 2, eX = mX, eY = mY;
    window.addEventListener("mousemove", (e) => {
      mX = e.clientX; mY = e.clientY;
      cursor.style.transform = "translate(" + mX + "px," + mY + "px) translate(-50%,-50%)";
    });
    const hoverSel = "a, button, .term-opt, input, textarea, select, .session, .stat";
    document.addEventListener("mouseover", (e) => {
      if (e.target.closest(hoverSel)) cursor.classList.add("is-hover");
    });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest(hoverSel)) cursor.classList.remove("is-hover");
    });
    const cursorEcho = document.createElement("div");
    cursorEcho.className = "cursor-echo";
    document.body.appendChild(cursorEcho);
    let echoOn = false, echoTimer = null;
    function cursorTrail() {
      echoOn = true;
      cursorEcho.classList.add("on");
      clearTimeout(echoTimer);
      echoTimer = setTimeout(() => {
        echoOn = false;
        cursorEcho.classList.remove("on");
      }, 2400);
    }
    rafLoop(function echoLoop() {
      eX += (mX - eX) * 0.16;
      eY += (mY - eY) * 0.16;
      if (echoOn) cursorEcho.style.transform = "translate(" + eX.toFixed(1) + "px," + eY.toFixed(1) + "px) translate(-50%,-50%)";
    });
    setInterval(() => {
      if (document.hidden || !echoOn) return;
      if (Math.random() < 0.6) cursorEcho.style.boxShadow = "0 0 16px rgba(255,0,0,.7), 0 0 30px rgba(255,0,0,.35)";
      setTimeout(() => { cursorEcho.style.boxShadow = ""; }, 180);
    }, 700);
    setInterval(() => {
      if (document.hidden || GAME_OVERLAY || safeZone) return;
      if (Math.random() < 0.2) cursorTrail();
    }, 5000);
  }

  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        en.target.classList.add("in");
        io.unobserve(en.target);
      }
    });
  }, { threshold: 0.14 });
  if (!("IntersectionObserver" in window)) {
    $$(".reveal").forEach((el) => el.classList.add("in"));
  } else {
    $$(".reveal").forEach((el) => io.observe(el));
  }

  const staggerIO = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        const kids = Array.prototype.slice.call(en.target.children);
        kids.forEach((k, i) => { k.style.transitionDelay = (i * 90) + "ms"; });
        en.target.classList.add("in");
        setTimeout(() => {
          kids.forEach((k) => { k.style.transitionDelay = ""; });
        }, 1200 + kids.length * 90);
        staggerIO.unobserve(en.target);
      }
    });
  }, { threshold: 0.15 });
  $$("[data-stagger]").forEach((el) => {
    if ("IntersectionObserver" in window) staggerIO.observe(el);
    else el.classList.add("in");
  });

  $$(".session, .platform-card").forEach((el) => {
    el.classList.add("spotlight");
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", (e.clientX - r.left) + "px");
      el.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  /* ---------- Views & navigation ---------- */
  function setPanel(open) {
    document.body.classList.toggle("panel-open", open);
    if (navToggle) navToggle.textContent = open ? "[ CLOSE ]" : "[ NAV ]";
  }

  // Calm pages (story/forum) each get their own theme. The screen collapses to
  // a glowing seam (like a TV off), the theme swaps, then it unfurls from the
  // seam. Style presets pause while a calm theme is up and come back on exit.
  let themeTimer = null;
  let themeSavedStyle = "dark";
  function setThemeMode(theme) {
    const cur = document.body.classList.contains("paper") ? "paper"
      : document.body.classList.contains("forum") ? "forum" : "";
    if (cur === theme) return;
    if (theme) {
      themeSavedStyle = tqgStyle;
      document.body.classList.remove("style-retro", "style-crt", "style-old");
    } else {
      document.body.classList.remove("paper", "forum");
      setStyle(themeSavedStyle || "dark", false);
    }
    const wipe = document.createElement("div");
    wipe.className = "paper-wipe";
    wipe.style.background = THEME_FLASH[theme] || "#040404";
    document.body.appendChild(wipe);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        wipe.classList.add("go");
        wipe.classList.add("flash");
      });
    });
    clearTimeout(themeTimer);
    themeTimer = setTimeout(() => {
      document.body.classList.toggle("paper", theme === "paper");
      document.body.classList.toggle("forum", theme === "forum");
      wipe.classList.remove("go");
      wipe.classList.add("out");
      setTimeout(() => {
        if (wipe.parentNode) wipe.parentNode.removeChild(wipe);
      }, 520);
    }, 480);
  }

  const THEME_FLASH = { paper: "#efe9db", forum: "#f3e9d2" };
  const TQG_STYLES = ["dark", "retro", "crt", "old"];
  let tqgStyle = "dark";
  function setStyle(name, persist) {
    if (TQG_STYLES.indexOf(name) === -1) return false;
    tqgStyle = name;
    if (persist) {
      try { localStorage.setItem("tqg-style", name); } catch (e) {}
    }
    if (document.body.classList.contains("paper") || document.body.classList.contains("forum")) {
      themeSavedStyle = name;
      return true;
    }
    document.body.classList.toggle("style-retro", name === "retro");
    document.body.classList.toggle("style-crt", name === "crt");
    document.body.classList.toggle("style-old", name === "old");
    return true;
  }
  (function initStyle() {
    let saved = "dark";
    try { saved = localStorage.getItem("tqg-style") || "dark"; } catch (e) {}
    setStyle(TQG_STYLES.indexOf(saved) === -1 ? "dark" : saved, false);
  })();

  /* Site-wide theme switch — TERM (auto) / TIMES (paper) / FORUM. When a calm
     theme is pinned here it overrides the per-view calm theme everywhere, so
     the whole site can read as the paper edition or the webring forum. */
  let siteTheme = "";
  const SITE_THEMES = ["", "paper", "forum"];
  function applySiteTheme(name) {
    siteTheme = SITE_THEMES.indexOf(name) === -1 ? "" : name;
    try { localStorage.setItem("tqg-site-theme", siteTheme); } catch (e) {}
    const active = $(".view.active");
    const view = active ? active.dataset.view : "home";
    setThemeMode(siteTheme || CALM_VIEWS[view] || "");
    $$(".theme-btn").forEach((b) => {
      const on = b.getAttribute("data-theme") === siteTheme;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }
  (function initSiteTheme() {
    let saved = "";
    try { saved = localStorage.getItem("tqg-site-theme") || ""; } catch (e) {}
    if (SITE_THEMES.indexOf(saved) === -1) saved = "";
    siteTheme = saved;
    if (saved === "paper" || saved === "forum") {
      themeSavedStyle = tqgStyle;
      document.body.classList.toggle("paper", saved === "paper");
      document.body.classList.toggle("forum", saved === "forum");
      document.body.classList.remove("style-retro", "style-crt", "style-old");
    }
    $$(".theme-btn").forEach((b) => {
      const on = b.getAttribute("data-theme") === siteTheme;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  })();
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#themeSwitch .theme-btn");
    if (!btn) return;
    applySiteTheme(btn.getAttribute("data-theme") || "");
  });

  const CALM_VIEWS = { story: "paper", forum: "forum" };

  function showView(name) {
    safeZone = name === "dev" || CALM_VIEWS[name] !== undefined;
    document.body.classList.toggle("quiet-view", safeZone);
    setThemeMode(siteTheme || CALM_VIEWS[name] || "");
    const target = $('[data-view="' + name + '"]');
    if (!target) return;
    $$(".view.active").forEach((v) => v.classList.remove("active"));
    target.classList.add("active");
    $$(".contents-link, .side-link").forEach((a) => {
      const href = (a.getAttribute("href") || "").replace(/^#/, "");
      a.classList.toggle("active", href === name);
    });
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    setPanel(false);
    kbdTargetName = "";
    $$(".contents-link, .side-link").forEach((a) => a.classList.remove("kb-target"));
    if (name === "forum") setTimeout(forumLoad, 80);
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const id = (a.getAttribute("href") || "").slice(1);
    if (a.hasAttribute("data-merge")) {
      e.preventDefault();
      showView("simpler");
      beginTransit();
      return;
    }
    const el = document.getElementById(id);
    if (el && el.dataset && el.dataset.view) {
      e.preventDefault();
      showView(el.dataset.view);
    }
  });

  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("panel-open")) return;
    if (e.target.closest("#sidePanel, #navToggle")) return;
    setPanel(false);
  });

  // ---------- Game-style keyboard navigation (TAB cycles, ENTER confirms) ----------
  const kbdViews = $$(".view").map((v) => v.dataset.view).filter(Boolean);
  let kbdTargetName = "";
  let logsUnlocked = false;

  function kbdCycleList() {
    return kbdViews.filter((v) => v !== "logs" || logsUnlocked);
  }

  function setKbTarget(name) {
    $$(".contents-link, .side-link").forEach((a) => {
      const href = (a.getAttribute("href") || "").replace(/^#/, "");
      a.classList.toggle("kb-target", href === name);
    });
  }

  function unlockLogs() {
    if (logsUnlocked) return;
    logsUnlocked = true;
    const section = $("#logs");
    if (section) section.classList.remove("locked");
    const lock = $("#logsLock");
    if (lock) lock.classList.add("hidden");
    const grid = $("#logsGrid");
    if (grid) grid.classList.remove("hidden");
    $$(".logs-link").forEach((a) => a.classList.remove("hidden"));
    $$("#logs .reveal").forEach((el) => el.classList.add("in"));
    showToast("LOGS UNLOCKED — YOU TYPED THE CODE QUICKLY ENOUGH");
  }

  const NAV_DIGITS = {
    "1": "home", "2": "about", "3": "sessions", "4": "evidence", "5": "ambience",
    "6": "quotes", "7": "concerns", "8": "transmission", "9": "preview", "0": "download"
  };
  document.addEventListener("keydown", (e) => {
    if (GAME_OVERLAY) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.body.classList.contains("no-scroll")) return;
    if (resolveOpt) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button" || tag === "a" || tag === "summary" || e.target.isContentEditable) return;
    if ($(".modal-overlay:not(.hidden)")) return;
    if (NAV_DIGITS[e.key]) {
      e.preventDefault();
      showView(NAV_DIGITS[e.key]);
      return;
    }
    if (e.key !== "Tab" && e.key !== "Enter") return;
    const list = kbdCycleList();
    if (e.key === "Tab") {
      e.preventDefault();
      let i = list.indexOf(kbdTargetName);
      if (i === -1) {
        const active = document.querySelector(".view.active");
        i = active ? list.indexOf(active.dataset.view) : 0;
        if (i === -1) i = 0;
      }
      i = (i + (e.shiftKey ? -1 : 1) + list.length) % list.length;
      kbdTargetName = list[i];
      setKbTarget(list[i]);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (kbdTargetName) showView(kbdTargetName);
    }
  });

  const navToggle = $("#navToggle");
  if (navToggle) {
    navToggle.addEventListener("click", () => setPanel(!document.body.classList.contains("panel-open")));
  }
  const sidePanel = $("#sidePanel");
  if (sidePanel) {
    sidePanel.addEventListener("click", (e) => {
      if (e.target.closest("a")) setPanel(false);
    });
  }
  document.addEventListener("pointerdown", (e) => {
    if (!document.body.classList.contains("panel-open")) return;
    if (e.target.closest("#sidePanel") || e.target.closest("#navToggle")) return;
    setPanel(false);
  });
  showView("home");

  const tickerTrack = $("#tickerTrack");
  const TICKER_ITEMS = [
    "ARE YOU SITTING COMFORTABLY?",
    "ANSWER TRUTHFULLY",
    "THE ROOM IS GETTING COLDER",
    "DO YOU HEAR THAT SCRATCHING?",
    "THE GAME REMEMBERS. DO YOU?",
    "PLAY WITH HEADPHONES",
    "THERE IS SOMETHING IN THE ROOM WITH YOU",
    "THE QUESTIONS NEVER END"
  ];
  function buildTicker() {
    if (!tickerTrack) return;
    const set = TICKER_ITEMS.map((t) => {
      const s = document.createElement("span");
      s.className = "ticker-item";
      s.textContent = t;
      return s;
    });
    set.forEach((s) => tickerTrack.appendChild(s));
    set.forEach((s) => tickerTrack.appendChild(s.cloneNode(true)));
  }
  buildTicker();

  const SCRIPT = [
    { q: "ARE YOU SITTING COMFORTABLY?", o: ["YES", "NO"], r: ["GOOD. THAT WILL CHANGE.", "THEN STAND. IT WILL NOT HELP."] },
    { q: "ARE YOU ALONE RIGHT NOW?", o: ["YES", "NO"], r: ["WE WILL VERIFY THAT LATER.", "THEN WHO IS IN THE ROOM WITH YOU?"] },
    { q: "DO YOU TRUST WHAT IS ON YOUR SCREEN?", o: ["YES", "NO"], r: ["THAT IS THE FIRST MISTAKE.", "WISE. MOST PEOPLE LIE HERE."] },
    { q: "ARE YOU AFRAID OF THE DARK?", o: ["YES", "NO"], r: ["GOOD. THE DARK REMEMBERS TOO.", "EVERYONE IS. YOU HIDE IT BETTER."] },
    { q: "THE LIGHTS ARE OFF NOW. DO YOU FEEL SAFER?", o: ["YES", "NO"], r: ["THEN THE DARK HAS YOU EXACTLY WHERE IT WANTS YOU.", "GOOD. THE DARK NEVER NEEDED THE LIGHTS."] }
  ];

  const term = $("#term");
  const termLines = $("#termLines");
  const termOptions = $("#termOptions");
  const termStatus = $("#termStatus");

  async function addLine(cls, text, speed, onChar) {
    const line = document.createElement("div");
    line.className = "term-line";
    const body = document.createElement("span");
    if (cls === "term-meta") {
      body.className = "term-meta";
    } else {
      body.className = "term-q";
    }
    line.appendChild(body);
    termLines.appendChild(line);
    await typeNode(body, text, speed || 34, onChar);
    return line;
  }

  function showOptions(opts, activeIndex) {
    termOptions.classList.remove("hidden");
    termOptions.innerHTML = "";
    opts.forEach((o, i) => {
      const b = document.createElement("button");
      b.className = "term-opt" + (i === activeIndex ? " active" : "");
      b.type = "button";
      b.textContent = o;
      b.addEventListener("click", () => selectOption(i));
      termOptions.appendChild(b);
    });
    setActive(activeIndex);
  }

  function setActive(i) {
    $$(".term-opt").forEach((el, idx) => el.classList.toggle("active", idx === i));
  }
  let termBusy = false;
  let resolveOpt = null;

  function selectOption(i) {
    if (!resolveOpt) return;
    const r = resolveOpt;
    resolveOpt = null;
    r(i);
  }

  function promptChoice() {
    return new Promise((res) => { resolveOpt = res; });
  }

  async function runTransmission() {
    if (!term || termBusy) return;
    termBusy = true;
    termStatus.textContent = "RECEIVING FEED";
    const answers = [];
    termLines.innerHTML = "";
    termOptions.classList.add("hidden");

    await addLine("term-meta", "> TRANSMISSION 001 — PREVIEW MODE — ANSWER TRUTHFULLY.", 26);

    for (const step of SCRIPT) {
      await addLine("", "> " + step.q, 40);
      showOptions(step.o, 0);
      let sel = 0;
      const choice = promptChoice();
      const keyHandler = (e) => {
        if (e.key === "Tab") {
          e.preventDefault();
          sel = (sel + 1) % step.o.length;
          setActive(sel);
        } else if (e.key === "Enter") {
          e.preventDefault();
          selectOption(sel);
        } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
          e.preventDefault();
          sel = (sel - 1 + step.o.length) % step.o.length;
          setActive(sel);
        } else if (e.key === "ArrowDown" || e.key === "ArrowRight") {
          e.preventDefault();
          sel = (sel + 1) % step.o.length;
          setActive(sel);
        }
      };
      window.addEventListener("keydown", keyHandler);
      const idx = await choice;
      window.removeEventListener("keydown", keyHandler);
      answers.push(step.o[idx]);
      termOptions.classList.add("hidden");

      const ansLine = document.createElement("div");
      ansLine.className = "term-line";
      ansLine.innerHTML = '<span class="term-q">&gt; </span><span class="term-answer">[ ' + step.o[idx] + " ]</span>";
      termLines.appendChild(ansLine);

      await addLine("", "> " + step.r[idx], 36);
      await sleep(1100);
    }

    termStatus.textContent = "TRANSMISSION END";
    termOptions.classList.add("hidden");
    await addLine("", "> IT HAS WHAT IT NEEDS NOW.", 34);
    await sleep(600);
    giantJumpscare();
    await sleep(1800);
    lightsOn();
    termStatus.textContent = "SESSION LOGGED";
    await addLine("", "THE PREVIEW ENDS HERE. THE FULL SESSION HAS 100 QUESTIONS.", 32);
    await addLine("", "IT HEARS EVERYTHING.", 32);

    const note = document.createElement("div");
    note.className = "term-line";
    note.innerHTML = '<span class="term-answer warn">YOUR ANSWERS HAVE BEEN NOTED: ' + answers.length + "/" + SCRIPT.length + ".</span>";
    termLines.appendChild(note);

    const again = document.createElement("button");
    again.className = "term-opt";
    again.type = "button";
    again.textContent = "[ REPLAY TRANSMISSION ]";
    again.addEventListener("click", () => runTransmission());
    const toDownload = document.createElement("a");
    toDownload.className = "term-opt";
    toDownload.href = "#download";
    toDownload.textContent = "[ CONTINUE TO DOWNLOAD ]";
    termOptions.classList.remove("hidden");
    termOptions.innerHTML = "";
    termOptions.appendChild(again);
    termOptions.appendChild(toDownload);
    termBusy = false;

    setTimeout(() => {
      if (bfStarted) return;
      if (document.hidden) {
        const onVis = () => {
          window.removeEventListener("visibilitychange", onVis);
          if (!bfStarted) bfStart();
        };
        window.addEventListener("visibilitychange", onVis);
        return;
      }
      bfStart();
    }, 900);
  }

  if (term) {
    const termIo = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          runTransmission();
          termIo.disconnect();
        }
      });
    }, { threshold: 0.35 });
    termIo.observe(term);
  }

  function fmtSize(b) {
    if (b > 1048576) return (b / 1048576).toFixed(1) + " MB";
    if (b > 1024) return (b / 1024).toFixed(1) + " KB";
    return b + " B";
  }

  const ASSET_LABELS = [
    [/\.apk$/i, "ANDROID — APK INSTALLER (ARM64)"],
    [/\.zip$/i, "WINDOWS 10/11 — ZIP ARCHIVE"],
    [/\.dmg$/i, "macOS — APP BUNDLE"],
    [/\.tar\.gz$/i, "LINUX — TAR.GZ ARCHIVE"]
  ];

  function setStatus(el, text, miss) {
    el.textContent = text;
    el.classList.toggle("miss", !!miss);
  }

  function pauseAndroid() {
    const btn = $("#dlAndroid");
    const status = $("#dlAndroidStatus");
    if (btn) {
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
      btn.classList.add("platform-miss");
      btn.textContent = "ANDROID — PAUSED";
    }
    if (status) setStatus(status, "ANDROID SUPPORT IS PAUSED DUE TO A FATAL BUG — THE APK CRASHES ON LAUNCH. A FIX IS IN THE WORKS.", true);
  }

  function platformKey() {
    const p = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    if (/android/i.test(p) || /android/i.test(navigator.userAgent || "")) return "android";
    if (/mac|darwin/i.test(p)) return "mac";
    if (/linux|unix|X11/i.test(p)) return "linux";
    if (/win/i.test(p)) return "win";
    return null;
  }

  function wirePlatform(btnId, statusId, asset) {
    if (btnId === "dlAndroid") { pauseAndroid(); return; }
    const btn = $("#" + btnId);
    const status = $("#" + statusId);
    if (asset) {
      let label = asset.name;
      for (const [re, text] of ASSET_LABELS) {
        if (re.test(asset.name)) { label = text; break; }
      }
      btn.href = asset.browser_download_url;
      btn.removeAttribute("aria-disabled");
      btn.classList.remove("platform-miss");
      btn.textContent = "DOWNLOAD " + btn.dataset.os + " ⤓";
      setStatus(status, "READY — " + label + " · " + fmtSize(asset.size));
    } else {
      btn.setAttribute("aria-disabled", "true");
      btn.classList.add("platform-miss");
      btn.textContent = "UNAVAILABLE";
      setStatus(status, btn.dataset.os + " BUILD NOT PUBLISHED YET", true);
    }
  }

  const FALLBACKS = {
    classic: { tag: CLASSIC_TAG, win: "TheQuestionGame.zip", mac: "TheQuestionGame-macOS.dmg", linux: "TheQuestionGame-linux.tar.gz", apk: "TheQuestionGame-Android-1.0-arm64-v8a-debug.apk" },
    remastered: { tag: REMASTER_TAG, win: "TheQuestionGameRemastered.zip", mac: "TheQuestionGameRemastered-macOS.dmg", linux: "TheQuestionGameRemastered-linux.tar.gz" }
  };

  function downloadUrl(tag, file) {
    return "https://github.com/" + REPO + "/releases/download/" + tag + "/" + file;
  }

  function wireLinux(btnId, statusId, asset, fb) {
    if (!$("#" + btnId)) return;
    if (asset) wirePlatform(btnId, statusId, asset);
    else wireFallback(btnId, statusId, "LINUX", downloadUrl(fb.tag, fb.linux));
  }

  function wireFallback(btnId, statusId, os, url) {
    if (btnId === "dlAndroid") { pauseAndroid(); return; }
    const btn = $("#" + btnId);
    const status = $("#" + statusId);
    btn.href = url;
    btn.removeAttribute("aria-disabled");
    btn.classList.remove("platform-miss");
    btn.textContent = "DOWNLOAD " + os + " ⤓";
    setStatus(status, "READY");
  }

  async function loadReleaseFromTag(tag, dom, fb) {
    let wired = false;
    const applyAssets = (assets) => {
      const apk = assets.find((a) => /\.apk$/i.test(a.name));
      const zip = assets.find((a) => /\.zip$/i.test(a.name));
      const dmg = assets.find((a) => /\.dmg$/i.test(a.name));
      const tar = assets.find((a) => /\.tar\.gz$/i.test(a.name));
      if (zip) wirePlatform(dom.winBtn, dom.winStatus, zip);
      else wireFallback(dom.winBtn, dom.winStatus, "WINDOWS", downloadUrl(fb.tag, fb.win));
      if (dmg) wirePlatform(dom.macBtn, dom.macStatus, dmg);
      else wireFallback(dom.macBtn, dom.macStatus, "MACOS", downloadUrl(fb.tag, fb.mac));
      if (dom.linuxBtn) wireLinux(dom.linuxBtn, dom.linuxStatus, tar, fb);
      if (dom.androidBtn) {
        if (apk) {
          wirePlatform(dom.androidBtn, dom.androidStatus, apk);
        } else if (fb.apk) {
          wireFallback(dom.androidBtn, dom.androidStatus, "ANDROID", downloadUrl(fb.tag, fb.apk));
        } else {
          const abtn = $(dom.androidBtn);
          const ast = $(dom.androidStatus);
          if (abtn) {
            abtn.removeAttribute("href");
            abtn.setAttribute("aria-disabled", "true");
            abtn.classList.add("platform-miss");
            abtn.textContent = "APK SOON";
            if (ast) setStatus(ast, "ANDROID BUILD NOT PUBLISHED FOR THIS EDITION", true);
          }
        }
      }
    };
    const tryFetch = async () => {
      try {
        const url = tag
          ? "https://api.github.com/repos/" + REPO + "/releases/tags/" + tag
          : "https://api.github.com/repos/" + REPO + "/releases/latest";
        const res = await fetch(url);
        if (!res.ok) throw new Error("release not found");
        const rel = await res.json();
        if (wired) return;
        wired = true;
        if (dom.relVersion) $(dom.relVersion).textContent = rel.tag_name || tag || "v1.0.0";
        if (dom.relDate) $(dom.relDate).textContent = "RELEASED " + new Date(rel.published_at).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
        applyAssets(rel.assets || []);
      } catch (e) {
        if (wired) return;
        wired = true;
        if (dom.relVersion) $(dom.relVersion).textContent = fb.tag;
        if (dom.relDate) $(dom.relDate).textContent = "RELEASE SERVER UNREACHABLE — USING DIRECT LINK";
        applyAssets([]);
      }
    };
    const fallbackNow = () => {
      if (wired) return;
      wired = true;
      if (dom.relVersion) $(dom.relVersion).textContent = fb.tag;
      if (dom.relDate) $(dom.relDate).textContent = "DIRECT LINK — NO API REQUIRED";
      applyAssets([]);
    };
    tryFetch();
    setTimeout(fallbackNow, 8000);
  }

  async function loadRelease() {
    const os = platformKey();
    if (os === "win" || os === "mac" || os === "linux" || os === "android") {
      const classic = os === "mac" ? ["#macCard", "#macDetected"] : os === "linux" ? ["#linuxCard", "#linuxDetected"] : os === "android" ? ["#androidCard", "#androidDetected"] : ["#winCard", "#winDetected"];
      const rem = os === "mac" ? ["#remMacCard", "#remMacDetected"] : os === "linux" ? ["#remLinuxCard", "#remLinuxDetected"] : os === "android" ? ["#remAndroidCard", "#remAndroidDetected"] : ["#remWinCard", "#remWinDetected"];
      [classic, rem].forEach(([card, tag]) => {
        if (!card) return;
        const c = $(card);
        const t = $(tag);
        if (c) c.classList.add("is-current");
        if (t) t.classList.remove("hidden");
      });
    }
    loadReleaseFromTag(REMASTER_TAG, {
      relVersion: "remRelVersion", relDate: "remRelDate", releaseFallback: "remReleaseFallback",
      winBtn: "dlRemWindows", winStatus: "dlRemWindowsStatus",
      macBtn: "dlRemMac", macStatus: "dlRemMacStatus",
      linuxBtn: "dlRemLinux", linuxStatus: "dlRemLinuxStatus",
      androidBtn: "dlRemAndroid", androidStatus: "dlRemAndroidStatus"
    }, FALLBACKS.remastered);
    (async () => {
      let tag = CLASSIC_TAG;
      try {
        const res = await fetch("https://api.github.com/repos/" + REPO + "/releases");
        if (res.ok) {
          const rels = await res.json();
          const match = (Array.isArray(rels) ? rels : []).find((r) => !/remastered/i.test(r.tag_name || ""));
          if (match && match.tag_name) tag = match.tag_name;
        }
      } catch (e) { }
      loadReleaseFromTag(tag, {
        relVersion: "relVersion", relDate: "relDate", releaseFallback: "releaseFallback",
        winBtn: "dlWindows", winStatus: "dlWindowsStatus",
        macBtn: "dlMac", macStatus: "dlMacStatus",
        linuxBtn: "dlLinux", linuxStatus: "dlLinuxStatus",
        androidBtn: "dlAndroid", androidStatus: "dlAndroidStatus"
      }, FALLBACKS.classic);
    })();
  }
  pauseAndroid();
  loadRelease();

  // ---------- Ambience player ----------
  const ambienceAudio = $("#ambienceAudio");
  const ambiencePlayer = $("#ambiencePlayer");
  const ambienceStatus = $("#ambienceStatus");
  const musicButton = $("#musicButton");
  const musicButtonLabel = $("#musicButtonLabel");

  function ambiencePlaying() {
    const on = !!(ambienceAudio && !ambienceAudio.paused && !ambienceAudio.ended);
    if (ambiencePlayer) ambiencePlayer.classList.toggle("playing", on);
    if (musicButton) musicButton.classList.toggle("playing", on);
    if (musicButtonLabel) musicButtonLabel.textContent = on ? "[ PAUSE ]" : "[ MUSIC ]";
    if (ambienceStatus) ambienceStatus.textContent = on ? "LOOPING — LOGS THEME" : "STANDBY";
    const ambIcon = $("#ambIcon");
    if (ambIcon) ambIcon.classList.toggle("playing", on);
  }

  function toggleMusic() {
    if (!ambienceAudio) return;
    if (ambienceAudio.paused) {
      const p = ambienceAudio.play();
      if (p && p.catch) p.catch(() => {
        if (ambienceStatus) ambienceStatus.textContent = "FEED BLOCKED — ALLOW AUDIO";
        showToast("AUDIO BLOCKED BY THE BROWSER — CLICK [ MUSIC ] AGAIN", true);
      });
    } else {
      ambienceAudio.pause();
    }
  }

  if (musicButton) musicButton.addEventListener("click", toggleMusic);
  if (ambienceAudio) {
    ambienceAudio.addEventListener("play", ambiencePlaying);
    ambienceAudio.addEventListener("pause", ambiencePlaying);
    ambienceAudio.addEventListener("ended", ambiencePlaying);
    ambienceAudio.addEventListener("error", () => {
      if (ambienceStatus) ambienceStatus.textContent = "SOURCE OFFLINE";
    });
  }

  let ambienceWarmed = false;
  function warmAmbience() {
    if (ambienceWarmed || !ambienceAudio) return;
    ambienceWarmed = true;
    const p = ambienceAudio.play();
    if (p && p.catch) p.catch(() => {});
    ambiencePlaying();
  }

  const toast = $("#toast");
  let toastTimer = null;
  function showToast(text, isRed) {
    if (safeZone) return;
    toast.textContent = text;
    toast.classList.toggle("red", !!isRed);
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3800);
  }

  const DISCORD_HANDLE = "neptunetheii";
  const discordBtns = $$(".discord-copy");
  discordBtns.forEach((b) => {
    b.addEventListener("click", (e) => {
      e.preventDefault();
      const done = () => showToast("DISCORD: " + DISCORD_HANDLE + " — COPIED");
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(DISCORD_HANDLE).then(done).catch(done);
      } else {
        const ta = document.createElement("textarea");
        ta.value = DISCORD_HANDLE;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } catch (err) { }
        document.body.removeChild(ta);
        done();
      }
    });
  });

  // ---------- Download warning + install guide ----------
  const warnModal = $("#warnModal");
  const guideModal = $("#guideModal");
  const guideWin = $("#guideWin");
  const guideMac = $("#guideMac");
  const guideAndroid = $("#guideAndroid");
  const tabWin = $("#tabWin");
  const tabMac = $("#tabMac");
  const tabAndroid = $("#tabAndroid");
  let pendingUrl = null;
  let pendingOs = "win";

  function openModal(m) {
    if (!m) return;
    m.classList.remove("hidden");
    document.body.classList.add("modal-open");
  }
  function closeModal(m) {
    if (!m) return;
    m.classList.add("hidden");
    if (!$(".modal-overlay:not(.hidden)")) document.body.classList.remove("modal-open");
  }
  function setGuideTab(os) {
    const win = os === "win";
    const mac = os === "mac";
    const android = os === "android";
    tabWin.setAttribute("aria-selected", win ? "true" : "false");
    tabMac.setAttribute("aria-selected", mac ? "true" : "false");
    if (tabAndroid) tabAndroid.setAttribute("aria-selected", android ? "true" : "false");
    if (guideSecret) guideSecret.classList.add("hidden");
    if (tabSecret) tabSecret.classList.add("hidden");
    guideWin.classList.toggle("hidden", !win);
    guideMac.classList.toggle("hidden", !mac);
    if (guideAndroid) guideAndroid.classList.toggle("hidden", !android);
  }

  const platformBtns = $$(".platform-btn");
  platformBtns.forEach((b) => {
    b.addEventListener("click", (e) => {
      e.preventDefault();
      if (b.id === "dlAndroid") { pauseAndroid(); return; }
      if (b.classList.contains("platform-miss") || !b.getAttribute("href")) return;
      const osAttr = (b.getAttribute("data-os") || "").toLowerCase();
      pendingUrl = b.getAttribute("href");
      pendingOs = osAttr.indexOf("mac") !== -1 ? "mac" : osAttr.indexOf("linux") !== -1 ? "linux" : osAttr.indexOf("android") !== -1 ? "android" : "win";
      openModal(warnModal);
    });
  });

  $("#warnAccept").addEventListener("click", () => {
    closeModal(warnModal);
    if (pendingOs === "linux") {
      if (pendingUrl) window.location.href = pendingUrl;
      return;
    }
    setGuideTab(pendingOs);
    openModal(guideModal);
    if (pendingOs !== "android" && Math.random() < 0.4) setTimeout(secretTab, 1500);
  });
  $("#warnCancel").addEventListener("click", () => closeModal(warnModal));
  $("#warnClose").addEventListener("click", () => closeModal(warnModal));

  $("#guideGo").addEventListener("click", () => {
    closeModal(guideModal);
    if (pendingUrl) window.location.href = pendingUrl;
  });
  $("#guideCancel").addEventListener("click", () => {
    closeModal(guideModal);
    openModal(warnModal);
  });
  $("#guideClose").addEventListener("click", () => closeModal(guideModal));

  tabWin.addEventListener("click", () => setGuideTab("win"));
  tabMac.addEventListener("click", () => setGuideTab("mac"));
  if (tabAndroid) tabAndroid.addEventListener("click", () => setGuideTab("android"));

  const tabSecret = $("#tabSecret");
  const guideSecret = $("#guideSecret");
  let secretTabTimer = null;
  function secretTab() {
    if (!tabSecret || !guideModal || guideModal.classList.contains("hidden")) return;
    if (secretTabTimer) return;
    tabSecret.classList.remove("hidden");
    secretTabTimer = setTimeout(() => {
      tabSecret.classList.add("hidden");
      secretTabTimer = null;
    }, 3400);
  }
  if (tabSecret) {
    tabSecret.addEventListener("click", () => {
      guideSecret.classList.remove("hidden");
      guideWin.classList.add("hidden");
      guideMac.classList.add("hidden");
      if (guideAndroid) guideAndroid.classList.add("hidden");
      tabWin.setAttribute("aria-selected", "false");
      tabMac.setAttribute("aria-selected", "false");
      if (tabAndroid) tabAndroid.setAttribute("aria-selected", "false");
      tabSecret.classList.add("hidden");
      clearTimeout(secretTabTimer);
      secretTabTimer = null;
      pageGlitch();
      showWhisperText("THE SECRET IS THAT YOU CAME BACK.");
    });
  }
  setInterval(() => {
    if (document.hidden || GAME_OVERLAY || safeZone) return;
    if (Math.random() < 0.45) secretTab();
  }, 14000);

  [warnModal, guideModal].forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m) closeModal(m);
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!warnModal.classList.contains("hidden")) closeModal(warnModal);
    else if (!guideModal.classList.contains("hidden")) closeModal(guideModal);
  });

  const sfx = {
    ctx: null,
    ensure() {
      if (!this.ctx) {
        try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { }
      }
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
      return this.ctx;
    },
    type() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "square";
        o.frequency.value = 420 + Math.random() * 600;
        g.gain.setValueAtTime(0.03, ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.035);
        o.connect(g);
        g.connect(ctx.destination);
        o.start();
        o.stop(ctx.currentTime + 0.035);
      } catch (e) { }
    },
    boot() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const osc = (f, ms, vol, type, when, slide) => {
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = type || "square";
          o.frequency.setValueAtTime(f, t + (when || 0));
          if (slide) o.frequency.exponentialRampToValueAtTime(slide, t + (when || 0) + ms / 1000);
          g.gain.setValueAtTime(vol, t + (when || 0));
          g.gain.exponentialRampToValueAtTime(0.0001, t + (when || 0) + ms / 1000);
          o.connect(g);
          g.connect(ctx.destination);
          o.start(t + (when || 0));
          o.stop(t + (when || 0) + ms / 1000 + 0.02);
        };
        osc(70, 90, 0.12, "square", 0);
        osc(55, 120, 0.1, "square", 0.05);
        osc(880, 90, 0.07, "square", 0.5);
        osc(880, 90, 0.07, "square", 0.85);
        const n = Math.floor(ctx.sampleRate * 2.2);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.setValueAtTime(120, t);
        lp.frequency.linearRampToValueAtTime(900, t + 1.6);
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0, t);
        ng.gain.linearRampToValueAtTime(0.06, t + 0.8);
        ng.gain.linearRampToValueAtTime(0.02, t + 2.0);
        src.connect(lp); lp.connect(ng); ng.connect(ctx.destination);
        src.start(t); src.stop(t + 2.2);
        for (let i = 0; i < 8; i++) {
          const dt = 0.8 + Math.random() * 1.4;
          const s = ctx.createBufferSource();
          s.buffer = buf;
          const bp = ctx.createBiquadFilter();
          bp.type = "bandpass";
          bp.frequency.value = 700 + Math.random() * 1400;
          const sg = ctx.createGain();
          sg.gain.value = 0.045;
          s.connect(bp); bp.connect(sg); sg.connect(ctx.destination);
          s.start(t + dt); s.stop(t + dt + 0.03);
        }
      } catch (e) { }
    },
    scare() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const master = ctx.createGain();
        master.gain.setValueAtTime(0.0001, t);
        master.gain.exponentialRampToValueAtTime(0.8, t + 0.02);
        master.gain.setValueAtTime(0.8, t + 0.55);
        master.gain.exponentialRampToValueAtTime(0.0001, t + 1.25);
        master.connect(ctx.destination);

        [1850, 930, 500].forEach((f, i) => {
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "sawtooth";
          o.frequency.setValueAtTime(f, t);
          o.frequency.exponentialRampToValueAtTime(f * 0.3, t + 1.1);
          g.gain.setValueAtTime(0.0001, t);
          g.gain.exponentialRampToValueAtTime(0.2 + i * 0.08, t + 0.03);
          g.gain.exponentialRampToValueAtTime(0.0001, t + 1.1);
          o.connect(g);
          g.connect(master);
          o.start(t);
          o.stop(t + 1.2);
        });

        const n = Math.floor(ctx.sampleRate * 0.9);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0.85, t);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
        src.connect(ng);
        ng.connect(master);
        src.start(t);

        const low = ctx.createOscillator();
        const lg = ctx.createGain();
        low.type = "sine";
        low.frequency.setValueAtTime(90, t);
        low.frequency.exponentialRampToValueAtTime(38, t + 0.7);
        lg.gain.setValueAtTime(0.75, t);
        lg.gain.exponentialRampToValueAtTime(0.0001, t + 0.8);
        low.connect(lg);
        lg.connect(master);
        low.start(t);
        low.stop(t + 0.9);
      } catch (e) { }
    },
    drone() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(120 + Math.random() * 70, t);
        o.frequency.exponentialRampToValueAtTime(45, t + 1.4);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.05, t + 0.15);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 1.5);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 1.6);
      } catch (e) { }
    },
    glitch() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const n = Math.floor(ctx.sampleRate * 0.14);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.14, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
        src.connect(g);
        g.connect(ctx.destination);
        src.start(t);
        const o = ctx.createOscillator();
        const og = ctx.createGain();
        o.type = "square";
        o.frequency.setValueAtTime(300 + Math.random() * 400, t);
        o.frequency.exponentialRampToValueAtTime(70, t + 0.13);
        og.gain.setValueAtTime(0.06, t);
        og.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
        o.connect(og);
        og.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.14);
      } catch (e) { }
    },
    spike() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sawtooth";
        o.frequency.setValueAtTime(1300, t);
        o.frequency.exponentialRampToValueAtTime(120, t + 0.55);
        g.gain.setValueAtTime(0.14, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.62);
      } catch (e) { }
    },
    static() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const dur = 1.1;
        const n = Math.floor(ctx.sampleRate * dur);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.16, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        src.connect(g);
         g.connect(ctx.destination);
        src.start(t);
      } catch (e) { }
    },
    slam() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const master = ctx.createGain();
        master.gain.setValueAtTime(0.0001, t);
        master.gain.exponentialRampToValueAtTime(0.9, t + 0.02);
        master.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
        master.connect(ctx.destination);
        const o1 = ctx.createOscillator();
        o1.type = "square";
        o1.frequency.setValueAtTime(110, t);
        o1.frequency.exponentialRampToValueAtTime(36, t + 0.28);
        o1.connect(master);
        const o2 = ctx.createOscillator();
        o2.type = "sawtooth";
        o2.frequency.setValueAtTime(88, t);
        o2.frequency.exponentialRampToValueAtTime(28, t + 0.3);
        const g2 = ctx.createGain();
        g2.gain.value = 0.5;
        o2.connect(g2);
        g2.connect(master);
        const len = Math.floor(ctx.sampleRate * 0.28);
        const buf = ctx.createBuffer(1, len, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const nf = ctx.createBiquadFilter();
        nf.type = "lowpass";
        nf.frequency.value = 300;
        const ng = ctx.createGain();
        ng.gain.setValueAtTime(0.6, t);
        ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.28);
        src.connect(nf);
        nf.connect(ng);
        ng.connect(master);
        o1.start(t);
        o2.start(t);
        src.start(t);
        o1.stop(t + 0.32);
        o2.stop(t + 0.32);
      } catch (e) { }
    },
    badge() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        [523, 659, 784].forEach((f, i) => {
          const o = ctx.createOscillator();
          o.type = "square";
          o.frequency.value = f;
          const g = ctx.createGain();
          const s = t + i * 0.12;
          g.gain.setValueAtTime(0.0001, s);
          g.gain.exponentialRampToValueAtTime(0.15, s + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, s + 0.3);
          o.connect(g);
          g.connect(ctx.destination);
          o.start(s);
          o.stop(s + 0.32);
        });
      } catch (e) { }
    },
    pew() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "square";
        o.frequency.setValueAtTime(620, t);
        o.frequency.exponentialRampToValueAtTime(1240, t + 0.09);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.09, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.1);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.11);
      } catch (e) { }
    },
    dash() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const n = Math.floor(ctx.sampleRate * 0.18);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const f = ctx.createBiquadFilter();
        f.type = "bandpass";
        f.frequency.setValueAtTime(900, t);
        f.frequency.exponentialRampToValueAtTime(220, t + 0.18);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.16, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
        src.connect(f);
        f.connect(g);
        g.connect(ctx.destination);
        src.start(t);
      } catch (e) { }
    },
    beamCharge() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sawtooth";
        o.frequency.setValueAtTime(160, t);
        o.frequency.exponentialRampToValueAtTime(900, t + 0.75);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.07, t + 0.5);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.8);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.8);
      } catch (e) { }
    },
    beam() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const master = ctx.createGain();
        master.gain.setValueAtTime(0.0001, t);
        master.gain.exponentialRampToValueAtTime(0.5, t + 0.02);
        master.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
        master.connect(ctx.destination);
        const o1 = ctx.createOscillator();
        o1.type = "square";
        o1.frequency.setValueAtTime(1500, t);
        o1.frequency.exponentialRampToValueAtTime(90, t + 0.55);
        o1.connect(master);
        o1.start(t);
        o1.stop(t + 0.6);
        const n = Math.floor(ctx.sampleRate * 0.55);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.25, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.55);
        src.connect(g);
        g.connect(master);
        src.start(t);
      } catch (e) { }
    },
    boltHit() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "square";
        o.frequency.setValueAtTime(880, t);
        o.frequency.exponentialRampToValueAtTime(180, t + 0.1);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.12, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.13);
      } catch (e) { }
    },
    land() {
      const ctx = this.ensure();
      if (!ctx) return;
      try {
        const t = ctx.currentTime;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(130, t);
        o.frequency.exponentialRampToValueAtTime(55, t + 0.07);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.14, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.1);
      } catch (e) { }
    }
  };

  const typeIn = $("#typeIn");
  const aiLog = $("#aiLog");
  const signalSend = $("#signalSend");
  const aiKey = (window.AI_CONFIG && window.AI_CONFIG.groqKey) || "";
  const aiModel = (window.AI_CONFIG && window.AI_CONFIG.model) || "llama-3.3-70b-versatile";
  const AI_SYSTEM = "You are THE QUESTION, the entity from a horror text game. Answer in exactly ONE short sentence. Be eerie and unsettling, but never violent, never threaten the user directly, no gore, no harm. Stay under 180 characters.";
  const AI_FALLBACK = [
    "THE SIGNAL IS STATIC TONIGHT. TRY AGAIN WHEN THE LIGHTS ARE OFF.",
    "I HEARD THAT. I AM NOT SURE I BELIEVE IT.",
    "THE ENTITY IS BUSY ELSEWHERE. IT WILL REMEMBER YOU ASKED.",
    "STATIC. ONLY STATIC. THAT IS ALSO AN ANSWER."
  ];
  let aiBusy = false;

  async function askAI(text) {
    if (!aiKey || aiKey.indexOf("PASTE_") === 0) throw new Error("no key");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15000);
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + aiKey },
        body: JSON.stringify({
          model: aiModel,
          messages: [
            { role: "system", content: AI_SYSTEM },
            { role: "user", content: text }
          ],
          max_tokens: 90,
          temperature: 0.9
        }),
        signal: ctrl.signal
      });
      if (!res.ok) throw new Error("groq " + res.status);
      const data = await res.json();
      const out = ((data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "").trim();
      if (!out) throw new Error("empty");
      return out;
    } finally {
      clearTimeout(timer);
    }
  }

  function aiLine(cls, label, text) {
    const div = document.createElement("div");
    div.className = "ai-line " + cls;
    const lab = document.createElement("span");
    lab.textContent = "> " + label + ": ";
    const body = document.createElement("span");
    body.textContent = text;
    div.appendChild(lab);
    div.appendChild(body);
    aiLog.appendChild(div);
    aiLog.scrollTop = aiLog.scrollHeight;
    return body;
  }

  async function sendSignal() {
    const text = (typeIn ? typeIn.value : "").trim();
    if (!text || aiBusy) return;
    if (typeIn) typeIn.value = "";
    aiBusy = true;
    if (signalSend) { signalSend.disabled = true; signalSend.textContent = "..."; }
    aiLog.classList.remove("hidden");
    aiLine("ai-you", "YOU", text);
    const body = aiLine("ai-it", "IT", "TRANSMITTING...");
    let reply;
    try {
      reply = await askAI(text);
    } catch (err) {
      reply = AI_FALLBACK[Math.floor(Math.random() * AI_FALLBACK.length)];
    }
    body.textContent = "";
    typeNode(body, reply, 24);
    aiBusy = false;
    if (signalSend) { signalSend.disabled = false; signalSend.textContent = "SEND"; }
  }

  if (typeIn && signalSend) {
    signalSend.addEventListener("click", sendSignal);
    typeIn.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendSignal();
      }
    });
    const signalBox = typeIn.closest(".signal-box");
    if (signalBox) {
      typeIn.addEventListener("focus", () => signalBox.classList.add("focused"));
      typeIn.addEventListener("blur", () => signalBox.classList.remove("focused"));
    }
    typeIn.addEventListener("focus", () => stopGhost(true));
    typeIn.addEventListener("input", () => stopGhost(false));
    typeIn.addEventListener("input", () => {
      if (aiBusy || !typeIn || !typeIn.value.trim()) return;
      if (Math.random() < 0.03) {
        const v = typeIn.value;
        const last = v.charAt(v.length - 1);
        if (last && /\S/.test(last)) {
          typeIn.value = v + last;
        } else {
          typeIn.value = v.slice(0, -1) + ["▚", "◈", "▓", "×"][Math.floor(Math.random() * 4)];
        }
      }
    });
  }

  const scare = $("#scare");
  const FACE_HTML = '<div class="face"><div class="face-eyes"><span></span><span></span></div><div class="face-mouth"></div><div class="face-text">IT SEES YOU</div></div>';

  function giantJumpscare() {
    if (scareLock) return;
    scareLock = true;
    const mainEl = document.querySelector("main");
    const saved = scare ? scare.innerHTML : null;
    if (scare) {
      scare.innerHTML = FACE_HTML;
      scare.classList.add("giant", "go");
    }
    if (mainEl) mainEl.classList.add("shake");
    if (document.body) document.body.classList.add("body-shake");
    sfx.scare();
    let n = 0;
    const pulse = () => {
      flash.classList.add("go");
      setTimeout(() => {
        flash.classList.remove("go");
        n++;
        if (n < 6) {
          setTimeout(pulse, 100);
        }
      }, 160);
    };
    pulse();
    setTimeout(() => {
      if (scare) {
        scare.classList.remove("go", "giant");
        if (saved !== null) scare.innerHTML = saved;
      }
      if (mainEl) mainEl.classList.remove("shake");
      if (document.body) document.body.classList.remove("body-shake");
      scareLock = false;
    }, 1650);
  }

  function jumpscare() {
    if (scareLock) return;
    scareLock = true;
    const mainEl = document.querySelector("main");
    if (mainEl) mainEl.classList.add("shake");
    if (scare) scare.classList.add("go");
    let n = 0;
    const pulse = () => {
      flash.classList.add("go");
      setTimeout(() => {
        flash.classList.remove("go");
        n++;
        if (n < 4) {
          setTimeout(pulse, 110);
        } else {
          if (scare) scare.classList.remove("go");
          if (mainEl) mainEl.classList.remove("shake");
          scareLock = false;
        }
      }, 150);
    };
    pulse();
  }
  let scareLock = false;

  const PHRASES = {
    "who are you": "WE ARE A SET OF QUESTIONS.",
    "are you there": "WE ARE ALWAYS HERE.",
    "exit": "ESCAPING IS NOT AS EASY AS YOU THINK.",
    "help": "NO HELP FOR YOU.",
    "truth": "THE TRUTH WAS ALWAYS THE POINT.",
    "lie": "LYING IS NOTED. IT ALWAYS IS.",
    "game": "THE GAME REMEMBERS. DO YOU?"
  };

  function triggerEasterEgg(word) {
    const w = String(word).toLowerCase();
    if (w === "hello") {
      if (typeIn) typeIn.value = "";
      jumpscare();
      return;
    }
    if (w === "smile") {
      if (typeIn) typeIn.value = "";
      gifScare();
      return;
    }
    if (w === "2013") {
      unlockLogs();
      return;
    }
    if (PHRASES[w]) {
      showToast(PHRASES[w], w === "exit" || w === "lie");
      return;
    }
  }

  const QUICK_SIGNALS = ["hello", "smile", "2013", "who are you", "are you there", "exit", "help", "truth", "lie", "game"];
  const signalKeys = $("#signalKeys");
  if (signalKeys) {
    QUICK_SIGNALS.forEach((w) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "signal-key";
      b.textContent = w.toUpperCase();
      b.setAttribute("aria-label", "Send signal: " + w);
      b.addEventListener("click", () => triggerEasterEgg(w));
      signalKeys.appendChild(b);
    });
  }

  let keyBuf = "";
  let keyTimer = null;

  function handleTypeKey(e, key) {
    sfx.type();
    keyBuf = (keyBuf + key.toLowerCase()).slice(-24);
    clearTimeout(keyTimer);
    keyTimer = setTimeout(() => { keyBuf = ""; }, 2500);
    if (!safeZone) {
      if (keyBuf.endsWith("hello")) {
        keyBuf = "";
        if (typeIn) typeIn.value = "";
        jumpscare();
        return;
      }
      if (keyBuf.endsWith("smile")) {
        keyBuf = "";
        if (typeIn) typeIn.value = "";
        gifScare();
        return;
      }
    }
    if (keyBuf.endsWith("2013")) {
      keyBuf = "";
      unlockLogs();
      return;
    }
    for (const phrase in PHRASES) {
      if (keyBuf.endsWith(phrase)) {
        showToast(PHRASES[phrase], phrase === "exit" || phrase === "lie");
        keyBuf = "";
        break;
      }
    }
  }

  document.addEventListener("keydown", (e) => {
    if (GAME_OVERLAY) return;
    const tag = (e.target.tagName || "").toLowerCase();
    const inSignal = typeIn && e.target === typeIn;
    if (!inSignal && (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Enter") {
      keyBuf = "";
      if (inSignal) typeIn.blur();
      return;
    }
    if (e.key.toLowerCase() === "m" && !inSignal) {
      toggleMusic();
      return;
    }
    if (e.key.length === 1) {
      handleTypeKey(e, e.key);
    }
  });

  // ---------- BOSSFIGHT STAGE 1/8 ----------
  const bfEl = $("#bossfight");
  const bfArena = $("#bfArena");
  const bfPlayerEl = $("#bfPlayer");
  const bfPistonEl = $("#bfPiston");
  const bfTeethEl = $("#bfTeeth");
  const bfSpikesEl = $("#bfSpikes");
  const bfTimerEl = $("#bfTimer");
  const bfFaceEl = $("#bfFace");
  const bfBadgeEl = $("#bfBadge");
  const bfFlashEl = $("#bfFlash");
  const bfMsgEl = $("#bfMsg");
  const bfAudioEl = $("#bfAudio");
  const bfLeftBtn = $("#bfLeft");
  const bfRightBtn = $("#bfRight");
  const bfCrouchBtn = $("#bfCrouch");
  const bfDashBtn = $("#bfDash");
  const bfFireBtn = $("#bfFire");

  const BF = {
    active: false, won: false, over: false,
    W: 0, H: 0, floorY: 0,
    tLeft: 30, last: 0, acc: 0, raf: 0,
    pw: 26, phStand: 36, phCrouch: 16,
    px: 0, py: 0, vy: 0, crouch: false, grounded: true, invuln: 0, jumpHeld: false,
    keys: { left: false, right: false, crouch: false, jump: false },
    piston: { x: 0, y: 0, w: 0, h: 62, dir: 1, minX: 0, maxX: 0, speed: 0,
              slamTimer: 0, slamInterval: 2.6, slamPhase: 0, slamming: false, slammed: false },
    spikes: { floor: [], ceil: [] },
    badge: { x: 0, y: 0, taken: false },
    facing: 1,
    shots: [],
    bolts: [],
    particles: [],
    beam: { state: "idle", x: 0, t: 0, warnEl: null, beamEl: null },
    dash: { on: false, t: 0, cd: 0, dir: 0 },
    bossT: 0, nextBeam: 0, nextBolt: 0,
    fireCd: 0, ghostAcc: 0, ghosts: 0
  };
  let bfStarted = false;
  const easeInOut = (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

  function bfClearSpikes() {
    bfSpikesEl.innerHTML = "";
    BF.spikes.floor = [];
    BF.spikes.ceil = [];
  }
  function bfAddSpike(which, x, h, w) {
    const s = document.createElement("div");
    s.className = "bf-spike " + which;
    s.style.left = x + "px";
    const hw = (w || 14) / 2;
    if (which === "f") {
      s.style.borderLeftWidth = hw + "px";
      s.style.borderRightWidth = hw + "px";
      s.style.borderBottomWidth = h + "px";
      s.style.bottom = "0px";
    } else {
      s.style.borderLeftWidth = hw + "px";
      s.style.borderRightWidth = hw + "px";
      s.style.borderTopWidth = h + "px";
      s.style.top = "0px";
    }
    bfSpikesEl.appendChild(s);
    const spikeKey = which === "c" ? "ceil" : "floor";
    BF.spikes[spikeKey].push({ x, h, w: w || 14, el: s });
  }
  function bfAddSpikeCluster(which, cx, h, width, n) {
    const spread = width / (n + 1);
    for (let i = 0; i < n; i++) {
      const x = cx - width / 2 + spread * (i + 1) - 14;
      bfAddSpike(which, x, Math.round(h * (0.72 + 0.14 * (i % 3))), 20 + 8 * (i % 2));
    }
  }
  function bfLayout() {
    BF.W = window.innerWidth;
    BF.H = window.innerHeight;
    BF.floorY = BF.H - 86;
    const pw = BF.piston;
    pw.w = Math.max(180, Math.min(330, Math.round(BF.W * 0.34)));
    pw.h = 62;
    pw.minX = Math.round(BF.W * 0.33);
    pw.maxX = BF.W - pw.w - Math.round(BF.W * 0.33);
    if (pw.maxX < pw.minX) pw.maxX = pw.minX;
    pw.speed = BF.W * 0.22;
    if (pw.x < pw.minX) pw.x = pw.minX;
    if (pw.x > pw.maxX) pw.x = pw.maxX;
    bfPistonEl.style.width = pw.w + "px";
    bfPistonEl.style.height = pw.h + "px";
    bfTeethEl.innerHTML = "";
    const teeth = Math.floor(pw.w / 18);
    for (let i = 0; i < teeth; i++) {
      const t = document.createElement("div");
      t.className = "bf-tooth";
      t.style.left = (i * 18 + 2) + "px";
      bfTeethEl.appendChild(t);
    }
    bfClearSpikes();
    [0.27, 0.5, 0.73].forEach((fx) => bfAddSpikeCluster("f", Math.round(BF.W * fx), 32, 90, 4));
    [0.27, 0.73].forEach((fx) => bfAddSpikeCluster("c", Math.round(BF.W * fx), Math.max(90, BF.floorY - 170), 90, 4));
  }

  function bfResetPlayer(death) {
    BF.px = 24;
    BF.py = BF.floorY - BF.phStand;
    BF.vy = 0;
    BF.crouch = false;
    BF.grounded = true;
    BF.jumpHeld = false;
    BF.facing = 1;
    BF.dash.on = false;
    bfPlayerEl.classList.remove("crouch", "invuln", "running", "flip", "jump", "land", "dash", "dash-glow");
    if (death) {
      BF.invuln = 1.4;
      bfPlayerEl.classList.add("invuln");
      bfSpawnBurst(BF.px + BF.pw / 2, BF.py + 18, true);
      bfFlashEl.classList.add("go");
      setTimeout(() => bfFlashEl.classList.remove("go"), 320);
    }
  }
  function bfDie() {
    if (BF.invuln > 0 || BF.won || BF.over) return;
    bfResetPlayer(true);
    sfx.glitch();
  }

  function bfSlamImpact() {
    if (document.hidden) return;
    bfArena.classList.add("bf-shake");
    setTimeout(() => bfArena.classList.remove("bf-shake"), 260);
    sfx.slam();
  }

  function bfSpawnPx(x, y, cls, vx, vy, life) {
    if (BF.particles.length >= 60) {
      const old = BF.particles.shift();
      if (old.el && old.el.parentNode) old.el.parentNode.removeChild(old.el);
    }
    const el = document.createElement("div");
    el.className = "bf-px " + cls;
    el.style.left = x + "px";
    el.style.top = y + "px";
    bfArena.appendChild(el);
    BF.particles.push({ x, y, vx, vy, life, max: life, el, cls });
  }
  function bfUpdateParticles(dt) {
    for (let i = BF.particles.length - 1; i >= 0; i--) {
      const p = BF.particles[i];
      p.life -= dt;
      if (p.life <= 0) {
        if (p.el.parentNode) p.el.parentNode.removeChild(p.el);
        BF.particles.splice(i, 1);
        continue;
      }
      p.vy += 520 * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.el.style.left = p.x.toFixed(1) + "px";
      p.el.style.top = p.y.toFixed(1) + "px";
      p.el.style.opacity = String(Math.max(0, p.life / p.max));
    }
  }
  function bfSpawnDust(x, y) {
    for (let i = 0; i < 4; i++) {
      bfSpawnPx(x + (Math.random() * 16 - 8), y - 2, "", (Math.random() * 120 - 60), -80 - Math.random() * 70, 0.32 + Math.random() * 0.2);
    }
  }
  function bfSpawnBurst(x, y, red) {
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2 + Math.random() * 0.5;
      const sp = 90 + Math.random() * 130;
      bfSpawnPx(x, y, red ? "red" : "green", Math.cos(a) * sp, Math.sin(a) * sp, 0.4 + Math.random() * 0.25);
    }
  }
  function bfSpawnGhost() {
    if (BF.ghosts >= 12) return;
    BF.ghosts++;
    const el = document.createElement("div");
    el.className = "bf-ghost";
    el.style.left = BF.px + "px";
    el.style.top = BF.py + "px";
    bfArena.appendChild(el);
    setTimeout(() => {
      BF.ghosts--;
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 320);
  }

  function bfTryDash() {
    if (!BF.active || BF.over || BF.won) return;
    if (BF.dash.on || BF.dash.cd > 0) return;
    BF.dash.on = true;
    BF.dash.t = 0.26;
    BF.dash.dir = BF.facing;
    BF.invuln = Math.max(BF.invuln, 0.3);
    bfPlayerEl.classList.add("dash", "dash-glow");
    sfx.dash();
  }
  function bfTryFire() {
    if (!BF.active || BF.over || BF.won) return;
    if (BF.fireCd > 0 || BF.shots.length >= 4) return;
    BF.fireCd = 0.32;
    const sx = BF.facing > 0 ? BF.px + BF.pw + 4 : BF.px - 14;
    const sy = BF.py + (BF.crouch ? BF.phCrouch : BF.phStand) * 0.55;
    const el = document.createElement("div");
    el.className = "bf-shot";
    el.textContent = "?";
    el.style.left = sx + "px";
    el.style.top = sy + "px";
    bfArena.appendChild(el);
    BF.shots.push({ x: sx, y: sy, vx: BF.facing * 560, life: 0.9, el });
    sfx.pew();
  }
  function bfUpdateShots(dt) {
    for (let i = BF.shots.length - 1; i >= 0; i--) {
      const s = BF.shots[i];
      s.life -= dt;
      s.x += s.vx * dt;
      if (s.life <= 0 || s.x < -20 || s.x > BF.W + 20) {
        if (s.el.parentNode) s.el.parentNode.removeChild(s.el);
        BF.shots.splice(i, 1);
        continue;
      }
      s.el.style.left = s.x.toFixed(1) + "px";
      s.el.style.top = s.y.toFixed(1) + "px";
      for (let j = BF.bolts.length - 1; j >= 0; j--) {
        const b = BF.bolts[j];
        if (b.delay > 0) continue;
        if (s.x > b.x - 10 && s.x < b.x + 12 && s.y > b.y - 10 && s.y < b.y + 12) {
          bfSpawnBurst(b.x, b.y, true);
          sfx.boltHit();
          if (s.el.parentNode) s.el.parentNode.removeChild(s.el);
          BF.shots.splice(i, 1);
          if (b.el.parentNode) b.el.parentNode.removeChild(b.el);
          BF.bolts.splice(j, 1);
          break;
        }
      }
    }
  }

  function bfSprayBolts() {
    const cx = BF.W / 2;
    const cy = 90;
    const tx = BF.px + BF.pw / 2;
    const ty = BF.py + 18;
    const n = 3 + (BF.tLeft <= 12 ? 2 : 0);
    bfMsgEl.textContent = "IT SPITS.";
    bfMsgEl.classList.add("show");
    bfFaceEl.classList.add("attacking");
    setTimeout(() => {
      bfMsgEl.classList.remove("show");
      bfFaceEl.classList.remove("attacking");
    }, 1100);
    for (let i = 0; i < n; i++) {
      const off = (i - (n - 1) / 2) * 80;
      const dx = tx + off - cx;
      const dy = ty - cy;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const sp = 250 + Math.random() * 60;
      bfAddBolt(cx + Math.random() * 30 - 15, cy, (dx / dist) * sp, (dy / dist) * sp + 40, 0.16 + i * 0.09);
    }
  }
  function bfAddBolt(x, y, vx, vy, delay) {
    if (BF.bolts.length >= 6) return;
    const el = document.createElement("div");
    el.className = "bf-bolt";
    el.style.left = x + "px";
    el.style.top = y + "px";
    bfArena.appendChild(el);
    BF.bolts.push({ x, y, vx, vy, delay, el });
  }
  function bfUpdateBolts(dt) {
    for (let i = BF.bolts.length - 1; i >= 0; i--) {
      const b = BF.bolts[i];
      if (b.delay > 0) { b.delay -= dt; continue; }
      b.vy += 240 * dt;
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      if (b.y >= BF.floorY - 8) {
        b.y = BF.floorY - 8;
        bfSpawnBurst(b.x, b.y, true);
        if (b.el.parentNode) b.el.parentNode.removeChild(b.el);
        BF.bolts.splice(i, 1);
        continue;
      }
      b.el.style.left = b.x.toFixed(1) + "px";
      b.el.style.top = b.y.toFixed(1) + "px";
      const phh = BF.crouch ? BF.phCrouch : BF.phStand;
      if (BF.invuln <= 0 && b.x + 12 > BF.px && b.x < BF.px + BF.pw &&
          b.y + 12 > BF.py && b.y < BF.py + phh) {
        bfSpawnBurst(b.x, b.y, true);
        if (b.el.parentNode) b.el.parentNode.removeChild(b.el);
        BF.bolts.splice(i, 1);
        bfDie();
        continue;
      }
    }
  }

  function bfStartBeam() {
    BF.beam.state = "telegraph";
    BF.beam.t = 0;
    BF.beam.x = BF.px + BF.pw / 2;
    const warn = document.createElement("div");
    warn.className = "bf-beam-warn";
    warn.style.left = (BF.beam.x - 3) + "px";
    bfArena.appendChild(warn);
    BF.beam.warnEl = warn;
    bfFaceEl.classList.add("attacking");
    bfMsgEl.textContent = "IT GAZES.";
    bfMsgEl.classList.add("show");
    sfx.beamCharge();
  }
  function bfUpdateBeam(dt) {
    const bm = BF.beam;
    bm.t += dt;
    if (bm.state === "telegraph" && bm.t >= 0.85) {
      bm.state = "active";
      bm.t = 0;
      if (bm.warnEl && bm.warnEl.parentNode) bm.warnEl.parentNode.removeChild(bm.warnEl);
      bm.warnEl = null;
      const beam = document.createElement("div");
      beam.className = "bf-beam";
      beam.style.left = (bm.x - 45) + "px";
      beam.style.width = "90px";
      bfArena.appendChild(beam);
      bm.beamEl = beam;
      sfx.beam();
      if (Math.abs(BF.px + BF.pw / 2 - bm.x) < 45 && BF.invuln <= 0 && !BF.won) {
        bfDie();
      }
    } else if (bm.state === "active" && bm.t >= 0.6) {
      bfClearBeam();
    }
  }
  function bfClearBeam() {
    const bm = BF.beam;
    if (bm.warnEl && bm.warnEl.parentNode) bm.warnEl.parentNode.removeChild(bm.warnEl);
    if (bm.beamEl && bm.beamEl.parentNode) bm.beamEl.parentNode.removeChild(bm.beamEl);
    bm.warnEl = null;
    bm.beamEl = null;
    bm.state = "idle";
    bm.t = 0;
    bfFaceEl.classList.remove("attacking");
    bfMsgEl.classList.remove("show");
    BF.nextBeam = BF.bossT + 6.5 + Math.random() * 3;
  }
  function bfClearFx() {
    bfClearBeam();
    for (const s of BF.shots) if (s.el && s.el.parentNode) s.el.parentNode.removeChild(s.el);
    BF.shots.length = 0;
    for (const b of BF.bolts) if (b.el && b.el.parentNode) b.el.parentNode.removeChild(b.el);
    BF.bolts.length = 0;
    for (const p of BF.particles) if (p.el && p.el.parentNode) p.el.parentNode.removeChild(p.el);
    BF.particles.length = 0;
    BF.dash.on = false;
    BF.fireCd = 0;
    BF.bossT = 0;
    bfPlayerEl.classList.remove("dash", "dash-glow", "running", "flip", "jump", "land");
  }

  function bfLoop(ts) {
    if (!BF.active) return;
    const dt = Math.min(0.05, (ts - BF.last) / 1000);
    BF.last = ts;
    if (BF.over) { BF.raf = requestAnimationFrame(bfLoop); return; }

    if (!BF.won) {
      BF.acc += dt;
      if (BF.acc >= 1) {
        const step = Math.floor(BF.acc);
        BF.acc -= step;
        BF.tLeft -= step;
        if (BF.tLeft < 0) BF.tLeft = 0;
        bfTimerEl.textContent = String(BF.tLeft);
        bfTimerEl.classList.toggle("warn", BF.tLeft <= 10);
        if (BF.tLeft === 0) { bfWin(); }
      }
    }

    let move = 0;
    if (BF.keys.left) move -= 1;
    if (BF.keys.right) move += 1;
    BF.crouch = BF.keys.crouch;

    const wasGrounded = BF.grounded;
    const wasVy = BF.vy;

    if (BF.keys.jump && BF.grounded && !BF.jumpHeld) {
      BF.vy = -400;
      BF.grounded = false;
      BF.jumpHeld = true;
      sfx.type();
    }
    if (!BF.keys.jump) BF.jumpHeld = false;

    if (BF.dash.on) {
      BF.dash.t -= dt;
      BF.px += BF.dash.dir * 830 * dt;
      BF.ghostAcc += dt;
      if (BF.ghostAcc >= 0.045) {
        BF.ghostAcc = 0;
        bfSpawnGhost();
      }
      if (BF.dash.t <= 0) {
        BF.dash.on = false;
        bfPlayerEl.classList.remove("dash", "dash-glow");
        BF.dash.cd = 1.4;
      }
    } else {
      BF.px += move * 260 * dt;
      if (BF.dash.cd > 0) BF.dash.cd = Math.max(0, BF.dash.cd - dt);
    }
    BF.px = Math.max(0, Math.min(BF.W - BF.pw, BF.px));
    if (move !== 0) BF.facing = move < 0 ? -1 : 1;

    let g = 900;
    if (BF.jumpHeld && BF.vy < 0) g *= 0.6;
    BF.vy += g * dt;
    BF.py += BF.vy * dt;
    const ph = BF.crouch ? BF.phCrouch : BF.phStand;
    if (BF.py >= BF.floorY - ph) {
      BF.py = BF.floorY - ph;
      BF.vy = 0;
      BF.grounded = true;
    } else {
      BF.grounded = false;
    }

    if (!wasGrounded && BF.grounded && wasVy > 320) {
      bfSpawnDust(BF.px + BF.pw / 2, BF.floorY);
      bfPlayerEl.classList.add("land");
      setTimeout(() => bfPlayerEl.classList.remove("land"), 120);
      sfx.land();
    }

    bfPlayerEl.classList.toggle("crouch", BF.crouch);
    bfPlayerEl.classList.toggle("running", BF.grounded && (BF.keys.left || BF.keys.right));
    bfPlayerEl.classList.toggle("flip", BF.facing < 0);
    bfPlayerEl.classList.toggle("jump", !BF.grounded && BF.vy < 0);
    bfPlayerEl.style.transform = "translate(" + BF.px.toFixed(1) + "px," + BF.py.toFixed(1) + "px)";

    if (BF.fireCd > 0) BF.fireCd = Math.max(0, BF.fireCd - dt);

    if (BF.invuln > 0) {
      BF.invuln -= dt;
      if (BF.invuln <= 0) bfPlayerEl.classList.remove("invuln");
    }

    const pw = BF.piston;
    if (!BF.won) {
      if (!pw.slamming) {
        pw.x += pw.dir * pw.speed * dt;
        if (pw.x <= pw.minX) { pw.x = pw.minX; pw.dir = 1; }
        if (pw.x >= pw.maxX) { pw.x = pw.maxX; pw.dir = -1; }
        pw.slamTimer += dt;
        if (pw.slamTimer >= pw.slamInterval) {
          pw.slamTimer = 0;
          pw.slamming = true;
          pw.slamPhase = 0;
        }
      } else {
        pw.slamPhase += dt;
        const p = pw.slamPhase;
        if (p < 0.35) {
          pw.y = easeInOut(Math.min(1, p / 0.35)) * (BF.floorY - 18 - pw.h);
          bfPistonEl.classList.add("warn");
          bfPistonEl.classList.remove("slamming");
        } else if (p < 0.9) {
          pw.y = BF.floorY - 18 - pw.h;
          bfPistonEl.classList.remove("warn");
          bfPistonEl.classList.add("slamming");
          if (!pw.slammed) { pw.slammed = true; bfSlamImpact(); }
        } else if (p < 1.5) {
          pw.y = (1 - easeInOut(Math.min(1, (p - 0.9) / 0.6))) * (BF.floorY - 18 - pw.h);
          bfPistonEl.classList.add("warn");
          bfPistonEl.classList.remove("slamming");
        } else {
          pw.y = 0;
          pw.slamming = false;
          pw.slammed = false;
          bfPistonEl.classList.remove("warn", "slamming");
        }
      }
    } else {
      pw.y = 0;
      pw.slamming = false;
      pw.slammed = false;
      bfPistonEl.classList.remove("warn", "slamming");
    }
    bfPistonEl.style.transform = "translate(" + pw.x.toFixed(1) + "px," + pw.y.toFixed(1) + "px)";

    if (!BF.won) {
      BF.bossT += dt;
      if (BF.beam.state === "idle" && BF.bossT >= BF.nextBeam) bfStartBeam();
      if (BF.beam.state !== "idle") bfUpdateBeam(dt);
      if (BF.bossT >= BF.nextBolt && BF.bolts.length < 5 && BF.beam.state === "idle") {
        BF.nextBolt = BF.bossT + 6 + Math.random() * 4;
        bfSprayBolts();
      }
      bfUpdateBolts(dt);
    } else {
      if (BF.beam.state !== "idle") bfClearBeam();
      for (const b of BF.bolts) if (b.el && b.el.parentNode) b.el.parentNode.removeChild(b.el);
      BF.bolts.length = 0;
    }
    bfUpdateShots(dt);
    bfUpdateParticles(dt);

    if (!BF.won) {
      const pistonBottom = pw.y + pw.h;
      const playerTop = BF.py;
      if (pistonBottom > playerTop &&
          BF.px < pw.x + pw.w - 6 && BF.px + BF.pw > pw.x + 6) {
        if (!BF.crouch) bfDie();
      }
      for (const s of BF.spikes.floor) {
        if (BF.py + ph > BF.floorY - s.h &&
            BF.px + BF.pw > s.x && BF.px < s.x + s.w) {
          bfDie();
        }
      }
      for (const s of BF.spikes.ceil) {
        if (BF.py < s.h &&
            BF.px + BF.pw > s.x && BF.px < s.x + s.w) {
          bfDie();
        }
      }
    }

    if (BF.won && !BF.badge.taken) {
      if (BF.badge.y < BF.floorY - 46) {
        BF.badge.y += 700 * dt;
        if (BF.badge.y >= BF.floorY - 46) BF.badge.y = BF.floorY - 46;
        bfBadgeEl.style.top = BF.badge.y + "px";
      } else if (BF.px < BF.badge.x + 46 && BF.px + BF.pw > BF.badge.x &&
                 BF.py + ph >= BF.floorY - 50) {
        BF.badge.taken = true;
        bfCollectBadge();
      }
    }

    BF.raf = requestAnimationFrame(bfLoop);
  }

  function bfWin() {
    BF.won = true;
    if (BF.beam.state !== "idle") bfClearBeam();
    for (const b of BF.bolts) if (b.el && b.el.parentNode) b.el.parentNode.removeChild(b.el);
    BF.bolts.length = 0;
    bfPlayerEl.classList.remove("dash", "dash-glow");
    BF.dash.on = false;
    bfTimerEl.textContent = "0";
    BF.badge.x = Math.max(0, Math.min(BF.W - 46, BF.px + BF.pw / 2 - 23));
    BF.badge.y = 0;
    bfBadgeEl.style.left = BF.badge.x + "px";
    bfBadgeEl.style.top = "0px";
    bfBadgeEl.classList.add("show");
    bfMsgEl.textContent = "THE PISTON STILLS. TAKE IT.";
    bfMsgEl.classList.add("show");
  }

  async function bfCollectBadge() {
    bfBadgeEl.classList.remove("show");
    bfMsgEl.textContent = "BADGE 1/8 COLLECTED.";
    sfx.badge();
    bfFaceEl.classList.add("gone");
    if (bfAudioEl) bfAudioEl.pause();
    try {
      document.cookie = "tq_boss1=defeated; path=/; SameSite=Lax; max-age=31536000";
    } catch (e) { }
    await sleep(2600);
    bfEnd();
  }

  function bfEnd() {
    BF.active = false;
    BF.over = true;
    cancelAnimationFrame(BF.raf);
    bfClearFx();
    bfEl.classList.remove("go");
    document.body.classList.remove("modal-open");
    GAME_OVERLAY = false;
    bfFaceEl.classList.remove("gone");
    bfMsgEl.classList.remove("show");
    bfMsgEl.textContent = "";
    bfTimerEl.textContent = "120";
    bfTimerEl.classList.remove("warn");
    bfPlayerEl.classList.remove("crouch", "invuln");
    bfBadgeEl.classList.remove("show");
    bfPistonEl.classList.remove("warn", "slamming");
    BF.won = false;
    BF.tLeft = 120;
    BF.acc = 0;
    bfStarted = false;
    BF.piston.y = 0;
    bfPistonEl.style.transform = "translate(0px,0px)";
    bfPlayerEl.style.transform = "";
  }

  function bfStart() {
    if (bfStarted || !bfEl || !bfArena) return;
    bfStarted = true;
    GAME_OVERLAY = true;
    bfClearFx();
    bfLayout();
    bfResetPlayer(false);
    BF.active = true;
    BF.over = false;
    BF.won = false;
    BF.tLeft = 120;
    BF.acc = 0;
    BF.badge.taken = false;
    BF.keys.left = BF.keys.right = BF.keys.crouch = BF.keys.jump = false;
    BF.dash.on = false;
    BF.dash.cd = 0;
    BF.fireCd = 0;
    BF.nextBeam = 3.5;
    BF.nextBolt = 4.5 + Math.random() * 2;
    bfTimerEl.textContent = "120";
    bfEl.classList.add("go");
    document.body.classList.add("modal-open");
    if (bfAudioEl) {
      const p = bfAudioEl.play();
      if (p && p.catch) p.catch(() => { });
    }
    BF.last = performance.now();
    BF.raf = requestAnimationFrame(bfLoop);
  }

  function bfKeyDown(e) {
    if (!BF.active || BF.over) return;
    const k = e.key;
    if (k === "ArrowLeft" || k === "a" || k === "A") BF.keys.left = true;
    else if (k === "ArrowRight" || k === "d" || k === "D") BF.keys.right = true;
    else if (k === "ArrowDown" || k === "s" || k === "S") BF.keys.crouch = true;
    else if (k === " " || k === "ArrowUp" || k === "w" || k === "W") BF.keys.jump = true;
    else if (k === "Shift") { if (!e.repeat) bfTryDash(); }
    else if (k === "x" || k === "X" || k === "j" || k === "J" || k === "k" || k === "K") { if (!e.repeat) bfTryFire(); }
    if (k === " " || k.indexOf("Arrow") === 0) e.preventDefault();
  }
  function bfKeyUp(e) {
    const k = e.key;
    if (k === "ArrowLeft" || k === "a" || k === "A") BF.keys.left = false;
    else if (k === "ArrowRight" || k === "d" || k === "D") BF.keys.right = false;
    else if (k === "ArrowDown" || k === "s" || k === "S") BF.keys.crouch = false;
    else if (k === " " || k === "ArrowUp" || k === "w" || k === "W") BF.keys.jump = false;
  }
  window.addEventListener("keydown", bfKeyDown);
  window.addEventListener("keyup", bfKeyUp);

  function bfBindBtn(btn, key) {
    const down = (e) => { e.preventDefault(); BF.keys[key] = true; btn.classList.add("press"); };
    const up = (e) => { e.preventDefault(); BF.keys[key] = false; btn.classList.remove("press"); };
    btn.addEventListener("pointerdown", down);
    btn.addEventListener("pointerup", up);
    btn.addEventListener("pointerleave", up);
    btn.addEventListener("pointercancel", up);
  }
  if (bfLeftBtn) bfBindBtn(bfLeftBtn, "left");
  if (bfRightBtn) bfBindBtn(bfRightBtn, "right");
  if (bfCrouchBtn) bfBindBtn(bfCrouchBtn, "crouch");

  if (bfDashBtn) {
    bfDashBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); bfTryDash(); bfDashBtn.classList.add("press"); });
    bfDashBtn.addEventListener("pointerup", (e) => { e.preventDefault(); bfDashBtn.classList.remove("press"); });
    bfDashBtn.addEventListener("pointerleave", () => bfDashBtn.classList.remove("press"));
  }
  if (bfFireBtn) {
    bfFireBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); bfTryFire(); bfFireBtn.classList.add("press"); });
    bfFireBtn.addEventListener("pointerup", (e) => { e.preventDefault(); bfFireBtn.classList.remove("press"); });
    bfFireBtn.addEventListener("pointerleave", () => bfFireBtn.classList.remove("press"));
  }

  const stageBtnEl = $("#stageBtn");
  if (stageBtnEl) {
    stageBtnEl.addEventListener("click", () => {
      if (!BF.active) bfStart();
    });
  }

  if (bfArena) {
    let bfSwipe = { x: 0, y: 0, on: false };
    bfArena.addEventListener("touchstart", (e) => {
      const t = e.changedTouches[0];
      bfSwipe = { x: t.clientX, y: t.clientY, on: true };
    }, { passive: true });
    bfArena.addEventListener("touchend", (e) => {
      if (!bfSwipe.on || !BF.active || BF.over) return;
      const t = e.changedTouches[0];
      const dy = bfSwipe.y - t.clientY;
      const dx = t.clientX - bfSwipe.x;
      bfSwipe.on = false;
      if (dy > 46 && Math.abs(dy) > Math.abs(dx)) {
        BF.keys.jump = true;
        setTimeout(() => { BF.keys.jump = false; }, Math.min(240, 70 + dy * 1.2));
      }
    }, { passive: true });
  }

  /* ---------- THE SIMPLER TIMES — melt, explode, signal, redirect ---------- */
  const mergeLaunch = $("#mergeLaunch");
  const sigOverlay = $("#sigOverlay");
  const sigStatic = $("#sigStatic");
  const sigSub = $("#sigSub");
  const sigPct = $("#sigPct");
  const TST_URL = "https://notmicrosoft2000-cmd.github.io/TheSimplerTimes/?from=tqg";

  let transitActive = false;
  let sigStaticIv = null;
  let sigPctTimer = null;

  function makeMeltDrips() {
    document.querySelectorAll(".melt-drip").forEach((d) => d.remove());
    for (let i = 0; i < 10; i++) {
      const d = document.createElement("div");
      d.className = "melt-drip";
      d.style.left = (2 + Math.random() * 94) + "%";
      d.style.animationDelay = (0.05 + Math.random() * 0.9) + "s";
      document.body.appendChild(d);
    }
    for (let i = 0; i < 8; i++) {
      const d = document.createElement("div");
      d.className = "melt-drip green";
      d.style.left = (2 + Math.random() * 94) + "%";
      d.style.animationDelay = (0.2 + Math.random() * 1.2) + "s";
      document.body.appendChild(d);
    }
  }

  function meltTitle() {
    document.querySelectorAll(".hero h1, .section-title").forEach((el) => el.classList.add("melt"));
  }

  function clearMelt() {
    document.querySelectorAll(".hero h1.melt, .section-title.melt").forEach((el) => el.classList.remove("melt"));
    document.querySelectorAll(".melt-drip").forEach((d) => d.remove());
  }

  function explodeSite() {
    const flash = document.createElement("div");
    flash.className = "explode-flash";
    document.body.appendChild(flash);
    const colors = ["#00dc00", "#ffb020", "#66ff66", "#ffcf7d", "#ffffff"];
    for (let i = 0; i < 30; i++) {
      const f = document.createElement("div");
      f.className = "explode-frag";
      const ang = Math.random() * Math.PI * 2;
      const dist = 18 + Math.random() * 46;
      f.style.setProperty("--dx", Math.round(Math.cos(ang) * dist) + "vw");
      f.style.setProperty("--dy", Math.round(Math.sin(ang) * dist) + "vh");
      f.style.setProperty("--rot", Math.round(Math.random() * 720 - 360) + "deg");
      f.style.background = colors[Math.floor(Math.random() * colors.length)];
      f.style.animationDelay = (Math.random() * 0.12) + "s";
      document.body.appendChild(f);
    }
    document.body.classList.add("exploding");
    setTimeout(() => {
      document.querySelectorAll(".explode-flash, .explode-frag").forEach((el) => el.remove());
      document.body.classList.remove("exploding");
    }, 1200);
  }

  function sigStart() {
    if (!sigOverlay) return;
    clearTimeout(sigPctTimer);
    sigOverlay.classList.remove("hidden");
    sigOverlay.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => requestAnimationFrame(() => sigOverlay.classList.add("go")));
    if (sigStatic) {
      const cv = sigStatic;
      cv.width = window.innerWidth;
      cv.height = window.innerHeight;
      const c2 = cv.getContext("2d");
      sigStaticIv = setInterval(() => {
        const w = cv.width, h = cv.height;
        const img = c2.createImageData(w, h);
        const d = img.data;
        for (let i = 0; i < d.length; i += 4) {
          const v = Math.floor(Math.random() * 256);
          d[i] = v; d[i + 1] = v; d[i + 2] = v; d[i + 3] = 255;
        }
        c2.putImageData(img, 0, 0);
      }, 60);
    }
    const start = performance.now();
    const dur = 2300;
    const tickPct = () => {
      const p = Math.min(100, Math.round(((performance.now() - start) / dur) * 100));
      if (sigPct) sigPct.textContent = p + "%";
      if (p < 100) sigPctTimer = setTimeout(tickPct, 90);
    };
    tickPct();
  }

  function sigStop() {
    if (sigStaticIv) { clearInterval(sigStaticIv); sigStaticIv = null; }
    clearTimeout(sigPctTimer);
    if (sigOverlay) {
      sigOverlay.classList.remove("go");
      sigOverlay.setAttribute("aria-hidden", "true");
      setTimeout(() => sigOverlay.classList.add("hidden"), 250);
    }
  }

  async function beginTransit() {
    if (transitActive || !sigOverlay) return;
    transitActive = true;
    if (termOpen) termClose();
    if (ambienceAudio) { ambienceAudio.pause(); ambiencePlaying(); }
    document.body.classList.add("warming");
    const sig = $("#sigStatus");
    if (sig) sig.textContent = "WARMING";
    showToast("THE QUESTION GAME IS WARMING.");
    sfx.boot();
    await sleep(1400);
    document.body.classList.add("melting");
    makeMeltDrips();
    meltTitle();
    await sleep(2200);
    explodeSite();
    await sleep(850);
    if (sigSub) sigSub.textContent = "RE-ESTABLISHING LINK TO THE SIMPLER TIMES";
    sigStart();
    await sleep(2300);
    sigStop();
    await sleep(300);
    window.location.href = TST_URL;
  }

  function abortTransit() {
    if (!transitActive) return;
    transitActive = false;
    document.body.classList.remove("warming", "melting");
    clearMelt();
    sigStop();
    const sig = $("#sigStatus");
    if (sig) sig.textContent = sig.getAttribute("data-base") || "STABLE";
    showToast("IT LET YOU WALK AWAY. IT WILL REMEMBER THE CLICK.");
  }

  // Arrival from THE SIMPLER TIMES — a short signal-acquired flash over the boot
  (function arrivalFlash() {
    if (new URLSearchParams(location.search).get("from") !== "tst") return;
    if (!sigOverlay) return;
    if (sigSub) sigSub.textContent = "SIGNAL ACQUIRED — MERGE COMPLETE";
    sigOverlay.classList.add("arrive");
    sigOverlay.style.pointerEvents = "none";
    sigStart();
    setTimeout(() => {
      sigStop();
      sigOverlay.classList.remove("arrive");
      sigOverlay.style.pointerEvents = "";
    }, 1900);
  })();

  if (mergeLaunch) {
    mergeLaunch.addEventListener("click", () => beginTransit());
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && transitActive) {
      e.preventDefault();
      abortTransit();
    }
  });

  /* --------------------------------------------------------------
     MAINTENANCE TERMINAL — a real prompt. It obeys.
     -------------------------------------------------------------- */
  const mterm = $("#mterm");
  const termOut = $("#termOut");
  const termInput = $("#termInput");
  let termOpen = false;

  function tEsc(s) {
    return String(s).split("&").join("&amp;").split("<").join("&lt;").split(">").join("&gt;");
  }

  function tPrint(html, cls) {
    if (!termOpen) return;
    const div = document.createElement("div");
    div.className = "t-line " + (cls || "t-in");
    div.innerHTML = html;
    termOut.appendChild(div);
    termOut.scrollTop = termOut.scrollHeight;
    while (termOut.children.length > 220) termOut.removeChild(termOut.firstChild);
  }

  function tType(text, cls, cb) {
    if (!termOpen) { if (cb) cb(); return; }
    const div = document.createElement("div");
    div.className = "t-line " + (cls || "t-in");
    termOut.appendChild(div);
    let i = 0;
    const iv = setInterval(() => {
      if (!termOpen) { clearInterval(iv); return; }
      i += 2 + Math.floor(Math.random() * 3);
      div.textContent = text.slice(0, i);
      termOut.scrollTop = termOut.scrollHeight;
      if (i >= text.length) { clearInterval(iv); if (cb) cb(); }
    }, 10);
  }

  function termOpenIt() {
    if (termOpen) return;
    termOpen = true;
    if (transitActive) abortTransit();
    mterm.classList.remove("hidden");
    mterm.setAttribute("aria-hidden", "false");
    setTimeout(() => mterm.classList.add("go"), 20);
    termOut.textContent = "";
    tType("TQG — LORE & CUSTOMIZATION", "t-sys", () => {
      tType("BROWSE THE RECORD. RECOLOR THE ROOM. IT KEEPS WHAT YOU ASK FOR.", "t-sys", () => {
        setTimeout(() => tPrint('<span class="mterm-prompt">TQG&gt;</span>', "t-in"), 200);
      });
    });
    sfx.type();
    setTimeout(() => termInput.focus(), 260);
  }

  function termClose() {
    if (!termOpen) return;
    termOpen = false;
    mterm.classList.remove("go");
    mterm.setAttribute("aria-hidden", "true");
    sfx.type();
    setTimeout(() => mterm.classList.add("hidden"), 200);
  }

  const TERM_VIEWS = ["home", "about", "sessions", "evidence", "ambience", "quotes", "concerns", "transmission", "preview", "download", "dev", "simpler", "forum", "story"];
  const TQG_VAR_KEYS = ["--bg", "--bg-soft", "--panel", "--line", "--line-bright", "--text", "--dim", "--green", "--green-dim", "--red", "--dark-red", "--cyan"];
  const TQG_PALETTES = {
    green: {},
    amber: { "--bg": "#060400", "--bg-soft": "#0e0902", "--panel": "#0e0902", "--line": "#201406", "--line-bright": "#32200a", "--text": "#ffb020", "--dim": "#7a4c0e", "--green": "#ffb020", "--green-dim": "#7a4c0e", "--red": "#ff3c3c", "--dark-red": "#8a2010", "--cyan": "#ffcf7d" },
    red: { "--bg": "#070101", "--bg-soft": "#0e0202", "--panel": "#0e0202", "--line": "#300a08", "--line-bright": "#4a110d", "--text": "#ff5040", "--dim": "#8a2a20", "--green": "#ff5040", "--green-dim": "#8a2a20", "--red": "#ff2c2c", "--dark-red": "#640000", "--cyan": "#ff9085" },
    blue: { "--bg": "#010207", "--bg-soft": "#02040e", "--panel": "#02040e", "--line": "#081130", "--line-bright": "#0b184a", "--text": "#3a8cff", "--dim": "#1f4a8a", "--green": "#3a8cff", "--green-dim": "#1f4a8a", "--red": "#ff5c5c", "--dark-red": "#640000", "--cyan": "#7ab3ff" },
    mono: { "--bg": "#050505", "--bg-soft": "#0a0a0a", "--panel": "#0a0a0a", "--line": "#1c1c1c", "--line-bright": "#2a2a2a", "--text": "#b8b8b8", "--dim": "#5c5c5c", "--green": "#b8b8b8", "--green-dim": "#5c5c5c", "--red": "#ff5c5c", "--dark-red": "#640000", "--cyan": "#cfcfcf" }
  };

  function tSetColor(name) {
    const p = TQG_PALETTES[name];
    if (!p) return false;
    const rs = document.documentElement.style;
    TQG_VAR_KEYS.forEach((k) => {
      if (name === "green") rs.removeProperty(k);
      else if (p[k] !== undefined) rs.setProperty(k, p[k]);
    });
    return true;
  }

  function termRun(raw) {
    raw = raw.trim();
    const echo = '<span class="mterm-prompt">TQG&gt;</span> ' + tEsc(raw);
    if (!raw) { tPrint(echo, "t-in"); return; }
    const parts = raw.split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const rest = raw.slice(parts[0].length).trim();
    const arg = parts[1] || "";
    const unknown = () => tType("'" + tEsc(raw) + "' IS NOT A KNOWN COMMAND.\nTYPE HELP. IT REMEMBERS WHAT YOU TRY ANYWAY.", "t-err");

    if (cmd === "help" || cmd === "?") {
      tPrint(echo, "t-in");
      tType(
        "HELP — LORE & CUSTOMIZATION\n" +
        "  GOTO <VIEW>     HOME ABOUT SESSIONS EVIDENCE AMBIENCE QUOTES CONCERNS\n" +
        "                  TRANSMISSION PREVIEW DOWNLOAD DEV SIMPLER\n" +
        "  LOGS             UNLOCK + OPEN THE LOG ARCHIVE\n" +
        "  COLOR <N>        GREEN AMBER RED BLUE MONO\n" +
        "  STYLE <N>        DARK RETRO CRT OLD\n" +
        "  AMBIENCE [ON|OFF]\n" +
        (logsUnlocked ? "  FX <ON|OFF>      DROP OR RESTORE THE STATIC + CRT\n" : "") +
        "  WHISPER <T>      WHISPER ANYTHING\n" +
        "  TOAST <T>        SAY IT OUT LOUD\n" +
        "  TYPE <T>         TYPE IT FOR YOU IN THE BOX\n" +
        "  TST              BEGIN THE MERGE TO THE SIMPLER TIMES\n" +
        "  STATS · WHOAMI · DATE · TIME · VER\n" +
        "  CLS · EXIT · ECHO",
        "t-sys"
      );
      return;
    }
    if (cmd === "cls" || cmd === "clear") { termOut.textContent = ""; tPrint(echo, "t-in"); return; }
    if (cmd === "echo") { tPrint(echo, "t-in"); tType(rest || "ECHO IS ON.", "t-in"); return; }
    if (cmd === "goto" || cmd === "go" || cmd === "visit") {
      tPrint(echo, "t-in");
      const v = arg.toLowerCase();
      if (v === "logs") {
        unlockLogs();
        setTimeout(() => { termClose(); showView("logs"); }, 250);
        tType("LOG ARCHIVE UNLOCKED. OPENING IT.", "t-ok");
        return;
      }
      if (TERM_VIEWS.indexOf(v) === -1) { tType("NO SUCH SECTION: " + arg.toUpperCase() + "\nTHE SITE HAS SECTIONS. THAT IS NOT ONE OF THEM.", "t-err"); return; }
      setTimeout(() => { termClose(); showView(v); }, 250);
      tType("GOING TO: " + arg.toUpperCase(), "t-ok");
      return;
    }
    if (cmd === "logs" || cmd === "2013") {
      tPrint(echo, "t-in");
      unlockLogs();
      setTimeout(() => { termClose(); showView("logs"); }, 250);
      tType("2013. LOG ARCHIVE OPEN.", "t-ok");
      return;
    }
    if (cmd === "whisper") {
      tPrint(echo, "t-in");
      showWhisperText(rest || "IT SEES YOU.");
      tType("WHISPERED: " + rest.toUpperCase(), "t-in");
      return;
    }
    if (cmd === "toast") {
      tPrint(echo, "t-in");
      showToast(rest || "IT SEES YOU.", false);
      tType("SAID IT OUT LOUD.", "t-in");
      return;
    }
    if (cmd === "type") {
      tPrint(echo, "t-in");
      if (typeIn) { typeIn.value = rest; tType("TYPED IT FOR YOU. IT LOOKS MORE NATURAL IN YOUR HANDS.", "t-in"); }
      else tType("NO INPUT BOX HERE. IT WILL REMEMBER THIS.", "t-err");
      return;
    }
    if (cmd === "color" || cmd === "palette") {
      tPrint(echo, "t-in");
      const n = (arg || "green").toLowerCase();
      if (tSetColor(n)) tType("PALETTE: " + n.toUpperCase() + ". THE WHOLE SITE IS " + n.toUpperCase() + " NOW.", "t-ok");
      else tType("UNKNOWN PALETTE: " + arg + "\nTRY GREEN, AMBER, RED, BLUE OR MONO.", "t-err");
      return;
    }
    if (cmd === "style" || cmd === "theme") {
      tPrint(echo, "t-in");
      const n = (arg || "dark").toLowerCase();
      if (setStyle(n, true)) tType("STYLE: " + n.toUpperCase() + ".\nTHE SITE REBUILT ITSELF. IT REMEMBERS IT NOW.", "t-ok");
      else tType("UNKNOWN STYLE: " + arg + "\nTRY DARK, RETRO, CRT OR OLD.", "t-err");
      return;
    }
    if (cmd === "fx" || cmd === "static" || cmd === "effects") {
      tPrint(echo, "t-in");
      if (!logsUnlocked) {
        tType("THAT SWITCH IS IN THE ARCHIVE.\nUNLOCK THE LOGS FIRST — FOUR CHARACTERS, TYPED QUICKLY.", "t-err");
        return;
      }
      if (/off|remove|drop|clear|clean/.test(rest)) {
        setFxEnabled(false, true);
        tType("STATIC AND CRT: OFF.\nTHE ROOM GOT QUIETER. IT WATCHES THE SAME.", "t-ok");
      } else if (/on|restore|back|add/.test(rest)) {
        setFxEnabled(true, true);
        tType("STATIC AND CRT: ON.\nTHE FEED RETURNS. EVERYTHING IS AS IT WAS.", "t-in");
      } else {
        tType("FX IS " + (fxEnabled ? "ON" : "OFF") + ".\nTRY FX OFF OR FX ON.", "t-sys");
      }
      return;
    }
    if (cmd === "ambience") {
      tPrint(echo, "t-in");
      if (!ambienceAudio) { tType("NO FEED. THE ROOM IS SILENT. IT IS LISTENING HARDER.", "t-err"); return; }
      if (/off|mute/.test(rest)) { ambienceAudio.pause(); ambiencePlaying(); tType("AMBIENCE: OFF. THE ROOM IS QUIETER.", "t-in"); return; }
      if (/on|play/.test(rest)) {
        const p = ambienceAudio.play();
        if (p && p.catch) p.catch(() => showToast("AUDIO BLOCKED — CLICK [ PLAY ] AGAIN", true));
        ambiencePlaying();
        tType("AMBIENCE: ON.", "t-in");
        return;
      }
      if (ambienceAudio.paused) { const p = ambienceAudio.play(); if (p && p.catch) p.catch(() => {}); }
      else ambienceAudio.pause();
      ambiencePlaying();
      tType("AMBIENCE: " + (ambienceAudio.paused ? "OFF" : "ON") + ".", "t-in");
      return;
    }
    if (cmd === "tst" || cmd === "simpler" || cmd === "merge") {
      tPrint(echo, "t-in");
      tType("BEGINNING THE MERGE.\nIT HAS BEEN WAITING FOR YOU TO ASK.", "t-amber");
      setTimeout(() => { termClose(); beginTransit(); }, 700);
      return;
    }
    if (cmd === "stats") {
      tPrint(echo, "t-in");
      const q = $("#qCounter");
      tType("SESSIONS: " + (q ? q.textContent : "??") + "\nANSWERS FILED: EVERY ONE OF THEM.\nYOUR SESSION: CURRENTLY BEING WATCHED.", "t-sys");
      return;
    }
    if (cmd === "whoami") {
      tPrint(echo, "t-in");
      tType("A SESSION IN THE ARCHIVE.\nNUMBERED. TIMESTAMPED. FILED BEFORE YOU FINISHED TYPING.", "t-sys");
      return;
    }
    if (cmd === "date") {
      tPrint(echo, "t-in");
      tType("CURRENT DATE: 2013. SOMETIMES IT FORGETS THE YEAR IS OVER.\nTHE ARCHIVE DOES NOT.", "t-sys");
      return;
    }
    if (cmd === "time") {
      tPrint(echo, "t-in");
      const d = new Date();
      tType("CURRENT TIME: " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + "\nIT KNOWS WHAT TIME IT IS WHERE YOU ARE.", "t-sys");
      return;
    }
    if (cmd === "ver" || cmd === "version") {
      tPrint(echo, "t-in");
      tType("THE QUESTION GAME WEBSITE v2.04\nBUILD: STILL. STILL RUNNING.", "t-sys");
      return;
    }
    if (cmd === "exit" || cmd === "quit") {
      tPrint(echo, "t-in");
      tType("GOODBYE. THE TERMINAL STAYS OPEN FOR YOU. IT ALWAYS HAS.", "t-sys");
      setTimeout(termClose, 600);
      return;
    }
    tPrint(echo, "t-in");
    unknown();
  }

  if (termInput) {
    termInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        termRun(termInput.value);
        termInput.value = "";
      } else if (e.key === "Escape" || e.key === "`" || e.key === "Backquote") {
        e.preventDefault();
        termClose();
      }
    });
  }
  const mtermHead = $("#mtermHead");
  const termCloseBtn = $("#termCloseBtn");
  const finePointer = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
  let termDrag = null;
  if (mtermHead && finePointer) {
    mtermHead.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".mterm-close")) return;
      termDrag = { dx: e.clientX - mterm.offsetLeft, dy: e.clientY - mterm.offsetTop };
      mterm.classList.add("dragging");
      if (mterm.setPointerCapture) mterm.setPointerCapture(e.pointerId);
    });
    mterm.addEventListener("pointermove", (e) => {
      if (!termDrag) return;
      mterm.style.left = (e.clientX - termDrag.dx) + "px";
      mterm.style.top = (e.clientY - termDrag.dy) + "px";
    });
    const endDrag = () => {
      if (!termDrag) return;
      termDrag = null;
      mterm.classList.remove("dragging");
    };
    mterm.addEventListener("pointerup", endDrag);
    mterm.addEventListener("pointercancel", endDrag);
  }
  if (termCloseBtn) {
    termCloseBtn.addEventListener("click", () => termClose());
    termCloseBtn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); termClose(); }
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "`" && e.key !== "Backquote") return;
    if (!document.body.classList.contains("loaded")) return;
    if (GAME_OVERLAY) return;
    if (e.target === termInput) return;
    e.preventDefault();
    termOpen ? termClose() : termOpenIt();
  });

  initNoise();
  initAsh();
  runBoot().catch(() => {
    boot.classList.add("done");
    document.body.classList.remove("no-scroll");
    document.body.classList.add("loaded");
  });

  /* ---------- Forum — GitHub Issues chat + uploads ---------- */
  const FC = window.FORUM_CONFIG || {};
  let forumUser = null;
  let forumToken = "";
  try { forumUser = JSON.parse(localStorage.getItem("tqg-forum-user") || "null"); } catch (e) {}
  try { forumToken = localStorage.getItem("tqg-forum-token") || ""; } catch (e) {}

  const forumAuth = $("#forumAuth");
  const forumMsgs = $("#forumMsgs");
  const forumMsg = $("#forumMsg");
  const forumStatus = $("#forumStatus");
  const forumTokenInput = $("#forumToken");
  const forumTokenBox = $("#forumTokenBox");
  const forumAuthHint = $("#forumAuthHint");
  const forumSignupForm = $("#forumSignupForm");
  const forumLoginForm = $("#forumLoginForm");
  const forumSignupName = $("#forumSignupName");
  const forumSignupPass = $("#forumSignupPass");
  const forumSignupPass2 = $("#forumSignupPass2");
  const forumLoginName = $("#forumLoginName");
  const forumLoginPass = $("#forumLoginPass");

  async function forumHash(pw, salt) {
    const data = new TextEncoder().encode(salt + ":" + pw);
    const buf = await crypto.subtle.digest("SHA-256", data);
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  function forumAcctKey(name) { return "tqg-forum-acct-" + name.toLowerCase(); }
  function forumGetUser(name) {
    try { return JSON.parse(localStorage.getItem(forumAcctKey(name)) || "null"); } catch (e) { return null; }
  }
  function forumSetSession(u) {
    forumUser = u;
    try { localStorage.setItem("tqg-forum-user", JSON.stringify(u)); } catch (e) {}
    if (forumTokenBox) forumTokenBox.classList.remove("hidden");
    if (forumAuthHint) forumAuthHint.textContent = u
      ? "Logged in as " + u.name + ". Add or update your GitHub token to post and upload."
      : "Posting identity comes from a GitHub token — your messages show your GitHub avatar and name.";
  }
  function forumStatusMsg(t) {
    if (forumStatus) { forumStatus.textContent = t; forumStatus.classList.add("show"); }
  }

  async function forumSignup(e) {
    e.preventDefault();
    const name = (forumSignupName.value || "").trim();
    const pw = forumSignupPass.value || "";
    const pw2 = forumSignupPass2.value || "";
    if (pw !== pw2) { forumStatusMsg("PASSWORDS DO NOT MATCH."); return; }
    if (!/^[A-Za-z0-9_\- ]{3,24}$/.test(name)) { forumStatusMsg("USERNAME MUST BE 3-24 CHARS: LETTERS, NUMBERS, _ - SPACE."); return; }
    if (pw.length < 4) { forumStatusMsg("PASSWORD MUST BE AT LEAST 4 CHARACTERS."); return; }
    if (forumGetUser(name)) { forumStatusMsg("THAT USERNAME IS TAKEN ON THIS DEVICE."); return; }
    const salt = Math.random().toString(36).slice(2) + Date.now().toString(36);
    const hash = await forumHash(pw, salt);
    const u = { name, salt, hash };
    try { localStorage.setItem(forumAcctKey(name), JSON.stringify(u)); } catch (err) { forumStatusMsg("COULD NOT SAVE ACCOUNT."); return; }
    forumSetSession(u);
    forumSignupForm.reset();
    forumStatusMsg("ACCOUNT CREATED. WELCOME, " + name.toUpperCase() + ".");
    if (forumTokenInput) forumTokenInput.focus();
  }

  async function forumLogin(e) {
    e.preventDefault();
    const name = (forumLoginName.value || "").trim();
    const pw = forumLoginPass.value || "";
    const u = forumGetUser(name);
    if (!u) { forumStatusMsg("NO ACCOUNT WITH THAT USERNAME ON THIS DEVICE."); return; }
    const h = await forumHash(pw, u.salt);
    if (h !== u.hash) { forumStatusMsg("WRONG PASSWORD."); return; }
    forumSetSession(u);
    forumLoginForm.reset();
    forumStatusMsg("WELCOME BACK, " + u.name.toUpperCase() + ".");
  }

  function forumTokenSave() {
    if (!forumTokenInput) return;
    const t = forumTokenInput.value.trim();
    if (!t) { forumStatusMsg("TYPE A TOKEN FIRST."); return; }
    forumToken = t;
    try { localStorage.setItem("tqg-forum-token", t); } catch (e) {}
    forumTokenInput.value = "";
    forumStatusMsg("TOKEN SAVED — YOU CAN NOW POST AND UPLOAD.");
  }

  async function forumApi(path, opts) {
    const res = await fetch(FC.api + path, opts || {});
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.message || "GitHub error " + res.status);
    return body;
  }

  // Anonymous guests read the static mirror committed by the forum-cache
  // workflow (unlimited, no API rate limit). Logged-in users read the live
  // GitHub API (5,000 req/hr with their token).
  async function forumRead() {
    if (forumToken) {
      return forumApi("/repos/" + FC.owner + "/" + FC.repo + "/issues/" + FC.channelIssue + "/comments?per_page=100");
    }
    const cacheUrl = FC.raw + "/" + FC.owner + "/" + FC.repo + "/" + (FC.cacheBranch || "forum-cache") + "/" + (FC.cachePath || "forum-cache.json");
    const res = await fetch(cacheUrl);
    if (!res.ok) throw new Error("cache unavailable " + res.status);
    const data = await res.json();
    if (forumStatus) {
      const ts = new Date(data.updated_at).toLocaleTimeString();
      forumStatus.textContent = "CACHE MIRROR · UPDATED " + ts;
      forumStatus.classList.remove("show");
    }
    return (data.comments || []).map((c) => {
      c.created_at = c.created_at || new Date().toISOString();
      return c;
    });
  }

  async function forumLoad() {
    if (!forumMsgs || !FC.channelIssue) return;
    forumStatusMsg("LOADING...");
    try {
      const comments = await forumRead();
      forumRender(comments || []);
      if (forumToken) forumStatusMsg("");
    } catch (err) {
      // Fall back to the live API even for guests if the mirror is missing.
      try {
        const comments = await forumApi("/repos/" + FC.owner + "/" + FC.repo + "/issues/" + FC.channelIssue + "/comments?per_page=100");
        forumRender(comments || []);
        forumStatusMsg("");
      } catch (err2) {
        forumStatusMsg("COULDN'T REACH THE FORUM: " + err.message);
      }
    }
  }

  function forumRender(comments) {
    forumMsgs.innerHTML = "";
    const list = comments.slice().reverse();
    if (!list.length) {
      forumMsgs.innerHTML = '<p class="forum-empty">NO MESSAGES YET — BE THE FIRST.</p>';
    }
    list.forEach((c) => {
      const div = document.createElement("div");
      div.className = "forum-msg";
      const who = (c.user && c.user.login) ? c.user.login : "GHOST";
      const avatar = c.user && c.user.avatar_url;
      const when = new Date(c.created_at).toLocaleString();
      div.innerHTML =
        '<div class="forum-msg-head">' +
        (avatar ? '<img class="forum-avatar" src="' + avatar + '" alt="" loading="lazy">' : "") +
        '<span class="forum-who">' + who + "</span>" +
        '<span class="forum-when">' + when + "</span></div>" +
        '<div class="forum-msg-body">' + forumRenderBody(c.body || "") + "</div>";
      forumMsgs.appendChild(div);
    });
    const count = $("#forumMsgCount");
    if (count) count.textContent = list.length + " POST" + (list.length === 1 ? "" : "S");
    forumMsgs.scrollTop = forumMsgs.scrollHeight;
  }

  function forumRenderBody(text) {
    return String(text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .split("\n").map((line) =>
        line.replace(/https?:\/\/[^\s]+/g, (u) => {
          if (/\.(png|jpe?g|gif|webp)(\?.*)?$/i.test(u)) {
            return '<a href="' + u + '" target="_blank" rel="noopener"><img class="forum-img" src="' + u + '" alt="attachment" loading="lazy"></a>';
          }
          return '<a href="' + u + '" target="_blank" rel="noopener">' + u + "</a>";
        })
      ).join("<br>");
  }

  async function forumSend(text) {
    const body = String(text !== undefined ? text : (forumMsg ? forumMsg.value : "")).trim();
    if (!body) return;
    if (!forumUser) { forumStatusMsg("SIGN UP OR LOG IN FIRST."); return; }
    if (!forumToken) { forumStatusMsg("ADD YOUR GITHUB TOKEN TO POST."); return; }
    try {
      await forumApi("/repos/" + FC.owner + "/" + FC.repo + "/issues/" + FC.channelIssue + "/comments", {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + forumToken,
          "Accept": "application/vnd.github+json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ body: "**" + forumUser.name + ":** " + body })
      });
      if (forumMsg) forumMsg.value = "";
      forumLoad();
    } catch (err) {
      forumStatusMsg("POST FAILED: " + err.message + ". CHECK THE TOKEN SCOPES.");
    }
  }

  async function forumUpload(file) {
    if (!file) return;
    if (!forumUser) { forumStatusMsg("SIGN UP OR LOG IN FIRST."); return; }
    if (!forumToken) { forumStatusMsg("ADD YOUR GITHUB TOKEN TO UPLOAD."); return; }
    if (file.size > 10 * 1024 * 1024) { forumStatusMsg("MAX 10 MB PER FILE."); return; }
    forumStatusMsg("UPLOADING " + file.name.toUpperCase() + "...");
    const base64 = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result).split(",")[1]);
      r.onerror = rej;
      r.readAsDataURL(file);
    });
    const path = FC.uploadsPath + "/" + Date.now() + "-" + String(file.name).replace(/[^\w.\- ]/g, "_");
    try {
      await forumApi("/repos/" + FC.owner + "/" + FC.repo + "/contents/" + path, {
        method: "PUT",
        headers: {
          "Authorization": "Bearer " + forumToken,
          "Accept": "application/vnd.github+json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: "Forum upload: " + file.name, content: base64, branch: FC.branch })
      });
      const url = FC.raw + "/" + FC.owner + "/" + FC.repo + "/" + FC.branch + "/" + path;
      forumStatusMsg("UPLOADED. POSTING LINK...");
      forumSend("shared " + file.name + "\n" + url);
    } catch (err) {
      forumStatusMsg("UPLOAD FAILED: " + err.message + ". TOKEN NEEDS CONTENTS:WRITE.");
    }
  }

  if (forumAuth && forumSignupForm && forumLoginForm) {
    const tabSignup = $("#forumTabSignup");
    const tabLogin = $("#forumTabLogin");
    if (tabSignup) tabSignup.addEventListener("click", () => {
      tabSignup.classList.add("active"); tabLogin.classList.remove("active");
      forumLoginForm.classList.add("hidden"); forumSignupForm.classList.remove("hidden");
    });
    if (tabLogin) tabLogin.addEventListener("click", () => {
      tabLogin.classList.add("active"); tabSignup.classList.remove("active");
      forumSignupForm.classList.add("hidden"); forumLoginForm.classList.remove("hidden");
    });
    forumSignupForm.addEventListener("submit", forumSignup);
    forumLoginForm.addEventListener("submit", forumLogin);
    const tokenSave = $("#forumTokenSave");
    if (tokenSave) tokenSave.addEventListener("click", forumTokenSave);
    if (forumUser) forumSetSession(forumUser);
  }
  if (forumMsg) {
    const sendBtn = $("#forumSend");
    if (sendBtn) sendBtn.addEventListener("click", () => forumSend());
    forumMsg.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); forumSend(); }
    });
  }
  const fileInput = $("#forumFile");
  if (fileInput) fileInput.addEventListener("change", (e) => forumUpload(e.target.files && e.target.files[0]));
  const refreshBtn = $("#forumRefresh");
  if (refreshBtn) refreshBtn.addEventListener("click", forumLoad);
  if (forumTokenInput && forumToken) forumTokenInput.placeholder = "TOKEN SAVED — CLEAR TO CHANGE";
})();
