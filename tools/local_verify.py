"""Build from current source before tests; supports GCC/Clang or scoped local Zig."""

import shutil
import subprocess
import sys
from pathlib import Path

Path("build").mkdir(exist_ok=True)
output = Path(
    "build/depthreplay.exe" if sys.platform == "win32" else "build/depthreplay"
)
compiler = shutil.which("g++") or shutil.which("clang++")
if compiler:
    command = [compiler]
else:
    local = Path(
        "../../maintenance/career-lab/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    ).resolve()
    installed = shutil.which("zig")
    if installed:
        command = [installed, "c++"]
    elif local.is_file():
        command = [str(local), "c++"]
    else:
        raise SystemExit(
            "Install C++20 GCC/Clang/Zig or use CMake then tools/ci_verify.py"
        )
subprocess.run(
    [
        *command,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        "-Werror",
        "src/main.cpp",
        "-o",
        str(output),
    ],
    check=True,
)
subprocess.run([sys.executable, "tools/ci_verify.py"], check=True)
