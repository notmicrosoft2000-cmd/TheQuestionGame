"""python-for-android entry point: runs TheQuestionGameRemastered.

This file only exists for the Android build (buildozer's `source.include_patterns`
picks it up); on desktop the game still runs through run_remastered.py.
"""
import os
import runpy
import sys
import traceback


def _android_setup():
    """Permissions + device niceties, all best-effort.

    Anything that touches Java runs inside try/except: a phone that refuses a
    permission must degrade (no webcam scare, no vibrate) rather than crash.
    """
    from android.permissions import Permission, request_permissions

    try:
        # CAMERA   -> the webcam scare (cv2.VideoCapture); INTERNET -> the AI
        # relay; VIBRATE -> scare haptics. Storage is deliberately absent:
        # saves live in the app's private home dir, which needs no permission.
        request_permissions([Permission.CAMERA, Permission.INTERNET, Permission.VIBRATE])
    except Exception:
        pass

    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def keep_screen_on():
            # The pauses are the game — let no timeout dim the screen mid-question.
            flags = autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON
            autoclass("org.kivy.android.PythonActivity").mActivity.getWindow().addFlags(flags)

        keep_screen_on()
    except Exception:
        pass


BOOT_CRASH_FILE = "tqg_boot_crash.txt"


def _record_boot_crash(text):
    """Leave a readable traceback where a device can fetch it.

    The first Android build died on launch with no console and no log, which
    turned a one-line fix into a week of guesswork. Write the failure into the
    app's private files dir (HOME on p4a); a debug APK is debuggable, so:

        adb shell run-as org.ntg.thequestiongameremastered cat files/tqg_boot_crash.txt

    also try the public Download dir as a fallback. Never fatal: if nothing is
    writable the original exception still propagates.
    """
    roots = []
    home = os.environ.get("HOME") or ""
    if home:
        roots.append(home)
    roots += ["/sdcard/Download", "/sdcard", "."]
    for root in roots:
        try:
            path = os.path.join(root, BOOT_CRASH_FILE)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return path
        except OSError:
            continue
    return None


def _run_game():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    os.chdir(here)
    target = os.path.join(here, "run_remastered.py")
    if not os.path.isfile(target):
        # The Android build compiles the app to bytecode-only; the .py source
        # never ships. Desktop keeps its .py, so check rather than branch on
        # platform. A missing entry point used to be the crash-on-launch bug.
        target += "c"
    runpy.run_path(target, run_name="__main__")


if sys.platform == "android":
    try:
        _android_setup()
        _run_game()
    except SystemExit:
        raise
    except BaseException:
        # Normal exits are not crashes. Everything else leaves a traceback.
        try:
            _record_boot_crash(traceback.format_exc())
        except Exception:
            pass
        raise
else:
    _run_game()
