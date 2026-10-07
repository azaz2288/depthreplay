import os
import subprocess
import sys
import tempfile
from pathlib import Path

executable = next(
    (
        p
        for p in [
            Path("build/Release/depthreplay.exe"),
            Path("build/depthreplay.exe"),
            Path("build/depthreplay"),
        ]
        if p.is_file()
    ),
    None,
)
if executable is None:
    raise SystemExit("Missing CMake executable")
env = {**os.environ, "DEPTHREPLAY_EXE": str(executable.resolve())}
subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    env=env,
    check=True,
)
with tempfile.TemporaryDirectory(prefix="depthreplay-verification-") as directory:
    base = Path(directory)
    events, snapshots, report = (
        base / "events.csv",
        base / "snapshots.csv",
        base / "report",
    )
    subprocess.run(
        [sys.executable, "tools/generate_demo.py", str(events), "--count", "10000"],
        check=True,
    )
    subprocess.run([str(executable.resolve()), str(events), str(snapshots)], check=True)
    subprocess.run(
        [sys.executable, "research/report.py", str(snapshots), str(report)], check=True
    )
