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

2. `make_tar` directory modes in private.tar
   `make_tar` writes directory entries with `tarfile.TarInfo(dir)` and never
   sets a mode, so they inherit TarInfo's default 0o644 — `drw-r--r--`. A
   directory without the execute bit cannot be traversed, so `tar xf
   private.tar` on a build host extracts an unreadable tree and any attempt to
   run or inspect the packaged app from it fails with confusing
   `ModuleNotFoundError` / `Permission denied` errors (the Java extractor on
   device ignores tar modes, which is why the APK still runs — this patch only
   makes the archive honest and debuggable). p4a's own troubleshooting docs
   tell you to extract private.tar, so the modes should be sane.

Run:  ~/.myenv/bin/python apply_p4a_patches.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P4A_ROOT = os.path.join(
    HERE, ".buildozer", "android", "platform",
    "python-for-android", "pythonforandroid",
)

PIP_PATCH = dict(
    path=os.path.join(P4A_ROOT, "build.py"),
    marker="Cross-platform aware install.",
    name="cross-platform pip install for resolved wheels",
    old=r'''            shprint(sh.bash, '-c', (
                "venv/bin/pip " +
                "install -v --target '{0}' --no-deps -r requirements.txt"
            ).format(ctx.get_site_packages_dir(arch).replace("'", "'\"'\"'")),
                    _env=copy.copy(env))''',
    new=r'''            # Cross-platform aware install. requirements.txt can pin wheels that
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
                    _env=copy.copy(env))''',
)

TAR_PATCH = dict(
    path=os.path.join(P4A_ROOT, "bootstraps", "common", "build", "build.py"),
    marker="Directories need the execute bit",
    name="private.tar directory modes",
    old='''                tinfo = tarfile.TarInfo(d)
                tinfo.type = tarfile.DIRTYPE
                clean(tinfo)''',
    new='''                tinfo = tarfile.TarInfo(d)
                tinfo.type = tarfile.DIRTYPE
                # Directories need the execute bit to be traversable. TarInfo
                # defaults to 0o644, which produced drw-r--r-- entries: harmless
                # on device (the Java extractor ignores tar modes) but it made
                # `tar xf private.tar` extract an unreadable tree, breaking the
                # debugging workflow p4a's docs recommend.
                tinfo.mode = 0o700
                clean(tinfo)''',
)

PATCHES = [PIP_PATCH, TAR_PATCH]


def apply_patch(patch):
    path = patch["path"]
    if not os.path.exists(path):
        print("p4a not cloned yet (%s)" % path)
        print("Buildozer clones it on first run; re-run this script after that, "
              "before the build stage.")
        return None
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    if patch["marker"] in src:
        return "already applied"
    if patch["old"] not in src:
        print("WARNING: %s does not match the expected text — the clone may be "
              "a different p4a version. Nothing patched for %r."
              % (path, patch["name"]), file=sys.stderr)
        return "MISMATCH"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src.replace(patch["old"], patch["new"], 1))
    print("patched p4a: %s" % patch["name"])
    return "patched"


def main():
    failed = False
    for patch in PATCHES:
        result = apply_patch(patch)
        if result is None:
            return 0
        if result == "MISMATCH":
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
