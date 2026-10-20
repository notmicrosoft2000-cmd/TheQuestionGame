#!/usr/bin/env python3
"""Re-apply the local python-for-android patches after a fresh p4a clone.

p4a lives in `.buildozer/` (gitignored), so its fixes must be re-applied on a
new machine or after the clone is wiped. `build_android.sh` calls this before
every build; it is idempotent — running it twice changes nothing.

Current patches:

1. `run_pymodules_install` cross-platform pip install
   p4a resolves non-recipe requirements with `pip --dry-run --platform
   android_... --python-version 3.14.2` and pins the matching *target* wheels
   into requirements.txt (e.g. charset-normalizer's android_24_arm64_v8a wheel,
   which exists on PyPI). The install step then ran plain host pip with no
   platform flags, which dies with:

       ERROR: charset_normalizer-3.5.2-cp314-cp314-android_24_arm64_v8a.whl
              is not a supported wheel on this platform.

   Fix: pass the same flags p4a already uses for prebuilt wheels
   (`Recipe.get_pip_install_args`): --only-binary=:all:, --no-deps,
   --python-version, --platform=<android tags>. Verified equivalent to
   upstream behaviour: pip only unpacks the wheel into --target.

Run:  ~/.myenv/bin/python apply_p4a_patches.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P4A_BUILD_PY = os.path.join(
    HERE, ".buildozer", "android", "platform",
    "python-for-android", "pythonforandroid", "build.py",
)

MARKER = "Cross-platform aware install."

OLD = r'''            shprint(sh.bash, '-c', (
                "venv/bin/pip " +
                "install -v --target '{0}' --no-deps -r requirements.txt"
            ).format(ctx.get_site_packages_dir(arch).replace("'", "'\"'\"'")),
                    _env=copy.copy(env))'''

NEW = r'''            # Cross-platform aware install. requirements.txt can pin wheels that
            # the resolver picked for the *target* platform (e.g. an
            # android_24_arm64_v8a charset-normalizer wheel), and host pip
            # rejects those with "... is not a supported wheel on this platform"
            # unless it is told which platform/python to validate for. These are
            # the same flags Recipe.get_pip_install_args() already passes when
            # installing prebuilt wheels.
            pip_flags = ["--only-binary=:all:", "--no-deps"]
            python_recipe = Recipe.get_recipe("python3", ctx)
            pip_flags += ["--python-version", python_recipe.version]
            for tag in PyProjectRecipe.get_wheel_platform_tags(arch.arch, ctx):
                pip_flags.append("--platform={}".format(tag))
            for index in ctx.extra_index_urls:
                pip_flags += ["--extra-index-url", index]

            shprint(sh.bash, '-c', (
                "venv/bin/pip " +
                "install -v --target '{0}' {1} -r requirements.txt"
            ).format(ctx.get_site_packages_dir(arch).replace("'", "'\"'\"'"),
                     " ".join(pip_flags)),
                    _env=copy.copy(env))'''


def main():
    if not os.path.exists(P4A_BUILD_PY):
        print("p4a not cloned yet (%s)" % P4A_BUILD_PY)
        print("Buildozer clones it on first run; re-run this script after that, "
              "before the pip-install stage.")
        return 0
    with open(P4A_BUILD_PY, "r", encoding="utf-8") as fh:
        src = fh.read()
    if MARKER in src:
        print("p4a patches already applied")
        return 0
    if OLD not in src:
        print("WARNING: p4a build.py does not match the expected text — the "
              "clone may be a different p4a version. Nothing patched.",
              file=sys.stderr)
        return 1
    with open(P4A_BUILD_PY, "w", encoding="utf-8") as fh:
        fh.write(src.replace(OLD, NEW, 1))
    print("patched p4a: cross-platform pip install for resolved wheels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
