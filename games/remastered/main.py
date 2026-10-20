"""python-for-android entry point: runs TheQuestionGameRemastered.

This file only exists for the Android build (buildozer's `source.include_patterns`
picks it up); on desktop the game still runs through run_remastered.py.
"""
import os
import runpy
import sys


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


if sys.platform == "android":
    _android_setup()

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
os.chdir(here)
runpy.run_path(os.path.join(here, "run_remastered.py"), run_name="__main__")
