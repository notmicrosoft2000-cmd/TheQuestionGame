(() => {
  "use strict";

  const REPO = "notmicrosoft2000-cmd/TheQuestionGame";


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
          setTimeout(() => flash.classList.remove("go"), 200);
        }
        loop();
      }, rand(10000, 20000));
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
    if (noiseCtx) {
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
    }
    setTimeout(frameNoise, document.hidden ? 400 : 100);
  }
  window.addEventListener("resize", sizeNoise);

  const cursor = $("#cursor");
  if (cursor && window.matchMedia("(pointer: fine)").matches) {
    window.addEventListener("mousemove", (e) => {
      cursor.style.transform = "translate(" + e.clientX + "px," + e.clientY + "px) translate(-50%,-50%)";
    });
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

  function showView(name) {
    const target = $('[data-view="' + name + '"]');
    if (!target) return;
    $$(".view.active").forEach((v) => v.classList.remove("active"));
    target.classList.add("active");
    $$(".nav-links a, .side-link").forEach((a) => {
      const href = (a.getAttribute("href") || "").replace(/^#/, "");
      a.classList.toggle("active", href === name);
    });
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    setPanel(false);
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const id = (a.getAttribute("href") || "").slice(1);
    const el = document.getElementById(id);
    if (el && el.dataset && el.dataset.view) {
      e.preventDefault();
      showView(el.dataset.view);
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
    [/\.zip$/i, "WINDOWS 10/11 — ZIP ARCHIVE"],
    [/\.dmg$/i, "macOS — APP BUNDLE"]
  ];

  function setStatus(el, text, miss) {
    el.textContent = text;
    el.classList.toggle("miss", !!miss);
  }

  function platformKey() {
    const p = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    if (/mac|darwin/i.test(p)) return "mac";
    if (/win/i.test(p)) return "win";
    return null;
  }

  function wirePlatform(btnId, statusId, asset) {
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

  async function loadRelease() {
    const ver = $("#relVersion");
    const date = $("#relDate");
    const fallback = $("#releaseFallback");
    const os = platformKey();
    if (os === "win" || os === "mac") {
      const card = $(os === "mac" ? "#macCard" : "#winCard");
      const tag = $(os === "mac" ? "#macDetected" : "#winDetected");
      card.classList.add("is-current");
      if (tag) tag.classList.remove("hidden");
    }
    try {
      const res = await fetch("https://api.github.com/repos/" + REPO + "/releases/latest");
      if (!res.ok) throw new Error("release not found");
      const rel = await res.json();
      ver.textContent = rel.tag_name || "v1.0.0";
      date.textContent = "RELEASED " + new Date(rel.published_at).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
      const assets = rel.assets || [];
      wirePlatform("dlWindows", "dlWindowsStatus", assets.find((a) => /\.zip$/i.test(a.name)));
      wirePlatform("dlMac", "dlMacStatus", assets.find((a) => /\.dmg$/i.test(a.name)));
    } catch (e) {
      date.textContent = "RELEASE NOT PUBLISHED YET";
      ["dlWindows", "dlMac"].forEach((id) => {
        const btn = $("#" + id);
        btn.setAttribute("aria-disabled", "true");
        btn.classList.add("platform-miss");
        btn.textContent = "UNAVAILABLE";
      });
      setStatus($("#dlWindowsStatus"), "WINDOWS BUILD NOT PUBLISHED YET", true);
      setStatus($("#dlMacStatus"), "MACOS BUILD NOT PUBLISHED YET", true);
      fallback.classList.remove("hidden");
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
  }

  const scare = $("#scare");

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
  let keyBuf = "";
  let keyTimer = null;

  function handleTypeKey(e, key) {
    sfx.type();
    keyBuf = (keyBuf + key.toLowerCase()).slice(-24);
    clearTimeout(keyTimer);
    keyTimer = setTimeout(() => { keyBuf = ""; }, 2500);
    if (keyBuf.endsWith("hello")) {
      keyBuf = "";
      if (typeIn) typeIn.value = "";
      jumpscare();
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
    const tag = (e.target.tagName || "").toLowerCase();
    const inSignal = typeIn && e.target === typeIn;
    if (!inSignal && (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Enter") {
      keyBuf = "";
      if (inSignal) typeIn.blur();
      return;
    }
    if (e.key.length === 1) {
      handleTypeKey(e, e.key);
    }
  });

  initNoise();
  runBoot().catch(() => {
    boot.classList.add("done");
    document.body.classList.remove("no-scroll");
    document.body.classList.add("loaded");
  });
})();
