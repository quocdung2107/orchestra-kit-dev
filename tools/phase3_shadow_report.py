"""Phase 3 — tóm tắt shadow log để Dung xem sau khi chạy thử (cổng v0.2: guard "lẽ ra chặn" trong 10 task).

    python tools/phase3_shadow_report.py --project D:/WMS

Đọc (chỉ đọc) `.orchestra/runtime/guard-shadow.jsonl` và `runtime/shadow.jsonl`; in bảng lẽ-ra-chặn theo
mode/lý do, mẫu lệnh/file, độ trễ quyết định, agent_type gặp được (kiểm W8: hook có chạy trong subagent không).
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path


def read(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def report(project: Path) -> str:
    rt = project / ".orchestra" / "runtime"
    g = read(rt / "guard-shadow.jsonl")
    s = read(rt / "shadow.jsonl")
    deny = [r for r in g if r.get("decision") == "deny"]
    out = ["# Shadow guard — tóm tắt", "",
           f"Tool call đã thấy: {len(g)}; lẽ ra chặn: {len(deny)}; "
           f"phiên: {len({r.get('session') for r in g})}; "
           f"agent_type: {sorted({str(r.get('agent_type')) for r in g})}", ""]
    if g:
        ms = [r.get("ms", 0) for r in g]
        out.append(f"Thời gian quyết định trong guard: median {statistics.median(ms)} ms, max {max(ms)} ms "
                   "(không gồm khởi động Python — xem tools/phase3_latency.py).")
        out.append("")
    out += ["## Lẽ ra chặn theo mode và lý do", "", "| Mode | Lý do | Số lần | Ví dụ |", "|---|---|---|---|"]
    groups = collections.defaultdict(list)
    for r in deny:
        reason = str(r.get("reason", "")).split(":")[0:2]
        groups[(r.get("mode"), ":".join(reason))].append(r)
    for (mode, reason), rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ex = str(rs[0].get("target", "")).replace("|", "\\|")[:80]
        out.append(f"| {mode} | {reason} | {len(rs)} | `{ex}` |")
    out += ["", "## Approval (shadow)", ""]
    miss = [r for r in s if r.get("event") == "approval_missing"]
    out.append(f"Giao task coder khi chưa có approval hợp lệ: {len(miss)} lần"
               + (f" ({', '.join(sorted({r['task'] for r in miss}))})" if miss else ""))
    out += ["", "Dung đánh dấu từng dòng: chặn đúng / chặn sai. Chặn sai > 0 ⇒ sửa bảng guard trước Phase 4."]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    sys.stdout.write(report(Path(ap.parse_args(argv).project)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
