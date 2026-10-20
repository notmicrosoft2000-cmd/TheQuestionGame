# The Question Game Remastered v3 — Master Plan

Single source of truth for the v3.0.0 remaster. Update checkboxes as phases complete.
Game code: `TheQuestionGameRemastered/` (package). Runner: `run_remastered.py`.

## Hard constraints (from Neptune)

- **Website is sacred.** Root-level `index.html`, `legacy.html`, `css/ js/ img/`,
  `forum-reactions.json`, `bossfight.mp3`, `jumpscare.mp3`, `windowq.png`,
  `logsmusic.ogg` are served by GitHub Pages from the repo root. **Never move/edit
  for the game's sake.** `bossfight.mp3` is also the *website's* easter egg — the
  game has its **own copies** in `TheQuestionGameRemastered/assets/`.
- **Repo layout (post-reorg):** `build/` = CI requirements + `build/mac/` py2app
  scripts; `archive/` = frozen pre-reorg snapshot (never touch); `tools/` =
  gitignored local tooling (cmdtools.zip). CI workflows already updated.
- **TTS is out of scope** — user explicitly doesn't care. Keep existing
  `whisper_text`/`speak_text` as-is, do not expand.
- Classic (`games/classic/TheQuestionGame.py`) is the *feel* reference; current
  remastered code is the *architecture* reference. Port mechanics, not spaghetti.
- v2.04 = "over-sanitized" rewrite. v3 = v2's clean code + Classic's bite.

## Goal list (user's asks)

1. Fix lag/performance (game stutters badly today)
2. Different AI provider (currently Groq llama-3.3-70b — swap needed)
3. Restore core music (logsmusic menu/ambience, bossfight run-3, jumpscare SFX)
4. Bring back easter eggs (2013/LOGS cheat, badges, false memory, process-awareness)
5. More visuals + better scares
6. More window movement / OS manipulation
7. Lock window to fixed size; remove min/max/close buttons (frameless)
8. Unclosable like Classic, but worse — only Task Manager kill works

## Current progress

**v3.0.0 is feature-complete. All phases below are DONE.** This build replaces
the v2.04 remastered release.

- [x] Phase 0: repo reorganization (build/ archive/ tools/, CI paths fixed)
- [x] Phase 1: performance / lag fixes — **DONE 2026-10-18** (see table below)
- [x] Phase 2a: audio.py music manager (play_music/stop_music/play_jumpscare/
      play_bossfight, `_music_path` asset resolver); assets copied:
      bossfight.mp3, jumpscare.mp3, courier.ttf
- [x] Phase 2b: multi-provider ai_client + provider chosen (Groq free tier,
      openai/gpt-oss-120b) — live AI verified end-to-end
- [x] Phase 3: music wiring (+ bossfight SFX ducking)
- [x] Phase 4a: config.py v3.0.0 + flags (WINDOW_LOCKED, BLOCK_CLOSE_ATTEMPTS,
      CLOSE_RESIST_MAX, ENABLE_TASKMGR_DETECT, ENABLE_DISCORD_DETECT,
      MUSIC_ENABLED) + new AI scare names (window_teleport, window_drift,
      rgb_split, screen_tear, jumpscare)
- [x] Phase 4b: NOFRAME window lockdown
- [x] Phase 5: unclosable close-resistance escalation
- [x] Phase 6: OS manipulation expansion
- [x] Phase 7: visuals & scares (+ webcam distortion)
- [x] Phase 8: easter eggs & badges
- [x] Phase 10: Classic bite — dynamic/contradiction/callback questions
- [x] Phase 9: escalation pacing & polish
- [x] Phase 11: packaging & release (Windows/macOS/Linux builders)
- [x] Phase 12: location/nation awareness + Windows-first bite

## Phase 1 — Performance / lag fixes  ← DONE (2026-10-18)

Headless profile (SDL dummy driver):

| Metric | Before | After |
|--------|--------|-------|
| Startup (script build) | minutes — 12 blocking HTTP calls | ~110ms |
| Frame time (PLAYING) | 25.7ms (~39fps) | ~2.0–2.7ms (holds 60fps) |

Biggest offenders found by profiling the render path:

