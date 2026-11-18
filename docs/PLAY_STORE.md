# Google Play Store prep — The Question Game Remastered

Everything technical for a Play upload is prepared **outside** this repo (the
signing key lives in `~/android/`). This file is the hand-off: what is ready,
what still needs a human with a Play Console account, and what to say in the
Console forms.

## Status

| Item | State |
|---|---|
| Signed 64-bit APK for itch.io | **done** — `games/remastered/bin/TheQuestionGameRemastered-Android-7.0-beta-arm64-v8a.apk`, also attached to the GitHub release |
| Target API 36 (Play's 2026 requirement) | `android.api = 36` in `buildozer.spec` |
| 64-bit ABI | `arm64-v8a` (switch `android.archs` back to `arm64-v8a, armeabi-v7a` for a universal build) |
| App Bundle instead of APK | deferred — Play Console is not available; switch `android.release_artifact = aab` if that changes |
| Upload signing key | `~/android/tqg-upload.jks` |
| Play Console account | **not done — needs you** (identity + $25 fee) |
| Store listing / screenshots / policy forms | **not done — needs Console access** |

## The signing key (keep this safe)

- Keystore: `/home/neptune/android/tqg-upload.jks`
- Alias: `tqg-upload`
- Passwords: `/home/neptune/android/tqg-release.env` (`chmod 600`, never in git)
- SHA-256 certificate fingerprint:
  `8C:56:D8:85:49:1C:2B:FD:10:9A:8E:98:A8:65:75:94:B5:7F:14:12:02:C2:A0:C1:71:79:9A:3A:6B:62:D9:71`
- Valid until 2054-04-05.

Back up the `.jks` and `.env` somewhere durable. If they are lost and the app
is published, you cannot ship an update. When you first upload, **enrol in
Play App Signing** — Google then holds the app-signing key and this one becomes
your upload key, so losing it is recoverable.

## Rebuilding the signed APK

```sh
cd games/remastered
./build_android.sh android release
```

`build_android.sh` sources `~/android/tqg-release.env` automatically and sets
Java 21. Output lands in `bin/`. For a local debug APK (single ABI, for a
32-bit test phone) use `./build_android.sh` with no arguments.

To verify the release APK locally:

```sh
BT=~/android/sdk/build-tools/36.0.0
APK=bin/TheQuestionGameRemastered-Android-7.0-beta-arm64-v8a.apk
$BT/apksigner verify --print-certs "$APK"
$BT/aapt dump badging "$APK" | grep -E 'package:|targetSdkVersion:|native-code:'
```

## itch.io (the usable route right now)

A Play Console account needs an adult account owner and a $25 fee, so it is
not available here. **itch.io accepts a signed APK directly with no fee** and
is the publishing target for this build.

- Upload the signed arm64 APK
  `games/remastered/bin/TheQuestionGameRemastered-Android-7.0-beta-arm64-v8a.apk`.
  It is already attached to the GitHub release under the same name.
- Set the platform to **Android** and mark it as an APK (not a bundle).
- The 32-bit APK `TheQuestionGameRemastered-Android-7.0-beta.apk` is attached to
  the same release and can be uploaded as a second file for older phones —
  itch.io lets you offer multiple downloads and label them.
- itch.io has no data-safety questionnaire, but the "no malware" line in the
  description still matters, and the same screenshots/graphics apply.
- A 64-bit build is also what modern phones (Android 11+ devices shipped since
  ~2019) need; the 32-bit APK only covers older hardware.
- A ready-to-paste HTML description is in `store-assets/ITCH_IO.html`. It has
  six Android captures plus two GIFs in `store-assets/`, and the same six plus
  two GIFs for the desktop build in `store-assets/desktop/`. Replace the `src`
  paths with the URLs itch gives you when you upload the images.

## Store listing copy

**App name** (30 chars max): `The Question Game Remastered`

**Short description** (80 chars max):
```
A horror quiz that learns what scares you. Answer the questions. It watches.
```

**Full description** (4000 chars max):
```
The Question Game is a horror quiz that gets to know you while it asks.

Three runs. Twenty-two, thirty-two and forty-six written questions. Every
answer you give changes what comes next — the questions, the tone, and the
things that happen between them. Say the same thing twice and it notices.
Hesitate and it notices that too.

It is an AI, and it is watching. The questions are generated for you from your
answers, your location and a few things your device knows about you. The
further you get, the less it feels like a quiz and the more it feels like
something is on the other side of the screen.

On a phone, the desktop tricks change shape instead of disappearing. Window
shakes become screen shakes. A stolen cursor becomes your answer selection
moving by itself. Wallpaper changes become corruption and flicker. There is a
watching eye in the corner that follows what you highlight and blinks when the
game does something frightening.

Features:
- Three progressively longer runs with dynamically generated questions
- A game that remembers every answer, every hesitation and every contradiction
- An eye that watches the screen and reacts to what you do
- Rebindable keys, photosensitivity switches, volume and graphics settings
- Runs offline with built-in questions, or connects to the AI relay
- An optional room of other players, where a hidden operator can send questions

The game is a prank. It is not malware. It does not hide, it does not steal
your data, and it does not need root. Everything it learns stays on your
device unless you switch on the online room.

CONTROLS: tap an answer, tap a menu row, use Back to leave a screen, and use
the visible PAUSE button while playing. The game runs in landscape and keeps
the screen awake.

NEEDS: Android 7.0+ (API 24), arm64 or arm32. Internet is optional but needed
for AI-generated questions and the online room.

Privacy policy: <publish a URL before submitting — see below>
```

**Category:** Game / Puzzle or Game / Trivia. **Content rating:** likely
**Mature 17+** (horror, jump scares, flashing effects). **Target audience:**
18+ — do NOT mark as "families"; the horror content and Data Safety answers
will conflict.

## Screenshots and graphics

Play needs an icon (512×512 PNG), a feature graphic (1024×500 JPG/PNG) and at
least two screenshots (min 320 px). Existing candidates in this repo:

- `games/remastered/TheQuestionGameRemastered/assets/windowq_70.png` — 256×256
  app mark; upscale/re-render to 512×512 for the store icon.
- `img/evidence-title.png`, `img/evidence-question.png`,
  `img/evidence-settings.png`, `img/evidence-help.png` — 1600×1200 (**desktop**
  captures, landscape).

Prefer **real phone screenshots** from the Android build — use `adb exec-out
screencap -p > shot.png` on a connected device. Desktop captures are a policy
risk if the listing implies they are phone gameplay.

A 1024×500 feature graphic still needs to be made.

## Data Safety (answer exactly)

| Question | Answer |
|---|---|
| Data collected | **Approximate location** (coarse, inferred from IP) and **User content** (your answers and any chat in the online room) |
| Purpose | App functionality — questions are tailored to your location and answers |
| Is data encrypted in transit? | **Yes** (HTTPS to the AI relay, geolocation providers and GitHub; one legacy `http://` geolocation endpoint exists as a last-resort fallback — remove it before submitting) |
| Is data shared with third parties? | **Yes** — the AI relay/model provider receives prompts containing location and answer history; geolocation providers receive your IP |
| Deletion available? | In-app settings clear local save data; server-side room data is not retained by design |
| Account required? | No |
| Camera / microphone / contacts | **No** — the Android build swaps camera scares for visual effects; `CAMERA` should be removed from the manifest before submission |

The app calls `https://ipwho.is/`, `https://ipinfo.io/json` and
`http://ip-api.com/json/` for geolocation, a Tailscale-hosted AI relay for
questions, the GitHub releases API for update checks, and `flagcdn.com` for a
country flag image. A privacy policy URL covering these must be published and
entered in the listing.

## Policy risks to resolve before submitting

1. **Camera permission declared but unused on Android.** Remove `CAMERA` from
   `android.permissions` in `buildozer.spec` and rebuild. Unused sensitive
   permissions are a common rejection reason.
2. **Plain-HTTP fallback** in `os_layer.py` (`http://ip-api.com/json/`). Either
   drop that provider or mark the app's Data Safety as not fully encrypted.
3. **"Malware alpha" / "it is inside your machine" copy.** Fine as fiction, but
   the listing must state plainly that it is a game and not malware (the draft
   above does). Avoid system-level scare language in the description.
4. **Scary content / flashing effects.** Photosensitivity switches exist in
   game; set Mature 17+ and disclose flashing effects.
5. **No privacy policy yet.** Required when any data is collected. Publish one
   on the project site first.

## Uploading (once you have Console access)

1. Create the app in Play Console using package name
   `org.ntg.thequestiongameremastered`. Package names cannot be changed later.
2. Enrol in **Play App Signing** on first upload.
3. Upload the signed `.aab` from `games/remastered/bin/`.
4. Complete Store listing, Content rating questionnaire, Data Safety form,
   Target audience, and App access (no special access needed — relay works
   without credentials; say so honestly).
5. Add the privacy policy URL.
6. Run a closed test with at least 12 testers for 14 days (Google's rule for
   new personal accounts), then submit for review.

## If you cannot create a Play Console account

You don't have to give up on distribution:

- A parent, guardian, or another adult with a Google account and a payment
  method can own the Console account and add you as a **developer/admin**.
- A school, club, or employer with a Google Workspace can own it.
- Other stores accept the APK directly with no $25 fee: **itch.io**,
  **F-Droid** (needs a build recipe), **APKMirror** (needs an established app),
  or your own site (already done — the GitHub release link).
- If you are under 18, Google requires an adult account owner regardless;
  there is no workaround, so use one of the options above.
