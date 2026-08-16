"""python-for-android entry point: runs TheQuestionGame.py as __main__."""
import os
import runpy

here = os.path.dirname(os.path.abspath(__file__))
runpy.run_path(os.path.join(here, "TheQuestionGame.py"), run_name="__main__")
