"""Phase 4 — phát lại tool call shadow thật (Phase 3) qua guard mới (FINDING-6).

    python tools/phase4_guard_replay.py [--log docs/phases/shadow-raw/guard-shadow.jsonl] [--root D:/WMS]

Chỉ phát lại Bash/PowerShell và Read/Grep (quyết định không phụ thuộc write_scope lúc đó). Edit/Write cần scope của task
tại thời điểm gọi — log không có — nên không phát lại. Lệnh trong log bị cắt ở 200 ký tự; heredoc chưa đóng được bỏ
tới hết lệnh. File artifact/context/session trong `.orchestra/` coi như được phép ghi (log không có trạng thái task
lúc đó) — đây là giả định có lợi cho guard, ghi rõ trong báo cáo.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "cli"))
import orc_guard as og  # noqa: E402

OWN_FILES = re.compile(r"\.orchestra/(?:artifacts/ART|contexts/CTX|sessions/S)-\d+\.md")


def replay(log: Path, root: Path, exclude=()) -> dict:
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("session") not in exclude]
    writable = sorted({m for r in rows for m in OWN_FILES.findall(r.get("target", ""))})
    active = {"tasks": [], "writable": writable, "protected": []}
    out = {"total": len(rows), "replayed": 0, "old_deny": 0, "new_deny": [], "skipped": collections.Counter()}
    for r in rows:
        tool = r.get("tool")
        if tool in og.SHELL_TOOLS:
            ti = {"command": r.get("target", "")}
        elif tool in og.READ_TOOLS:
            ti = {"file_path": r.get("target", "")}
        else:
            out["skipped"][tool] += 1
            continue
        out["replayed"] += 1
        out["old_deny"] += r.get("decision") == "deny"
        decision, reason, _ = og.decide(root, active, tool, ti, r.get("agent_type"), safe=False)
        if decision == "deny":
            out["new_deny"].append({"tool": tool, "reason": reason, "target": r.get("target", "")[:160],
                                    "old": r.get("decision")})
    return out


def render(res: dict) -> str:
    lines = ["# Phase 4 — phát lại shadow Phase 3 qua guard mới", "",
             f"Tool call trong log: {res['total']}; phát lại (Bash/Read/Grep): {res['replayed']}; "
             f"không phát lại: {dict(res['skipped'])}", "",
             f"Lẽ ra chặn — guard cũ: {res['old_deny']}; guard mới: {len(res['new_deny'])}", ""]
    if res["new_deny"]:
        lines += ["| Tool | Lý do | Lệnh/đích (cắt) | Guard cũ |", "|---|---|---|---|"]
        for d in res["new_deny"]:
            t = d["target"].replace("|", "\\|").replace("\n", "⏎")
            lines.append(f"| {d['tool']} | {d['reason']} | `{t}` | {d['old']} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(KIT / "docs/phases/shadow-raw/guard-shadow.jsonl"))
    ap.add_argument("--root", default="D:/WMS")
    ap.add_argument("--exclude-session", nargs="*", default=["883fcd3d-e75a-4804-8432-b3215e4b5a8c", "smoke-test"])
    a = ap.parse_args(argv)
    sys.stdout.write(render(replay(Path(a.log), Path(a.root), set(a.exclude_session))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
