"""Phase 5 — triage hồi cứu trên yêu cầu thật đã làm (chỉ đọc), để Dung điền mức tự đánh giá.

    python tools/phase5_triage_replay.py --project D:/WMS --app-repo app --map TASK-0006=a949af2 \
        [--module-roots app/src]

Mỗi yêu cầu (gom như Phase 0): lần 2 = write_scope các task coder (đếm file đang có trong git), lần 3 = file đổi và
số dòng (`git show --numstat`) của commit đã ghép, bỏ `.orchestra/`. Form khai báo không có trong dữ liệu cũ ⇒ không
bao giờ ra L0 (đúng nguyên tắc thiếu dữ kiện). Không ghi gì vào dự án.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "cli"))
sys.path.insert(0, str(KIT / "tools"))
import orc_core as oc  # noqa: E402
import orc_guard as og  # noqa: E402
import orc_triage as ot  # noqa: E402
import phase0_baseline as pb  # noqa: E402


def numstat(repo: Path, sha: str, prefix: str) -> tuple:
    r = subprocess.run(["git", "-C", str(repo), "show", "--numstat", "--format=", sha], capture_output=True)
    files, lines = [], 0
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, f = parts
        f = prefix + f
        if f.startswith(".orchestra/"):
            continue
        files.append(f)
        lines += (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
    return files, lines


def tracked(root: Path, app_repo: str | None) -> list:
    out = []
    for rel in ["."] + ([app_repo] if app_repo else []):
        r = subprocess.run(["git", "-C", str(root / rel), "ls-files", "-z"], capture_output=True)
        pre = "" if rel == "." else rel.rstrip("/") + "/"
        out += [pre + f for f in r.stdout.decode("utf-8", "replace").split("\0") if f]
    return out


def replay(project: Path, app_repo: str | None, mapping: dict, module_roots) -> list:
    root = oc.require_root(project)
    cfg = ot.config(root)
    if module_roots:
        cfg["module_roots"] = list(module_roots)
    data = pb.measure(root, app_repo, mapping)
    tasks = oc.load_registry(root, "task")
    req_of = pb.group_requests(tasks, {a["id"]: a for a in oc.load_registry(root, "artifact")})
    files_now = tracked(root, app_repo)
    rows = []
    for r in data["rows"]:
        coders = [t for t in tasks if req_of[t["id"]] == r["root"] and oc.agent_for(t["owner"]) == "coder"]
        scope = sorted({str(s) for t in coders for s in oc.as_list(t.get("write_scope"))})
        s2_files = sorted({f for p in scope for f in ([x for x in files_now if og.match_path(x, [p])] or [p])})
        l2, rules2 = ot.classify(s2_files if scope else None, None, None, cfg)
        f3, n3 = [], 0
        for c in r["commits"]:
            repo, sha = c.split(":", 1)
            rel = "." if repo == "(gốc)" else repo.rstrip("/")
            files, lines = numstat(root / rel, sha, "" if rel == "." else rel + "/")
            f3 += files
            n3 += lines
        f3 = sorted(set(f3))
        l3, rules3 = ot.classify(f3 if r["commits"] else None, n3 if r["commits"] else None, None, cfg)
        mods = len({ot.module_of(f, cfg["module_roots"]) for f in f3}) if f3 else 0
        rows.append({"root": r["root"], "title": r["title"], "coders": len(coders), "scope_files": len(s2_files),
                     "l2": l2, "rules2": rules2, "files3": len(f3), "lines3": n3, "modules3": mods, "l3": l3,
                     "rules3": rules3, "final": max(l2, l3)})
    return rows


def render(rows: list) -> str:
    out = ["# Phase 5 — triage hồi cứu trên yêu cầu thật (shadow, chỉ đọc)", "",
           "Lần 2 = write_scope các task coder; lần 3 = commit thật (bỏ `.orchestra/`). Không có form khai báo trong dữ",
           "liệu cũ ⇒ chỉ tín hiệu máy (form thật có thể **nâng** thêm, không hạ). Cột cuối để Dung điền.", "",
           "| Yêu cầu | Task coder | Lần 2: file scope → L | Lần 3: file / dòng / module → L | Kết quả (max) | Luật chính | Dung đánh giá |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        main = (r["rules3"] or r["rules2"])
        top = "; ".join(why for lv, why in main if lv == f"L{r['final']}")[:120] or "; ".join(w for _, w in main)[:120]
        out.append(f"| {r['root']} {oc._short(r['title'], 40)} | {r['coders']} | {r['scope_files']} → L{r['l2']} "
                   f"| {r['files3']} / {r['lines3']} / {r['modules3']} → L{r['l3']} | **L{r['final']}** "
                   f"| {top.replace('|', '/')} | L? |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--app-repo")
    ap.add_argument("--map", nargs="*", default=[])
    ap.add_argument("--module-roots", nargs="*", default=[])
    a = ap.parse_args(argv)
    rows = replay(Path(a.project), a.app_repo, dict(m.split("=", 1) for m in a.map), a.module_roots)
    sys.stdout.write(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
