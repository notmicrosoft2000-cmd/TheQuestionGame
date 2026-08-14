"""The floppy disk's filesystem and DOS command shell.

This module is pygame-free (pure Python) so the shell logic can be tested
headless. The filesystem tree is defined by script.build_fs(state); this
module only walks it, parses commands, and reports events for the UI.

File entry schema:
    {
        "name": "README", "ext": "001", "id": "readme",
        "content": "multi\\nline text", "size": 1234,
        "hidden": False, "system": False, "run": None,
        "fragile": False, "dir": "A:/"
    }
"""
import random
import re

# --------------------------------------------------------------------------
# Small filesystem walker
# --------------------------------------------------------------------------
class DosFs:
    """Walks a nested dict tree: {"dirs": {...}, "files": [...]}.

    Accepts either a static tree or a callable(state) builder so the tree
    can react to corruption/deletion/unlocks mid-session.
    """

    def __init__(self, tree_or_builder, state):
        self._src = tree_or_builder
        self.state = state

    def _tree(self):
        if callable(self._src):
            return self._src(self.state)
        return self._src

    def node(self, path):
        root = self._tree().get("A:/")
        if root is None:
            return None
        parts = [p for p in path.replace("\\", "/").split("/")
                 if p and p != "A:"]
        node = root
        for p in parts:
            node = node.get("dirs", {}).get(p)
            if node is None:
                return None
        return node

    def list_dir(self, path):
        node = self.node(path)
        if node is None:
            return None
        visible_files = [f for f in node.get("files", [])
                         if not f.get("hidden")]
        dirs = sorted(node.get("dirs", {}).keys())
        return dirs, visible_files

    def find_file(self, path, name, ext=None):
        """Find a file by its DOS 8.3 name (case-insensitive)."""
        node = self.node(path)
        if node is None:
            return None
        for f in node.get("files", []):
            fname = f["name"].upper()
            fext = f["ext"].upper()
            if name.upper() == fname and (ext is None or ext.upper() == fext):
                return f
        return None


