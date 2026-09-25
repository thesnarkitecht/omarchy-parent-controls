"""Linux Landlock: deny execution except exact trusted files. Fail closed."""
import ctypes
import os
from pathlib import Path
import platform
import stat

EXECUTE = 1
CREATE, ADD, RESTRICT = 444, 445, 446

class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class PathRule(ctypes.Structure):
    _layout_ = "ms"
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

def trusted_executable(filename, require_x=True):
    path = Path(filename).resolve(strict=True)
    for item in (path, *path.parents):
        info = item.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError(f"Executable path is not root-owned and protected: {path}")
    if not stat.S_ISREG(path.stat().st_mode) or (require_x and not os.access(path, os.X_OK)):
        raise RuntimeError(f"Not an executable file: {path}")
    with path.open("rb") as f:
        if f.read(4) != b"\x7fELF":
            raise RuntimeError(f"Only native ELF executables are supported: {path}")
    return str(path)

def restrict_execution(executables):
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "x86_64"):
        raise RuntimeError("Kids mode needs Linux on aarch64 or x86_64 with Landlock.")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    def call(number, *args):
        result = libc.syscall(ctypes.c_long(number), *args)
        if result < 0:
            raise OSError(ctypes.get_errno(), "Landlock enforcement failed; kids mode will not start")
        return result
    call(CREATE, ctypes.c_void_p(), ctypes.c_size_t(0), ctypes.c_uint32(1))
    attr = Ruleset(EXECUTE)
    rules = call(CREATE, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    try:
        loaders = {"aarch64": "/usr/lib/ld-linux-aarch64.so.1", "x86_64": "/usr/lib/ld-linux-x86-64.so.2"}
        # ELF interpreters require EXECUTE too. Mount-level noexec in the session
        # prevents invoking this loader to mmap unapproved programs directly.
        allowed = set(executables)
        if allowed:
            allowed.add(loaders[platform.machine()])
        for filename in sorted(allowed):
            path = trusted_executable(filename)
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(EXECUTE, fd)
                call(ADD, rules, 1, ctypes.byref(rule), 0)
            finally:
                os.close(fd)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise OSError(ctypes.get_errno(), "Cannot prohibit privilege escalation")
        call(RESTRICT, rules, 0)
    finally:
        os.close(rules)
