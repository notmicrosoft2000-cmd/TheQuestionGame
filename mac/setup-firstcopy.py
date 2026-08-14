import os

from setuptools import setup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

setup(
    name="TheSimplerTimes",
    version="1.0",
    description="The Simpler Times",
    app=[os.path.join(ROOT, "games", "firstcopy", "run_firstcopy.py")],
    options={
        "py2app": {
            "argv_emulation": True,
            "iconfile": os.path.join(ROOT, "icon.icns"),
            "packages": ["pygame", "numpy"],
            "excludes": ["tkinter", "PyQt5", "PySide2", "matplotlib", "scipy"],
            "plist": {
                "CFBundleName": "The Simpler Times",
                "CFBundleDisplayName": "The Simpler Times",
                "CFBundleIdentifier": "com.notmicrosoft2000.thesimplertimes",
                "CFBundleShortVersionString": "1.0",
                "CFBundleVersion": "1.0",
                "LSApplicationCategoryType": "public.app-category.games",
                "NSHighResolutionCapable": True,
            },
        }
    },
)
