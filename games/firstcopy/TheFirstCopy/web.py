"""Website-opening for The Simpler Times.

When the entity decides you should look at something, it opens a page in
your real browser — something a 1993 modem never could. The pages it
opens live on the game's own corner of the internet: The Simpler Times
website (separate from The Question Game site).

This module is pygame-free. The browser launch happens on a daemon thread
so the game never stalls, and it can be disabled entirely for headless
test runs: the connecting overlay still plays, the browser just does not
open.
"""
import threading
import webbrowser

# The pages the entity opens. "index" is the front door; "mail" is the
# game's inbox page on the same site.
SITES = {
    "index": "https://notmicrosoft2000-cmd.github.io/TheSimplerTimes/",
    "mail": "https://notmicrosoft2000-cmd.github.io/TheSimplerTimes/#mail",
}

_enabled = True
_lock = threading.Lock()
_opened = set()


def set_enabled(on):
    """Enable/disable real browser launches (tests call set_enabled(False))."""
    global _enabled
    with _lock:
        _enabled = on


def enabled():
    with _lock:
        return _enabled


def url_for(site):
    return SITES.get(site, SITES["index"])


def open_site(site):
    """Open a site's page in the default browser, in the background.
    The visit is always recorded so tests can assert it happened."""
    url = url_for(site)
    with _lock:
        _opened.add(site)
        do_open = _enabled
    if do_open:
        threading.Thread(target=_do_open, args=(url,), daemon=True).start()


def _do_open(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


def opened_sites():
    with _lock:
        return set(_opened)