| # | Hotspot | Fix |
|---|---------|-----|
| 1 | **Startup stall: `script.build_session` makes up to 12 blocking Groq HTTP calls** (30s timeout each) before the game even shows Q1 | Lazy generation: script returns `ai_pending` placeholders; main fetches each question in a background thread while THINKING dots show; also prefetch next 1–2. Bonus: real answers now feed AI context (v2 sent `"(recorded)"` stubs!) |
| 2 | `Game._fonts()` constructs 3 `pygame.font.Font` objects **per call**, and `_draw` calls it 4–6×/frame | Cache fonts keyed by (w, h, text_size); rebuild only on resize/setting change |
| 3 | `ui.apply_vignette` builds a full RGBA numpy array + `frombuffer` + `.copy()` every frame | Pre-render vignette surface per (w,h) once; blit with breathing `set_alpha(amt)` |
| 4 | `ui.apply_vhs_effects` draws ~150–600 `draw.line` calls/frame for scanlines | Pre-render scanline overlay per (w,h,step); single blit |
| 5 | `ui.draw_starfield` creates 2×3 SRCALPHA galaxy surfaces **per frame** | Pre-render galaxy blobs in `build_starfield`; blit cached |
| 6 | `render_wrapped_text`/`render_animated_wrapped_text` re-render every glyph every frame | New `ui.render_text_block`: caches rendered line surfaces per (text, font, color, width); sway/alpha applied at blit time. Prune cache >400 entries |
| 7 | `draw_dust`: `set_at` per particle/frame; 42 particles | Pre-render white dot sprites per size, tint via BLEND_RGBA_MULT blit; count 42→28 |
| 8 | `apply_shadow_static` builds a fresh SRCALPHA blob surface (40 rect fills) per trigger | Pre-generate 3 blob sprites lazily; blit at random pos |
| 9 | `apply_flicker` does ~50 `set_at` full-screen noise pixels/frame | Pre-render 96×96 noise tile once; blit 2–4× at random offsets (strobe fills kept) |
| 10 | `_draw_fade` / pending-exit overlay allocate `pygame.Surface((w,h))` per frame | Cache one black overlay surface per size |
| 11 | Double `poll_picture_result()` call per frame in run loop | Single call |
| 12 | Cached SRCALPHA surfaces not in display format → pygame re-converts **every blit** (vignette alone was 23ms/frame) | `convert_alpha()` on all cached surfaces (vignette: 24ms → 1.5ms) |
| 13 | `s.play().set_volume()` raised when mixer channels exhausted — scares failed silently | `_safe_play()` guard + 16 mixer channels |
| 14 | AI provider chain looped forever when all providers failed — THINKING dots never resolved | Each provider tried exactly once per call, then offline bank; timeout 30s→12s |

**Verified:** smoke test (boot <200ms, 120 frames @ ~2ms, all 18 scares fire,
close-resist ×8 never exits, config/registry sync) + integration test (full
19-step session answered end-to-end, real answers in history, run advances).
Tests isolated via `TQG_DATA_DIR` env override.

## Phase 2 — AI provider swap  ← DONE

- [x] Multi-provider client: `config.AI_PROVIDERS` (groq / openrouter / openai /
      deepseek / ollama — all OpenAI-compatible), selected via `TQG_AI_PROVIDER`,
      tried in order with offline bank backstop. `TQG_*_KEY` env vars override.
- [x] System prompt updated with the 5 new scare names + brevity rules
      (1 question, 1-4 word options) + output clamped in `_parse` so a chatty
      model can't blow out the question/option UI
- [x] Real answers now sent as AI context (was `"(recorded)"` stubs)
- [x] **RESOLVED (Neptune): stay on Groq's free tier.** The old embedded key was
      dead (HTTP 401), so the game was silently using the offline bank every
      session. Replaced with a working free key and swapped the model:
      `llama-3.3-70b-versatile` is no longer offered on the account →
      **`openai/gpt-oss-120b`** (tested 6/6 valid JSON, ~0.9s, on-brand voice).
      Groq's current catalog also has `openai/gpt-oss-20b` and `qwen/qwen3.8-27b`
      (faster but occasionally dumps huge graphic paragraphs — rejected).
- [x] `TQG_AI_PROVIDER=auto` prefers a usable local Ollama model, else
      OpenRouter when keyed, else Groq. The installed `qwen3:1.7b/4b` are
      thinking-only builds (reasoning leaks as the answer, ~7-13 tok/s) and are
      auto-skipped.
- [x] Live-AI verified: 16/18 questions in a session came back tagged
      `ai:openai/gpt-oss-120b`, correctly following the player's earlier answers.
- [ ] NOTE: the website's `js/config.js` still holds the same DEAD key — the
      site's AI easter egg is broken too. Left untouched (website is sacred);
      needs Neptune's say-so to fix.

