"""
CAPA 5: Runtime guard — PEP 578 audit hook injected into the sandboxed child process.

The AST validator is a deny-list and cannot see dynamic paths (open(var)) or
library calls that write files. This hook runs inside the child interpreter and
checks every sensitive event at runtime. Audit hooks cannot be removed once added.

Policy (fail-closed):
  - open() for writing: only inside the workspace.
  - open() for reading: workspace + the Python installation (stdlib, site-packages).
  - delete / rename / mkdir: only inside the workspace.
  - process creation, registry writes: always blocked. (ctypes stays allowed at runtime so
    numpy/matplotlib can load their DLLs; generated code cannot import ctypes: CAPA 2.)
  - network: only loopback (localhost).
"""

from __future__ import annotations

GUARD_TEMPLATE = r'''
import os as _g_os
import sys as _g_sys

def _g_install(workspace):
    real = _g_os.path.realpath
    ws = _g_os.path.normcase(real(workspace))
    roots = {_g_sys.prefix, _g_sys.base_prefix, _g_sys.exec_prefix}
    roots.update(p for p in _g_sys.path if p and "site-packages" in p)
    if _g_os.environ.get("WINDIR"):
        roots.add(_g_os.path.join(_g_os.environ["WINDIR"], "Fonts"))  # fuentes para matplotlib
    read_roots = tuple(_g_os.path.normcase(real(r)) for r in roots if r)
    write_flags = (_g_os.O_WRONLY | _g_os.O_RDWR | _g_os.O_CREAT
                   | _g_os.O_APPEND | _g_os.O_TRUNC)
    blocked_prefixes = ("subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                        "os.fork", "os.startfile", "os.kill", "_winapi.CreateProcess",
                        "winreg.CreateKey", "winreg.DeleteKey", "winreg.DeleteValue",
                        "winreg.SetValue", "winreg.LoadKey", "winreg.SaveKey",
                        "os.chmod", "os.chown", "os.symlink", "os.link")
    path_events = ("os.remove", "os.rmdir", "os.rename", "os.mkdir", "os.truncate",
                   "os.utime", "shutil.rmtree", "shutil.copyfile", "shutil.move")
    loopback = ("127.0.0.1", "::1", "localhost")

    def inside(path, allowed):
        try:
            p = _g_os.path.normcase(real(_g_os.fsdecode(path)))
        except (TypeError, ValueError):
            return False
        return any(p == r or p.startswith(r.rstrip(_g_os.sep) + _g_os.sep) for r in allowed)

    def deny(what):
        raise PermissionError("[sandbox] blocked: " + what)

    def hook(event, args):
        if event == "open":
            path, mode, flags = (tuple(args) + (None, None, None))[:3]
            if path is None or isinstance(path, int):
                return
            writing = bool(mode and any(c in str(mode) for c in "wax+"))
            writing = writing or bool(isinstance(flags, int) and flags & write_flags)
            if writing and not inside(path, (ws,)):
                deny("write outside workspace: " + str(path))
            if not writing and not inside(path, (ws,) + read_roots):
                deny("read outside workspace: " + str(path))
        elif event.startswith(blocked_prefixes):
            deny(event)
        elif event in path_events:
            for a in args[:2]:
                if isinstance(a, (str, bytes)) or hasattr(a, "__fspath__"):
                    if not inside(a, (ws,)):
                        deny(event + " outside workspace")
        elif event == "socket.connect":
            addr = args[1] if len(args) > 1 else None
            host = addr[0] if isinstance(addr, tuple) and addr else addr
            if host not in loopback:
                deny("network connection to " + str(host))
        elif event == "socket.getaddrinfo":
            if args and args[0] not in loopback:
                deny("DNS lookup of " + str(args[0]))

    _g_sys.addaudithook(hook)

_g_install(__WORKSPACE__)
del _g_install
'''


def build_guard(workspace: str) -> str:
    """Return the guard source with the workspace path embedded as a literal."""
    return GUARD_TEMPLATE.replace("__WORKSPACE__", repr(str(workspace)))
