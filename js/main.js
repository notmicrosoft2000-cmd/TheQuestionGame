(() => {
  "use strict";

  const REPO = "notmicrosoft2000-cmd/TheQuestionGame";
  const REPO_URL = "https://github.com/" + REPO;
  const RELEASES_URL = REPO_URL + "/releases/latest";

  const $ = (s, c) => (c || document).querySelector(s);
  const $$ = (s, c) => Array.prototype.slice.call((c || document).querySelectorAll(s));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const rand = (a, b) => Math.random() * (b - a) + a;

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

  const sfx = {
    ctx: null,
    init() {
      if (!this.ctx) {
        try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { }
      }
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
    },
    blip(freq, dur, vol, type) {
      if (!this.ctx) return;
      try {
        const o = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        o.type = type || "square";
        o.frequency.value = freq;
        g.gain.setValueAtTime(vol, this.ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + dur);
        o.connect(g);
        g.connect(this.ctx.destination);
        o.start();
        o.stop(this.ctx.currentTime + dur);
      } catch (e) { }
    },
    select() { this.blip(880, 0.07, 0.035); },
    nav() { this.blip(600, 0.03, 0.022); },
    error() { this.blip(150, 0.22, 0.05, "sawtooth"); }
  };

  function primeAudio() {
    sfx.init();
  }
  window.addEventListener("pointerdown", primeAudio, { once: true });
  window.addEventListener("keydown", primeAudio, { once: true });

  const soundToggle = $("#soundToggle");
  const ambience = {
    built: false,
    gain: null,
    muted: localStorage.getItem("tq:ambience") === "off",
    build() {
      sfx.init();
      if (this.built || !sfx.ctx) return;
      try {
        const ctx = sfx.ctx;
        const len = ctx.sampleRate * 4;
        const buf = ctx.createBuffer(1, len, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.loop = true;
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.value = 2400;
        const hum = ctx.createOscillator();
        hum.type = "sine";
        hum.frequency.value = 55;
        const humG = ctx.createGain();
        humG.gain.value = 0.05;
        this.gain = ctx.createGain();
        this.gain.gain.value = this.muted ? 0 : 0.05;
        src.connect(lp);
        lp.connect(this.gain);
        hum.connect(humG);
        humG.connect(this.gain);
        this.gain.connect(ctx.destination);
        src.start();
        hum.start();
        this.built = true;
      } catch (e) { }
    },
    setMuted(m) {
      this.muted = m;
      localStorage.setItem("tq:ambience", m ? "off" : "on");
      if (this.gain) this.gain.gain.value = m ? 0 : 0.05;
      if (soundToggle) {
        soundToggle.classList.toggle("off", m);
        soundToggle.textContent = m ? "AMBIENCE: OFF" : "AMBIENCE: ON";
      }
    }
  };

  if (soundToggle) {
    soundToggle.classList.toggle("off", ambience.muted);
    soundToggle.textContent = ambience.muted ? "AMBIENCE: OFF" : "AMBIENCE: ON";
    soundToggle.addEventListener("click", () => {
      sfx.init();
      if (!ambience.built) ambience.build();
      ambience.setMuted(!ambience.muted);
      sfx.select();
    });
  }

  const boot = $("#boot");
  const bootLog = $("#bootLog");
  const bootPrompt = $("#bootPrompt");

  const BOOT_LINES = [
    ["INITIALIZING THE QUESTION GAME v1.0.0", ""],
    ["CONNECTING TO LOCAL ENVIRONMENT METRICS ...", ""],
    ["READING HARDWARE PROFILE ... OK", ""],
    ["CALIBRATING INPUT PROTOCOL ... OK", ""],
    ["SCANNING SESSION ARCHIVE ...", ""],
    ["SESSION 001 READY.", ""],
    ["", ""],
    ["THIS IS NOT THE FIRST TIME WE HAVE SPOKEN.", "red"],
    ["ARE YOU SITTING COMFORTABLY?", "red"]
  ];

  async function runBoot() {
    document.body.classList.add("no-scroll");
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      boot.classList.add("done");
      document.body.classList.remove("no-scroll");
      document.body.classList.add("loaded");
      ambience.build();
      startHeroType();
      startRecTimer();
      startFlashLoop();
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
      sfx.nav();
    }
  }

  const heroType = $("#heroType");
  const HERO_PHRASES = [
    "IT REMEMBERS. DO YOU?",
    "ANSWER HONESTLY.",
    "THERE IS NO SKIP BUTTON.",
    "IT IS WAITING."
  ];

  async function startHeroType() {
    if (!heroType) return;
    await sleep(700);
    for (;;) {
      for (const phrase of HERO_PHRASES) {
        heroType.textContent = "";
        await typeNode(heroType, phrase, 46);
        await sleep(2600);
      }
    }
  }

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
          sfx.blip(80, 0.1, 0.04, "sawtooth");
          setTimeout(() => flash.classList.remove("go"), 200);
        }
        loop();
      }, rand(14000, 26000));
    })();
  }

  const noiseCnv = $("#noise");
  let noiseCtx = null;
  function initNoise() {
    if (!noiseCnv) return;
    noiseCtx = noiseCnv.getContext("2d");
    sizeNoise();
    frameNoise();
  }
  function sizeNoise() {
    noiseCnv.width = Math.max(1, Math.floor(window.innerWidth / 2));
    noiseCnv.height = Math.max(1, Math.floor(window.innerHeight / 2));
  }
  let noiseFrame = 0;
  function frameNoise() {
    const w = noiseCnv.width, h = noiseCnv.height;
    const img = noiseCtx.createImageData(w, h);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      const v = (Math.random() * 255) | 0;
      d[i] = v; d[i + 1] = v; d[i + 2] = v; d[i + 3] = 22;
    }
    noiseCtx.putImageData(img, 0, 0);
    noiseFrame++;
    if (noiseFrame % 9 === 0) {
      noiseCtx.fillStyle = "rgba(255,255,255,0.05)";
      noiseCtx.fillRect(0, Math.random() * h, w, 2 + Math.random() * 8);
    }
    setTimeout(frameNoise, 66);
  }
  window.addEventListener("resize", sizeNoise);

  const cursor = $("#cursor");
  if (cursor && window.matchMedia("(pointer: fine)").matches) {
    let cx = window.innerWidth / 2, cy = window.innerHeight / 2;
    window.addEventListener("mousemove", (e) => { cx = e.clientX; cy = e.clientY; });
    (function moveCursor() {
      cursor.style.transform = "translate(" + cx + "px," + cy + "px) translate(-50%,-50%)";
      requestAnimationFrame(moveCursor);
    })();
    const hoverSel = "a, button, .term-opt, input, textarea, select, .session, .stat";
    document.addEventListener("mouseover", (e) => {
      if (e.target.closest(hoverSel)) cursor.classList.add("is-hover");
    });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest(hoverSel)) cursor.classList.remove("is-hover");
    });
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
    { q: "ARE YOU AFRAID OF THE DARK?", o: ["YES", "NO"], r: ["GOOD. THE DARK REMEMBERS TOO.", "EVERYONE IS. YOU HIDE IT BETTER."] }
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
      b.addEventListener("mouseenter", () => {
        if (sfx.ctx) sfx.nav();
      });
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
    if (termBusy || !resolveOpt) return;
    sfx.select();
    resolveOpt(i);
    resolveOpt = null;
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
          sfx.nav();
        } else if (e.key === "Enter") {
          e.preventDefault();
          selectOption(sel);
        } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
          e.preventDefault();
          sel = (sel - 1 + step.o.length) % step.o.length;
          setActive(sel);
          sfx.nav();
        } else if (e.key === "ArrowDown" || e.key === "ArrowRight") {
          e.preventDefault();
          sel = (sel + 1) % step.o.length;
          setActive(sel);
          sfx.nav();
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
    toDownload.addEventListener("click", () => { if (sfx.ctx) sfx.select(); });
    termOptions.classList.remove("hidden");
    termOptions.innerHTML = "";
    termOptions.appendChild(again);
    termOptions.appendChild(toDownload);
    termBusy = false;
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

  function assetRow(asset, recommended) {
    const row = document.createElement("div");
    row.className = "asset-row";
    const info = document.createElement("div");
    info.className = "asset-info";
    const name = document.createElement("div");
    name.className = "asset-name";
    name.textContent = asset.name;
    info.appendChild(name);
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    meta.textContent = fmtSize(asset.size) + " · " + new Date(asset.updated_at || asset.created_at).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
    info.appendChild(meta);
    row.appendChild(info);
    const btn = document.createElement("a");
    btn.className = "asset-btn";
    btn.href = asset.browser_download_url;
    btn.target = "_blank";
    btn.rel = "noopener";
    btn.textContent = recommended ? "DOWNLOAD ⤓" : "GET";
    row.appendChild(btn);
    if (recommended) {
      const badge = document.createElement("span");
      badge.className = "asset-badge";
      badge.textContent = "RECOMMENDED";
      name.appendChild(badge);
    }
    return row;
  }

  async function loadRelease() {
    const box = $("#releaseAssets");
    const ver = $("#relVersion");
    const date = $("#relDate");
    try {
      const res = await fetch("https://api.github.com/repos/" + REPO + "/releases/latest");
      if (!res.ok) throw new Error("release not found");
      const rel = await res.json();
      ver.textContent = rel.tag_name || "v1.0.0";
      date.textContent = "RELEASED " + new Date(rel.published_at).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
      box.innerHTML = "";
      const assets = (rel.assets || []).slice().sort((a, b) => (b.size - a.size));
      const zip = assets.filter((a) => /\.zip$/i.test(a.name));
      const rest = assets.filter((a) => !/\.zip$/i.test(a.name));
      const ordered = zip.concat(rest).slice(0, 4);
      if (!ordered.length) {
        const a = document.createElement("p");
        a.className = "release-loading";
        a.textContent = "NO FILES ATTACHED TO THIS RELEASE YET.";
        box.appendChild(a);
      }
      ordered.forEach((a, i) => box.appendChild(assetRow(a, i === 0)));
    } catch (e) {
      date.textContent = "RELEASE NOT PUBLISHED YET";
      box.innerHTML = "";
      const p = document.createElement("p");
      p.className = "release-loading";
      p.textContent = "WAITING FOR THE FIRST RELEASE. THE ARCHIVE WILL APPEAR HERE.";
      box.appendChild(p);
      const a = document.createElement("a");
      a.className = "asset-btn";
      a.href = RELEASES_URL;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "[ OPEN GITHUB RELEASES ]";
      box.appendChild(a);
    }
  }
  loadRelease();

  const toast = $("#toast");
  let toastTimer = null;
  function showToast(text, isRed) {
    toast.textContent = text;
    toast.classList.toggle("red", !!isRed);
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3800);
  }

  const PHRASES = {
    "who are you": "WE ARE A SET OF QUESTIONS.",
    "are you there": "WE ARE ALWAYS HERE.",
    "exit": "ESCAPING IS NOT AS EASY AS YOU THINK.",
    "help": "NO HELP FOR YOU.",
    "truth": "THE TRUTH WAS ALWAYS THE POINT.",
    "lie": "LYING IS NOTED. IT ALWAYS IS.",
    "game": "THE GAME REMEMBERS. DO YOU?"
  };
  let keyBuf = "";
  let keyTimer = null;
  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Enter") {
      keyBuf = "";
      return;
    }
    if (e.key.length === 1) {
      keyBuf = (keyBuf + e.key.toLowerCase()).slice(-24);
      clearTimeout(keyTimer);
      keyTimer = setTimeout(() => { keyBuf = ""; }, 2500);
      for (const phrase in PHRASES) {
        if (keyBuf.endsWith(phrase)) {
          showToast(PHRASES[phrase], phrase === "exit" || phrase === "lie");
          keyBuf = "";
          break;
        }
      }
    }
  });

  initNoise();
  runBoot().catch(() => {
    boot.classList.add("done");
    document.body.classList.remove("no-scroll");
    document.body.classList.add("loaded");
  });
})();