## Phase 3 — Music & ambience wiring  ← DONE

- [x] LOGS → logsmusic (already); PLAYING/TITLE run≥3 → bossfight loop;
      other states → stop_music. `_draw_loading` now calls `_on_state_enter`
      so run-3 music starts at boot.
- [x] jumpscare.mp3 cached + played by the `jumpscare` scare
- [x] Duck SFX channel during bossfight — `audio.set_sfx_duck()`; `_safe_play`
      and the jumpscare both scale their volume by `config.SFX_DUCK_UNDER_MUSIC`
      (0.55) while bossfight plays, restored to 1.0 elsewhere (`_on_state_enter`)

## Phase 4 — Window lockdown  ← DONE

- [x] `pygame.NOFRAME` when WINDOW_LOCKED (no titlebar ⇒ no min/max/close
      buttons on all platforms); VIDEORESIZE ignored when locked
- [x] Window stays movable via SetWindowPos (scares depend on it)
- Note: WS_SYSMENU clearing unnecessary — NOFRAME removes the caption
  entirely; there is no close button to click in the first place.

## Phase 5 — Unclosable, but worse  ← DONE

- [x] `_resist_close()`: QUIT, Alt+F4, menu EXIT, ESC all route here;
      never sets `running=False` (endings still exit normally)
- [x] Escalation: 1–2 message+error sound; ≥3 corruption burst + glitch +
      window shake; ≥5 teleport + static scream; ≥7 mouse nudge + OS
      notification "You cannot leave."; ≥CLOSE_RESIST_MAX periodic drift
- [x] Rotating close messages (`get_close_intercept_message(attempt)`)
- [x] Task Manager awareness: background process cache → "The Task Manager
      will not help you." whisper + corruption + `task_manager` badge
- [x] Discord running → `not_alone` badge

## Phase 6 — OS manipulation expansion  ← DONE

- [x] `teleport_window_random()` + `drift_window(duration)` in os_layer
- [x] Wired as `window_teleport` / `window_drift` scares
- [x] `comment_on_open_apps()` one-shot beat (run 2+, after 12s)
- [x] Tab-out response: "You were gone N seconds. Where." + corruption
      (idle_tracker `pending` flag was set but never consumed before)

## Phase 7 — Visuals & scares  ← DONE

- [x] `ui.apply_rgb_split` (channel offset, sine-animated amount)
- [x] `ui.apply_screen_tear` (horizontal slice displacement)
- [x] Scare registry: +window_teleport, window_drift, rgb_split, screen_tear,
      jumpscare (18 total; config/registry sync asserted by test)
- [x] 6s per-name cooldown in `apply_scare` (stacking guard)
- [x] Run 3 low-grade trickle: every 4–9s a small corruption/rgb/flicker
- [x] Webcam feed distortion — `ui._distort_webcam()`: rolling numpy glitch
      bands + a periodic full-frame inversion on the live feed
      (`config.WEBCAM_DISTORTION`)

## Phase 8 — Easter eggs & badges  ← DONE

- [x] 2013 cheat → LOGS (already in v2, kept) → now awards `the_archivist`
- [x] Badges: the_archivist, not_alone, task_manager added to catalog
      (+ `patient_one` added in Phase 10)
- [x] False-memory beat: 18% chance after an answer it quotes an EARLIER
      real answer back — 'You said "X." You said it twice.'
      (+ Phase 10 adds the Classic *question* form with rebuttals)
- [x] LOGS entries: +3 new (ENTRY 166 close-spam teleport, 172 camera,
      203 no titlebar buttons)

## Phase 10 — Classic bite: dynamic / contradiction / callback questions  ← DONE

The actual personality fix — Classic's teeth, ported onto v3's clean code.
New module `interjections.py` holds the content; `script.py` authors the
openings; `main.py` drives resolution and insertion.

- [x] **Dynamic questions** built from real machine state, resolved off-thread
      like the AI placeholders: `DYNAMIC_PROCESSES` ("Roblox/Discord/Telegram
      is running…"), `DYNAMIC_LOCATION` ("Are you currently in {city}?" with a
      denial rebuttal), `DYNAMIC_APPS` (run 2).
- [x] **Contradiction callbacks**: `alone2` ("Are you alone?") rewritten at
      display time against the earlier `alone` answer, and a lie is recorded
      (`lie_count`, feeds the run-3 reveal). Discord-running + claimed-alone →
      "If you were truly alone, who exactly were you about to talk to?"
