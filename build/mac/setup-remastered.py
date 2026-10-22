import os

from setuptools import setup

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

setup(
    name="TheQuestionGameRemastered",
    version="6.1-alpha",
    description="The Question Game Remastered",
    app=[os.path.join(ROOT, "games", "remastered", "run_remastered.py")],
    options={
        "py2app": {
            "argv_emulation": True,
            "iconfile": os.path.join(ROOT, "icon.icns"),
            "packages": ["pygame", "numpy", "cv2", "requests"],
            # tkinter is NOT excluded: the desktop eye overlay is a Tk window.
            # It only runs in the --eye-overlay child process.
            "excludes": ["PyQt5", "PySide2", "matplotlib", "scipy"],
            "resources": [
                os.path.join(ROOT, "games", "remastered", "TheQuestionGameRemastered", "assets"),
            ],
            "plist": {
                "CFBundleName": "The Question Game Remastered",
                "CFBundleDisplayName": "The Question Game Remastered",
                "CFBundleIdentifier": "com.notmicrosoft2000.thequestiongameremastered",
                "CFBundleShortVersionString": "6.1-alpha",
                "CFBundleVersion": "6.1.0",
                "LSApplicationCategoryType": "public.app-category.games",
                "NSHighResolutionCapable": True,
                "NSCameraUsageDescription": "The Question Game Remastered checks whether you are still paying attention during the session.",
            },
        }
    },
)
