import os

from setuptools import setup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

setup(
    name="TheQuestionGame",
    version="2.02",
    description="The Question Game",
    app=[os.path.join(ROOT, "games", "classic", "TheQuestionGame.py")],
    options={
        "py2app": {
            "argv_emulation": True,
            "iconfile": os.path.join(ROOT, "icon.icns"),
            "packages": ["pygame", "numpy", "cv2", "requests"],
            "excludes": ["tkinter", "PyQt5", "PySide2", "matplotlib", "scipy"],
            "resources": [
                os.path.join(ROOT, "windowq.png"),
                os.path.join(ROOT, "logsmusic.ogg"),
                os.path.join(ROOT, "games", "classic", "readme.txt"),
            ],
            "plist": {
                "CFBundleName": "The Question Game",
                "CFBundleDisplayName": "The Question Game",
                "CFBundleIdentifier": "com.notmicrosoft2000.thequestiongame",
                "CFBundleShortVersionString": "2.02",
                "CFBundleVersion": "2.02",
                "LSApplicationCategoryType": "public.app-category.games",
                "NSHighResolutionCapable": True,
                "NSCameraUsageDescription": "The Question Game checks whether you are still paying attention during the session.",
            },
        }
    },
)