- [x] **Conditional questions**: `_condition` support in the step engine — e.g.
      "Are the blinds open?" only appears when "Is there a window?" = Yes
      (skipped by `_skip_inactive()` at build and on advance).
- [x] **Injected lore lines**: "They told us you would say that.", "This is not
      the first time we've spoken.", "You are doing exactly what the last one
      did."
- [x] **Tailored answer reactions** for the opening's questions (alone / dark /
      hurt / lied / siblings / window / why-return); thinned to 65% so the
      short opening doesn't feel like call-and-response.
- [x] **Hesitation call-out** (Classic's 20s threshold) after a slow answer.
- [x] **`patient_one` badge** — spent over a minute on a single question.
- [x] **False-memory question** form once per save (with "I have it written
      down" rebuttals), falling back to the ambient whisper.
- [x] **`desktop_check` action** (run 2): captures the foreground window title,
      slides the window aside to expose your desktop, then returns.
- [x] **Task Manager comment** injected as a question, not just a whisper.
- [x] **Background interference**: cmd flash every ~30s + random error beep
      (15–45s), so the machine never feels fully at rest.
- [x] New config flags: `ENABLE_DYNAMIC_QUESTIONS`, `ENABLE_CONTRADICTIONS`,
      `ENABLE_HESITATION_CALLOUT`, `ENABLE_BACKGROUND_INTERFERENCE`,
      `HESITATION_THRESHOLD`, `PATIENT_ONE_THRESHOLD`,
      `BACKGROUND_INTERFERENCE_INTERVAL`, `BACKGROUND_BEEP_INTERVAL`.
- [x] Headless harness `/tmp/opencode/bite_check.py`: 33 checks — script
      structure, interjection logic, a full run-1 drive (conditions, dynamic
      resolution, contradiction rephrase, reactions) and the patient_one badge.

## Phase 9 — Escalation pacing & polish  ← DONE

- [x] Run 3: constant low-grade corruption + bossfight + aggressive shake
- [x] Headless smoke + integration tests; `TQG_DATA_DIR` override so tests
      never touch real save data (`~/.tqgame_remastered`)
- [x] readme_remastered.txt updated for v3 (window lock, effects list,
      providers, TQG_DATA_DIR, corrected requirements path)
- [x] FPS assert in CI — committed as `games/remastered/tests/smoke_test.py`
      (asserts boot <2.5s, frame avg <12ms, all scares, close-resist,
      reset/badges, bite structure) run by `.github/workflows/test-remastered.yml`
- [x] Reset All Data / badge persistence verified — automated in the smoke test
      (reset clears answers + resets `run_count`, badges survive)

## Phase 11 — Packaging & release  ← DONE (config); binaries via CI

- [x] **Windows builder was missing entirely** — the `.spec` file existed but no
      workflow used it. Added `.github/workflows/build-windows-remastered.yml`
      (PyInstaller → `TheQuestionGameRemastered.zip` containing the `.exe` +
      `readme.txt`) and `build/requirements-windows.txt`.
- [x] `.github/workflows/test-remastered.yml` — runs the committed smoke test on
      every push/PR touching `games/remastered/**` (the CI FPS gate).
- [x] macOS `build/mac/setup-remastered.py` version bumped 2.02 → **3.0.0**
      (and `CFBundleShortVersionString` / `CFBundleVersion`).
- [x] Linux + macOS builders already existed
      (`build-linux-remastered.yml`, `build-mac-remastered.yml`) and trigger on a
      published release whose tag contains `remastered`.
- Builders only run on GitHub's servers (Windows on Windows, macOS on macOS).
      To produce downloads: publish a `v3.0.0-remastered` release, or run the
      three build workflows via **Actions → Run workflow**.

## Phase 12 — Location, nation & Windows-first bite  ← DONE

Neptune's follow-up asks, all landed on top of the same v3.0.0 release:

- [x] **Windows-first scares.** Two new Windows-only effects join the registry
      (now 20): `windows_shake` (shakes every *other* open window) and
      `windows_minimize` (minimizes everything else, leaving you alone with it).
      Added `os_layer.minimize_other_windows()`; both degrade to no-ops off-Windows.
- [x] **Harder to close.** `_resist_close` now also re-asserts `HWND_TOPMOST`,
      flashes the taskbar entry (≥2), forces the window to the foreground (≥4),
      teleports + shakes more (≥12), and enters a constant-drift phase at
      `CLOSE_RESIST_MAX` (raised 20 → 30). Added Windows-specific close taunts
      ("Right-click the taskbar all you like…", "The system menu is empty now…").
      `disable_system_close()` kills the SC_CLOSE item from the system menu, and
      a topmost-keeper thread (`start_topmost_keeper`) keeps the window on top.
- [x] **Location, accurately.** `os_layer.fetch_geo()` now queries several
      keyless IP-geolocation providers (ipwho.is → ip-api.com → ipinfo.io) and
      returns city / region / country / country_code / lat / lon / timezone.
      Live-verified: **Yangon, Myanmar (MM)**.
- [x] **Country flag.** `ui.prefetch_flag()` downloads the flag PNG from
      flagcdn.com and caches it to disk; `ui.draw_location_card()` shows a
      "LOCATED: City, Country" card with the flag and coordinates while the
      location question is on screen.
- [x] **Nation-tailored AI.** The resolved location is passed into
      `ScaryAI._context_messages`, so the entity references the player's country
      obliquely (`AI_TAILOR_TO_NATION`). Also added an author-side
      `build_nation_callback()` line injected after the location question.
- [x] **Camera, in the original's spirit.** Run 1 now has its own camera beat
      ("I am turning the camera on now. I would like to see who is answering.")
      via `start_webcam`, alongside the existing run-2 / run-3 camera moments.
- [x] New config: `KEEP_WINDOW_ON_TOP`, `ENABLE_LOCATION`,
      `ENABLE_COUNTRY_FLAG`, `AI_TAILOR_TO_NATION`.
- [x] Smoke test extended: geo normalisation, location card render, flag
      fallback, camera intro, nation callback, AI nation context, 38-attempt
      close-resist stress. Full-session integration drive: 35 steps, camera
      fired, location card shown, clean end.

## Verified-safe facts (from code reading)

- `os_layer.check_processes()` already detects taskmgr/discord/telegram/roblox
  on Win+mac; `_refresh_processes_loop` already runs every 4s → taskmgr scare
  needs zero new detection code, just consumption.
- `nudge_mouse_from_close()` already repels cursor from the (future) close area.
- `attempt_close_with_warning()` currently just plays error + returns False.
- `ui.py` webcam path already thread-offloaded (queue, maxsize=1) — fine.
- `persistence.py` badges live in own file, survive Reset All Data — keep.
- CI: mac icon build uses `games/remastered/.../assets/windowq.png` (unaffected);
  classic Linux bundles root `windowq.png logsmusic.ogg` (unaffected).

## Phase 13 — Bug hunt (pre-binary)

A broad hunt across every module (lint, cross-reference sweep, uninitialised
attributes, full three-run playthroughs, all menus, close storms, every scare,
every render state). Bugs found and fixed:

- **Dust corrupted itself to black.** `ui.draw_dust()` called
  `sprite.fill(color, BLEND_RGB_MULT)` on the *shared cached* dot sprite, so
  every particle multiplied it darker — after a few frames all dust was black
  and the cache was destroyed. Added a separate quantised tint cache
  (`_get_tinted_dot`) and never mutate the base sprite.
- **Display calls off the render thread.** `ui.request_picture_scaled_async`
  ran `convert_alpha()` (needs the display) on a worker thread — a crash risk.
  The worker now only loads/scales and hands back raw bytes; the main thread
  builds the surface in `poll_picture_result()`.
- **64-bit Windows handle truncation.** The new `windows_shake` /
  `windows_minimize` scares declared `EnumWindows` callbacks as `c_int`, which
  truncates HWNDs on 64-bit Windows (handles stop matching, scares silently do
  nothing). Added `os_layer._user32()` which sets correct pointer argtypes once,
  and a shared `_enum_visible_windows()` helper; routed every Win32 window call
  through it (topmost, flash, foreground, system-menu, rect, teleport, jiggle,
  foreground-title).
- **Fragile `ctypes.wintypes` import.** Used but never imported; added an
  explicit guarded import.
- **`_mk_error()` int16 overflow.** Two summed sines (±2) written to `int16`
  without clipping wrapped around into harsh aliasing; now `np.clip`ped.
- **Logs unlock not restored.** `logs_unlocked` was never pushed back into
  `menu_options` at startup → LOGS vanished on relaunch.
- **Shared `DEFAULT_STATE` list mutation.** A shallow `dict()` copy meant
  `lie_ids` could be mutated on the module default; now deep-copied in
  `load_game_state` / `reset_all_data`.
- **Close messages rendered single-line but contained `\n`.** Sanitised at draw
  time (whisper text too).
- **Location card overlapped the question.** Moved to the top-right and cached.
- **`prefetch_flag` called `convert_alpha()` off-thread.** Worker now
  downloads-to-disk atomically; main thread converts.
- **Redundant/leftover code.** Removed an unused `cc`, a dead ternary in
  `build_nation_callback`, and unused imports/variables/`global`s. `pyflakes` is
  now clean across the package and tests.
- **CI packaging.** `build/requirements-windows.txt` was git-ignored, so the new
  Windows workflow would fail to find it; force-added it (the other
  `build/requirements-*.txt` are tracked the same way).

Verification: `games/remastered/tests/smoke_test.py` → `SMOKE_OK`; the local hunt
harness → `HUNT_OK` (runs 1/2/3 complete, menus reachable, 40-attempt close
storm refused, all 20 scares fire, every state draws, every cross-module
attribute resolves, every awarded badge is in the catalogue, the AI prompt lists
every scare).

## Phase 14 — Feel & feedback pass (v3.0.1)  ← DONE

Player-feedback batch. All changes are local/uncommitted.

- **AI never saw the latest answer.** `_update_playing` prefetched
  `self.current_step + 1` while the current question was still on screen, so an
  AI question was generated *before* the player answered the one before it — the
  model always ran ~2 questions behind. Now only answer-independent
  `dynamic_pending` beats are prefetched; AI questions are generated the moment
  they become current (THINKING dots cover the wait), from the full, up-to-date
  `session_history`. `config.AI_PREFETCH_LOOKAHEAD` (default `False`) restores
  the old behaviour if wanted.
- **Text clipping / overlap ("clipping under the other").** The answer options
  were placed using `len(text.split("\n"))` — hard newlines only — so any
  soft-wrapped question drew its options straight on top of itself. Added
  `ui.wrapped_line_count()` (shares the render cache) and sized the question by
  its *visual* height, with an on-screen clamp that tightens the row gap instead
  of overlapping. Same bug fixed in `_draw_logs` (wrapped entries overlapped the
  next entry).
- **"Where's the logmusic?"** Runs 1-2 and every menu were silent (only the LOGS
  screen and run 3 had music). `logsmusic.ogg` now scores the title screen and
  runs 1-2 (at a lower in-game volume), run 3 keeps `bossfight.mp3`.
  `audio.play_music` no longer restarts a track that is already playing, so
  title→play transitions don't reset the song.
- **More CRT.** New `ui.apply_crt()` finishing pass: phosphor RGB triad mask,
  curved-tube edge fall-off on all four borders, a slow rolling refresh bar
  (all pre-rendered per window size, a few blits/frame). Gated by
  `config.CRT_ENABLED` and scaled by the VHS Effects setting.
- **Window floats up/down (Windows + macOS).** `os_layer.start_window_float()`
  runs a gentle sine bob around an anchor; the window also jumps to a fresh
  random spot near dead-centre each time a question lands
  (`move_window_near_center()`). Shake/teleport/drift pause the float so they
  don't fight. Deliberately a no-op on Linux (Wayland forbids self-positioning).
- **Endings make the session boundary explicit.** Each ending now tells the
  player to close the window and reopen for the next session (run 3: do not open
  it again), and the black exit fade repeats the instruction.
- **Closing is angrier.** Reaching for the close button now reacts immediately:
  a red flick, a hissed line (`_ANGRY_CLOSE_LINES`), an error sting and a
  visible shudder — before the old escalation (taskbar flash, corruption,
  teleport, cursor theft, drift) kicks in. Close taunts sharpened too.
- **Music scoped to the menu screens.** Corrected the above: the track now
  scores *only* Settings / About / Help / Logs (`config.MUSIC_MENUS_ONLY`);
  the title screen and all gameplay are ambience + SFX only.
- **Website text movement ported in.** The site's `.glitch` hero effect (base +
  red copy clipped to the top band + cyan copy clipped to the bottom band, with
  occasional jitter) is now `ui.render_glitch_text` / `ui.render_glitch_block`,
  applied to the title lines, every section heading and the question body.
  `ui.scramble_text` reproduces the site's periodic character scramble on the
  title. The existing red bloom sits under both.
- **Real VHS / tube pass.** `ui.apply_vhs_pass` stacks tracking slips, a drifting
  tracking bar, head-switching snow at the bottom, drifting static snow, a real
  barrel bow (`apply_vhs_curvature` — measured 726px wide at the top vs 799px in
  the middle) and the CRT phosphor/edge mask. The VHS Effects setting now scales
  it 0 (Off) → 2.0 (High). Benchmarked at ~1.3-2.4 ms/frame, so it is well
  inside the frame budget.

Verification: `smoke_test.py` → `SMOKE_OK`; hunt harness → `HUNT_OK`;
`/tmp/opencode/verify_changes.py` → `VERIFY_OK` (30 checks, incl. a functional
proof that a generated AI question now receives the player's latest answer);
rendered frames confirm edge fall-off + phosphor triads.



## Phase 15 — Readability, fonts, and harder hardware (v3.0.2)

Playtest round two. The glitch/VHS pass looked right but buried the text, and
the window/reactivity bits needed to be more assertive.

- **Text readability.**
  - The glitch split now paints the red/cyan fringes *under* a crisp, fully
    opaque base copy (`alpha_base` 210 → 255), instead of over it.
  - New 1px dark halo on all body/UI text (`config.TEXT_OUTLINE`,
    `ui.draw_text`, `outline=` on `_get_cached_lines`), so glyphs hold their
    shape on top of static and scanlines.
  - New soft dark wash behind the question + options block
    (`ui.draw_readability_panel`).
  - **Reordered `_draw`**: the scan sweep, dust, vignette and tape head line are
    now painted *before* the state content, so text sits on top of them and the
    vignette no longer dims it. Only the CRT finish (scanlines + VHS pass) stays
    in front, because that is the point of the effect.
- **Font customization.** New **Font** row in Settings: Courier, Terminal, Mono,
  Sans, Serif (with a Comic fallback) — `ui.FONT_CHOICES` / `resolve_font_path`
  / `ui._font`. Fonts are now cached by (label, size) rather than rebuilt every
  frame, which also makes the wrapped-line cache actually hit. **Text Size** grew
  to a fourth step (**Huge**, ×1.6) and `_load_settings_idx` maps it back
  correctly.
- **3D tube is unmissable.** `CRT_CURVATURE` 0.10 → 0.16 (and it now scales
  gently with the VHS setting, capped so the text column never gets pinched),
  stronger edge fall-off, and **rounded tube corners** — the mask blacks out
  everything outside an inscribed circle (`CRT_CORNER_ROUND`), which is what
  actually sells the curve.
- **Static line on the main screen.** `ui.draw_static_line` — a faint drifting
  tape head line, light by design (`config.VHS_STATIC_LINE`), on PLAYING only.
- **Window reacts to input (Windows/macOS).**
  - Answering a question nudges the window by up to ±13px (`os_layer.nudge_window`,
    fired from `_confirm_answer`).
  - Hovering parallax: `os_layer.set_hover_offset` lets the window lean up to
    ±6px toward the cursor (`WINDOW_HOVER_AMPLITUDE`), driven by a `MOUSEMOTION`
    handler and composed into the float loop so the two never fight.
  - Both are safe no-ops on Linux/Wayland.
- **Harder close resistance.** `_resist_close` now tracks a *burst*: attempts
  made within 4s of each other rank up faster, so spamming the button escalates
  several levels per click. Teleport, mouse theft and drift all trigger earlier,
  and every attempt opens with a hissed line plus a violent (40px) shake.
- **Aggressive lines shake the window.** New `_say_aggressive()` sets the
  whisper **and** fires the violent window shake in the same frame. Used by close
  attempts, the Task Manager line, the false-memory line, the idle/"where were
  you" lines, and the entity whispers in `scares._do_whisper`. Wayland forbids
  self-positioning, so it degrades to an in-frame screen shake
  (`fx["screen_shake_until"]` / `shake_amp`) that outranks the run-3 tremor.

Verification: `smoke_test.py` → `SMOKE_OK`; hunt harness → `HUNT_OK`;
`/tmp/opencode/verify_changes.py` → `VERIFY_OK` (**61** checks, incl. font
resolution + caching, corner-masking, close-escalation burst and violent-shake
assertions); curvature geometry and text contrast measured on rendered frames;
the full VHS pass still benchmarks at ~1.3-2.4 ms/frame.

## Phase 16 — Real sound assets, honest title, working EXIT (v3.0.2)

Final round of the requested changes.

- **The main-menu EXIT item works.** `_title_key` now sets `self.running = False`
  for the EXIT option instead of feeding `_resist_close()`. The window's close
  button is still the thing it fights you over — you get out through the menu, or
  not at all.
- **Title wording.** `_TITLE_SUB` R E M A S T E R E D → **"(R)"**, and the
  on-screen title lines are now "THE QUESTION GAME" (they were sentence case),
  matching the website hero. App/bundle names keep "Remastered" so saves and the
  build identity stay stable.
- **Sounds are real files now.** New `sfx_gen.py` renders every effect with numpy
  and writes it to `assets/` (`type`, `ui_nav`, `ui_select`, `mech_beep`, `error`,
  `glitch`, `static_burst`, `heartbeat`, `deep_rumble`, `reverse_chord`,
  `static_scream`, plus a 4s `ambience` bed). Writes MP3 when ffmpeg is present,
  otherwise WAV; the mixer runs 22 050 Hz mono. On first run `audio._load_asset_sounds`
  generates whatever is missing and loads it; after that the files are just files —
  **drop your own `assets/error.mp3` in and it is used instead**. Existing files
  are never overwritten. `start_ambience` now loops `assets/ambience.mp3` instead
  of synthesizing a drone in memory.
- `config.VERSION` and the macOS bundle metadata bumped to **3.0.2**.
- CI: `test-remastered.yml` gained an "audio assets generate + load" step that
  renders every sound into a temp dir and decodes each one with the mixer.
  `build/mac/setup-remastered.py` already ships the whole `assets/` folder.

Verification: `smoke_test.py` → `SMOKE_OK`; hunt harness → `HUNT_OK`;
`/tmp/opencode/verify_changes.py` → `VERIFY_OK` (**73** checks, now including the
EXIT item actually stopping the loop, the title wording, and asset generation /
non-clobbering / decode).

## Phase 17 — The AI becomes visible (v3.0.2)

Playtest note: "I don't notice the AI — every play starts with the same questions."
Both halves of that were literally true, and both are now fixed.

### Why the AI was invisible
- **It was all at the end.** Every run played its 16-question authored block first,
  so the first five minutes of every playthrough *were* identical. The AI only
  appeared afterwards.
- **Nothing ever labeled it.** `_source` was computed and thrown away.
- **Its context was 5 turns of flat text**, so it could not call anything back.
- **Reasoning-model truncation.** `gpt-oss-120b` intermittently emitted an empty or
  cut-off JSON object (or a hidden chain-of-thought), `_parse` returned `None`, and
  the game silently dropped to the offline bank. Measured: roughly half of all AI
  questions were being replaced without anyone knowing.

### What changed
- **Interleaved sessions** (`script._interleave`): AI questions are woven through
  the authored opening, not appended. It opens at authored beat **5 / 3 / 2** for
  runs 1/2/3 (`config.AI_OPENS_AT`) and then alternates every couple of beats.
- **Sessions grow, they don't shrink.** `AI_QUESTION_COUNT` is now **14 / 18 / 26**
  and totals land at **30 / 27 / 33** (was 29 / 19 / 15). The real ending is the
  longest session, not the shortest.
- **Real context** (`ai_client._context_messages`): full-session history (not 5),
  the player's OS name (`os_layer.get_cached_username`, filtered against generic
  accounts), open apps, prior-session answers, hesitation/contradiction counts, and
  the list of effects already spent so none is reused. The system prompt now states
  the three-session escalation arc outright.
- **Escalating scares**: `config.SCARE_FLOOR` (2 / 5 / 9) guarantees each run lands
  effects even when the model keeps answering "none", drawn only from
  `SCARE_FLOOR_POOL` — safe tone effects, never webcam/jumpscare/wallpaper/windows_*.
- **Robust parsing**: `ai_client._salvage_step` repairs truncated JSON, curly quotes,
  prose-wrapped objects, and out-of-range scare names instead of discarding them;
  `_post` reads the `reasoning` field when `content` holds no JSON and honours each
  provider's `extra` body fields (`reasoning_effort`). Measured AI success went
  **~50% -> 7/8** in a live run.
- **Runs 2 and 3 quote you back** (`script._remembered_answers`): run 2 opens with
  "We kept what you gave us: your color: blue / the window: Yes / being alone: Yes",
  and run 3 adds the counts plus everything stored from session one. Offline scare
  chance also escalates (0.25 / 0.5 / 0.75).

Verification: `smoke_test.py` -> `SMOKE_OK`, now including interleave order, the
growth curve, context contents, salvage-parser repair, and the scare floor.