# --------------------------------------------------------------------------
# Command shell
# --------------------------------------------------------------------------
class DosShell:
    """DOS-like command loop. Events are appended to self.events each frame."""

    PROMPT = "A:\\> "

    def __init__(self, fs, state, on_run=None, on_read=None, rng_seed=None,
                 corruptor=None):
        self.fs = fs
        self.state = state
        self.cwd = "A:/"
        self.buffer = ""
        self.output = []          # list of (text, color)
        self.events = []          # {type, ...} consumed by the UI layer
        self.on_run = on_run      # callable(file) for RUN
        self.on_read = on_read    # callable(file) when a read completes
        self.corruptor = corruptor  # callable(file) producing corrupted text
        self._reading = None      # file currently streaming
        self._read_i = 0
        self._rng = random.Random(rng_seed)

        self._boot()

    # --- boot banner ---
    def _boot(self):
        self.output.append(("A:\\> _", "dim"))
        self.output.append(("Non-system disk or disk error", "red"))
        self.output.append(("Replace and press any key when ready", "dim"))
        self.output.append(("", "dim"))

    def clr(self):
        self.output = []
        self.events.append({"type": "clear"})

    # --- input ---
    def handle_char(self, ch):
        if self._reading:
            return
        if ch == "\r":
            self._submit()
        elif ch == "\b":
            self.buffer = self.buffer[:-1]
        else:
            if len(self.buffer) < 64:
                self.buffer += ch

    def _submit(self):
        line = self.buffer
        self.buffer = ""
        self.output.append((self.PROMPT + line, "text"))
        self._parse(line)
        self.events.append({"type": "submit"})

    # --- command parsing ---
    def _parse(self, line):
        line = line.strip()
        if not line:
            return
        parts = line.split()
        cmd = parts[0].upper()
        args = " ".join(parts[1:])

        if cmd in ("CLS", "CLEAR"):
            self.clr()
        elif cmd in ("HELP", "?"):
            self._help()
        elif cmd == "DIR":
            self._dir()
        elif cmd == "CD":
            self._cd(args)
        elif cmd == "TYPE":
            self._type(args)
        elif cmd == "DEL":
            self._del(args)
        elif cmd == "RUN":
            self._run(args)
        elif cmd == "VER":
            self._ver()
        elif cmd == "EXIT":
            self.events.append({"type": "exit"})
        elif cmd == "2013":
            self._code_2013()
        elif cmd == "WHOAMI":
            self._whoami()
        else:
            self.output.append((f"Bad command or file name - {parts[0]}", "dim"))

    def _help(self):
        for line in ("Available commands:",
                     "  DIR          list files",
                     "  CD <dir>     change directory",
                     "  TYPE <file>  read a file",
                     "  DEL <file>   delete a file",
                     "  RUN <file>   execute a program",
                     "  CLS          clear the screen",
                     "  VER          show version",
                     "  EXIT         leave the machine",
                     "  HELP         this list"):
            self.output.append((line, "text"))

    def _path_from_args(self, args):
        """Resolve 'DIRNAME/FILE.EXT' against cwd. Returns (dirpath, name, ext)."""
        if not args:
            return None
        args = args.strip().upper()
        if "/" in args:
            d, f = args.rsplit("/", 1)
            d = d.replace("\\", "/").strip("/")
            base = "A:" + (("/" + d) if d else "")
        else:
            base = self.cwd
            f = args
        name = f
        ext = None
        if "." in f:
            name, ext = f.split(".", 1)
        return base, name, ext

    def _dir(self):
        res = self.fs.list_dir(self.cwd)
        if res is None:
            self.output.append(("Invalid directory", "red"))
            return
        dirs, files = res
        self.output.append((" Volume in drive A is FIRSTCOPY", "dim"))
        self.output.append((" Directory of " + self.cwd, "dim"))
        self.output.append(("", "dim"))
        for d in dirs:
            self.output.append((f"{d:<18}<DIR>", "text"))
        for f in files:
            fn = f["name"][:8].ljust(8) + " " + f["ext"][:3]
            self.output.append((f"{fn:<14} {self._size(f)}", "text"))
        self.output.append(("", "dim"))
        self.events.append({"type": "dir", "path": self.cwd})

    @staticmethod
    def _size(f):
        return f.get("size", 0)

    def _cd(self, args):
        if not args:
            return
        a = args.strip().upper().replace("\\", "/")
        if a in ("..", "A:"):
            self.cwd = "A:/"
            return
        target = "A:" + (("/" + a.strip("/")) if a.strip("/") else "")
        if self.fs.node(target) is not None:
            self.cwd = target
        else:
            self.output.append((f"Invalid directory - {a}", "red"))

    def _type(self, args):
        if not args:
            self.output.append(("Invalid syntax. TYPE <file>", "dim"))
            return
        resolved = self._path_from_args(args)
        if resolved is None:
            return
        base, name, ext = resolved
        f = self.fs.find_file(base, name, ext)
        if f is None:
            self.output.append((f"File not found - {args}", "red"))
            return
        # start streaming this file; the UI reveals it and reports progress
        self._reading = f
        self._read_i = 0
        content = f.get("content", "")
        self.events.append({"type": "read_start", "file": f})

    def _del(self, args):
        if not args:
            return
        resolved = self._path_from_args(args)
        if resolved is None:
            return
        base, name, ext = resolved
        f = self.fs.find_file(base, name, ext)
        if f is None:
            self.output.append((f"File not found - {args}", "red"))
            return
        if f.get("system"):
            self.output.append(("Access denied. That file stays.", "red"))
            self.events.append({"type": "scare", "kind": "delete_refused"})
            return
        node = self.fs.node(base)
        node["files"] = [x for x in node["files"] if x is not f]
        if f.get("id"):
            deleted = self.state.setdefault("deleted_files", [])
            if f["id"] not in deleted:
                deleted.append(f["id"])
        self.output.append((f"{args.upper()}  deleted.", "dim"))
        self.events.append({"type": "delete", "file": f})

    def _run(self, args):
        resolved = self._path_from_args(args)
        if resolved is None:
            self.output.append(("Invalid syntax. RUN <file>", "dim"))
            return
        base, name, ext = resolved
        f = self.fs.find_file(base, name, ext)
        if f is None:
            self.output.append((f"File not found - {args}", "red"))
            return
        if not f.get("run"):
            self.output.append(("Not a program.", "dim"))
            return
        if self.on_run:
            self.on_run(f)
        self.events.append({"type": "run", "file": f})

    def _ver(self):
        self.output.append(("MS-DOS? No.", "dim"))
        self.output.append(("This disk has no version.", "text"))
        self.output.append(("It was not made here.", "red"))

    def _whoami(self):
        n = self.state.get("answers", {}).get("name")
        if n:
            self.output.append((f"WHOAMI returned: {n}", "text"))
            self.output.append(("That is what you call yourself.", "dim"))
        else:
            self.output.append(("WHOAMI returned nothing.", "red"))
            self.output.append(("You have not told it your name.", "dim"))
        loc = self.state.get("location")
        where = ", ".join(x for x in (loc.get("city"),
                                      loc.get("country")) if x) if loc else ""
        if where:
            self.output.append(("It looked up your address: " + where, "red"))
            self.output.append(("It has been expecting you.", "dim"))

    def _code_2013(self):
        if not self.state.get("logs_unlocked"):
            self.state["logs_unlocked"] = True
        self.output.append(("The disk was quiet for a moment.", "dim"))
        self.output.append(("A file you did not see is now visible.", "red"))
        self.events.append({"type": "code2013"})

    # --- reading state ---
    def reading(self):
        return self._reading

    def reading_progress(self):
        """Return (revealed_chars, total_chars) of the current read."""
        if not self._reading:
            return 0, 0
        return self._read_i, len(self._reading.get("content", ""))

    def finish_read(self):
        """Called by the UI when the streamed file is fully revealed."""
        if not self._reading:
            return
        f = self._reading
        self._reading = None
        # mark discovered (unless already)
        if f.get("id") and f["id"] not in self.state.get("discovered", []):
            self.state.setdefault("discovered", []).append(f["id"])
        # archive if the read completed without the file corrupting
        if f.get("id") and not f.get("corrupted"):
            if f["id"] not in self.state.get("archived", []):
                self.state.setdefault("archived", []).append(f["id"])
        if self.on_read:
            self.on_read(f)
        self.events.append({"type": "read_done", "file": f})

    def advance_read(self, chars):
        """Advance the reveal cursor. Returns (completed, corrupted)."""
        if not self._reading:
            return False, False
        f = self._reading
        self._read_i = min(len(f.get("content", "")), self._read_i + chars)
        completed = self._read_i >= len(f.get("content", ""))
        corrupted = False
        if f.get("fragile") and self._read_i > 0 and not f.get("corrupted"):
            # while reading a fragile file, the entity may corrupt it;
            # risk is zero until it notices you, then grows with presence
            presence = self.state.get("presence", 0)
            risk = presence * 0.0008
            if self._rng.random() < risk * chars:
                f["corrupted"] = True
                f["content"] = self._corrupt_content(f)
                corrupted_files = self.state.setdefault("corrupted_files", [])
                if f.get("id") and f["id"] not in corrupted_files:
                    corrupted_files.append(f["id"])
                self.events.append({"type": "scare", "kind": "file_corrupt",
                                    "file": f})
                corrupted = True
        return completed, corrupted

    def _corrupt_content(self, f):
        if self.corruptor is not None:
            return self.corruptor(f)
        return "\n".join(self._corrupt_line(l)
                         for l in f.get("content", "").split("\n"))

    def _corrupt_line(self, line):
        out = []
        for ch in line:
            if ch.strip() and self._rng.random() < 0.25:
                out.append(self._rng.choice("█▓▒░#@%&?¡!/\\"))
            else:
                out.append(ch)
        return "".join(out)

    def cancel_read(self):
        if self._reading:
            f = self._reading
            self._reading = None
            self.events.append({"type": "read_cancel", "file": f})
