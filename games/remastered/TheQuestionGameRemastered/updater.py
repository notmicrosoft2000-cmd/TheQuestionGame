"""Automatic update checks against the project's GitHub releases.

The checker runs on a background daemon thread, so a slow or offline network
never stalls a frame. It only *reports* an available release: the player
decides whether to open the download page. Nothing is downloaded, replaced or
installed silently.

Versions are compared numerically, with alpha < beta < rc < final. The
``-remastered`` suffix identifies the release series and is ignored.
"""
import json
import os
import platform
import re
import threading
import time
import urllib.request

from . import config

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?")
_PRERELEASE_RANK = {"alpha": 0, "beta": 1, "rc": 2}


def parse_version(text):
    """Return ``((major, minor, patch, build), prerelease_rank)`` or None.

    ``v6.1-alpha-remastered`` -> ``((6, 1, 0, 0), 0)``
    ``6.1``                   -> ``((6, 1, 0, 0), 3)``
    """
    s = str(text or "").strip().lower()
    match = _VERSION_RE.search(s)
    if not match:
        return None
    numbers = tuple(int(match.group(i) or 0) for i in range(1, 5))
    suffix = s[match.end():]
    rank = 3
    for label, value in _PRERELEASE_RANK.items():
        if label in suffix:
            rank = value
            break
    return (numbers, rank)


def is_newer(remote, local):
    """True when ``remote`` is a later version than ``local``."""
    remote_version = parse_version(remote)
    local_version = parse_version(local)
    if remote_version is None or local_version is None:
        return False
    return remote_version > local_version


def display_version(tag):
    """A tag without the leading ``v`` or the edition suffix, for the UI."""
    text = re.sub(r"[-_ ]?remastered$", "", str(tag or "").strip(), flags=re.IGNORECASE)
    return text.lstrip("vV")


def _is_remastered(release):
    tag = str((release or {}).get("tag_name") or "")
    return "remastered" in tag.lower()


def _asset_url(release, system=None):
    """Best download URL for this platform, or "" when the release has none."""
    system = str(system or platform.system()).lower()
    if "windows" in system or system == "win":
        extensions = (".zip",)
    elif "darwin" in system or "mac" in system or system == "macos":
        extensions = (".dmg",)
    elif "android" in system:
        extensions = (".apk",)
    else:
        extensions = (".tar.gz",)
    for asset in (release or {}).get("assets") or []:
        name = str(asset.get("name") or "").lower()
        if name.endswith(extensions):
            return str(asset.get("browser_download_url") or "")
    return ""


class UpdateChecker:
    """Non-blocking GitHub release checker.

    Typical use::

        checker = UpdateChecker()
        checker.start()
        ...
        info = checker.poll()      # once, when a newer release appears
        if info:
            open_in_browser(info["url"])
    """

    def __init__(self, current_version=None, repo=None, api_url=None,
                 timeout=None, interval=None, enabled=None, state_path=None):
        self.current_version = str(current_version or config.VERSION)
        self.repo = str(repo or config.UPDATE_REPO)
        self.api_url = str(api_url or config.UPDATE_API_URL)
        self.timeout = float(config.UPDATE_CHECK_TIMEOUT if timeout is None else timeout)
        self.interval = float(config.UPDATE_CHECK_INTERVAL if interval is None else interval)
        self.enabled = bool(config.UPDATE_CHECK_ENABLED if enabled is None else enabled)
        self.state_path = state_path
        self.available = None        # dict once a newer release is found
        self.last_error = ""
        self._lock = threading.Lock()
        self._thread = None
        self._reported = False
        self._next_attempt = 0.0
        self._load_state()

    # --- scheduling ---------------------------------------------------------
    def start(self):
        """Kick off a check if one is due. Never blocks."""
        return self.maybe_check()

    def maybe_check(self, now=None, force=False):
        """Start a background check when enabled and due. Returns True if it did."""
        if not self.enabled:
            return False
        now = time.time() if now is None else float(now)
        with self._lock:
            if self.available is not None and not force:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            if not force and now < self._next_attempt:
                return False
            # Reserve the slot before the thread starts so two frames cannot
            # both launch a check.
            self._next_attempt = now + self.interval
            self._thread = threading.Thread(
                target=self._run_check, name="tqg-update-check", daemon=True)
            self._thread.start()
            return True

    def _run_check(self):
        try:
            info = self._fetch()
        except Exception as exc:                      # offline / rate limited
            self.last_error = str(exc)
            with self._lock:
                # Retry sooner than the full interval, but never in a hot loop.
                self._next_attempt = time.time() + min(1800.0, self.interval)
            return
        self.last_error = ""
        with self._lock:
            if info is not None:
                self.available = info
                self._reported = False
            self._next_attempt = time.time() + self.interval
        self._save_state(time.time())

    def poll(self):
        """Return a newly found update once, then None until another is found."""
        with self._lock:
            info = self.available
            if info is None or self._reported:
                return None
            self._reported = True
            return dict(info)

    def check_now(self):
        """Synchronous check, for tests or an explicit 'check now' action."""
        try:
            info = self._fetch()
        except Exception as exc:
            self.last_error = str(exc)
            return None
        self.last_error = ""
        with self._lock:
            if info is not None:
                self.available = info
                self._reported = False
        return info

    # --- network ------------------------------------------------------------
    def _fetch(self):
        url = self.api_url
        if "?" not in url:
            url += "?per_page=30"
        request = urllib.request.Request(url, headers={
            "User-Agent": "TheQuestionGameRemastered/" + self.current_version,
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict):
            payload = [payload]
        releases = [rel for rel in (payload or [])
                    if isinstance(rel, dict)
                    and _is_remastered(rel)
                    and not rel.get("draft")]
        if not releases:
            return None
        best = max(releases, key=lambda rel: parse_version(rel.get("tag_name"))
                   or ((0, 0, 0, 0), 0))
        tag = str(best.get("tag_name") or "")
        if not is_newer(tag, self.current_version):
            return None
        return {
            "version": display_version(tag),
            "tag": tag,
            "name": str(best.get("name") or tag),
            "url": str(best.get("html_url") or config.UPDATE_RELEASE_PAGE),
            "download_url": _asset_url(best),
            "published_at": str(best.get("published_at") or ""),
        }

    # --- persisted "last checked" ------------------------------------------
    def _load_state(self):
        if not self.state_path:
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            last = float(state.get("last_check", 0.0) or 0.0)
            # A clock that jumped backwards must not postpone checks forever.
            if last <= time.time() + 60.0:
                self._next_attempt = max(self._next_attempt, last + self.interval)
        except Exception:
            pass

    def _save_state(self, when):
        if not self.state_path:
            return
        try:
            directory = os.path.dirname(self.state_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            temporary = self.state_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"last_check": float(when)}, handle)
            os.replace(temporary, self.state_path)
        except Exception:
            pass
