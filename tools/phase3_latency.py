"""Phase 3 — đo độ trễ hook guard / prompt_log trên máy này (v0.2 W3, cổng < 300 ms/tool call).

    python tools/phase3_latency.py [--runs 30]

Dựng dự án tạm (1 task coder đang chạy), gọi hook như Claude Code: JSON qua stdin.
Ba cách: python trực tiếp; qua Git Bash (`bash -c`), cách Claude Code chạy hook trên Windows (SCHEMA §9);
và mốc `python -c pass` (chi phí khởi động Python).
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "cli"))
import orc_core as oc  # noqa: E402


def measure(cmd: list, payload: bytes, runs: int) -> dict:
    ts = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run(cmd, input=payload, capture_output=True)
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return {"median": round(statistics.median(ts)), "p90": round(ts[int(len(ts) * 0.9) - 1]),
            "max": round(ts[-1])}


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30)
    a = ap.parse_args(argv)
    py = Path(sys.executable).as_posix()
    bash = shutil.which("bash")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        oc.cmd_init(root, "lat", "đo")
        t = oc.new_task(root, title="x", owner="coder", write_scope=["app/src/"])["id"]
        oc.advance(root, t, "dispatched")
        guard = json.dumps({"cwd": str(root), "session_id": "s", "tool_name": "Bash",
                            "tool_input": {"command": "cd app && npm run test 2>&1 | tail -5"}}).encode()
        prompt = json.dumps({"cwd": str(root), "session_id": "s", "prompt": "orc:approve TASK-0001 ABCDEF"}).encode()
        rows = [("python -c pass (mốc)", measure([sys.executable, "-c", "pass"], b"", a.runs)),
                ("guard: python trực tiếp", measure([sys.executable, str(KIT / "hooks/guard")], guard, a.runs)),
                ("prompt_log: python trực tiếp", measure([sys.executable, str(KIT / "hooks/prompt_log")], prompt, a.runs))]
        if bash:
            hook = (KIT / "hooks/guard").as_posix()
            rows.append(("guard: qua Git Bash", measure([bash, "-c", f'"{py}" "{hook}"'], guard, a.runs)))
        inner = [json.loads(l)["ms"] for l in
                 (root / ".orchestra/runtime/guard-shadow.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"# Độ trễ hook ({a.runs} lần mỗi dòng, ms)\n")
    print("| Cách gọi | median | p90 | max |\n|---|---|---|---|")
    for name, r in rows:
        print(f"| {name} | {r['median']} | {r['p90']} | {r['max']} |")
    print(f"\nThời gian quyết định bên trong guard (không gồm khởi động Python): median "
          f"{statistics.median(inner)} ms, max {max(inner)} ms.")
    print(f"Python: {sys.version.split()[0]}; bash: {bash or 'không có'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
