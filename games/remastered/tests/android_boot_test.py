#!/usr/bin/env python3
"""Guards the Android entry point — the thing that used to crash on launch.

The first APK died before the game drew a frame: p4a ships bytecode only, but
the shim tried to run `run_remastered.py`, which is not in the package. That is
fixed by a `.pyc` fallback. A second class of failure is invisible by design on
a phone (no console), so the shim now leaves a traceback file. This test keeps
both properties, without executing the shim's module-level boot code.

Run:  python games/remastered/tests/android_boot_test.py
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHIM = os.path.join(ROOT, "main.py")

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILS.append(name)
        print("  FAIL %s %s" % (name, extra))


def main():
    with open(SHIM, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=SHIM)

    print("== the bytecode-only entry point is handled ==")
    check("the shim looks for run_remastered.py", '"run_remastered.py"' in source)
    check("the shim falls back to .pyc", 'target += "c"' in source)
    check("the fallback is checked by file existence, not platform",
          "os.path.isfile(target)" in source)

    print("== boot failures leave a traceback ==")
    check("a boot crash file is defined", 'BOOT_CRASH_FILE = "tqg_boot_crash.txt"' in source)
    check("the traceback comes from traceback.format_exc",
          "traceback.format_exc()" in source)
    check("a writable location is searched",
          '"/sdcard/Download"' in source and 'os.environ.get("HOME")' in source)
    check("normal exits are not logged as crashes",
          "except SystemExit:" in source and "raise" in source)
    check("the Android setup runs before the game",
          source.index("_android_setup()") < source.index("_run_game()"))

    # Execute just _record_boot_crash in an isolated namespace: importing the
    # whole shim would boot the game on desktop.
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef)
               and n.name == "_record_boot_crash"), None)
    check("_record_boot_crash is a real function", fn is not None)
    if fn is not None:
        constant = next((n for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name)
                                 and t.id == "BOOT_CRASH_FILE" for t in n.targets)), None)
        check("the crash file name is a module constant", constant is not None)
        ns = {"os": os}
        mod = ast.Module(body=[n for n in (constant, fn) if n is not None],
                         type_ignores=[])
        exec(compile(ast.fix_missing_locations(mod), SHIM, "exec"), ns)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HOME"] = tmp
            path = ns["_record_boot_crash"]("TRACEBACK TEXT")
            check("the crash log is written", bool(path) and os.path.isfile(path), path)
            if path:
                with open(path, encoding="utf-8") as fh:
                    check("the crash log contains the traceback",
                          fh.read() == "TRACEBACK TEXT")

    if FAILS:
        print("\nANDROID_BOOT_FAIL: %s" % ", ".join(FAILS))
        return 1
    print("\nANDROID_BOOT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
