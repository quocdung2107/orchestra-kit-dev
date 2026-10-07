"""Phase 0 — đo baseline của orchestra-kit 0.1.0 từ dữ liệu thật đã có (chỉ đọc).

Cách chạy:
    python tools/phase0_baseline.py --project D:/WMS [--app-repo app] [--map TASK-0006=a949af2 ...]

Đọc: .orchestra/state/*.yaml, artifacts/, sessions/, runtime/sessions/ của dự án; git log của dự án,
của repo con (--app-repo) và của kit. Không ghi bất cứ file nào. In bảng Markdown ra stdout.

Ghép commit với yêu cầu: commit có nhắc TASK-/ART-/S- ID (kể cả dạng TASK-0006..0015) của yêu cầu;
commit không nhắc ID thì chỉ ghép khi truyền --map <TASK gốc>=<sha>.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "cli"))
import orc_core as oc  # noqa: E402

ID_IN_TEXT = re.compile(r"\b(TASK|ART|S)-(\d{4})(?:\.\.(\d{4}))?\b")


def git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8")
    return r.stdout if r.returncode == 0 else ""


def commits(repo: Path, rev: str = "HEAD") -> list:
    """[(sha, iso time, subject, [files])], cũ → mới. Repo không có git → []."""
    out = []
    for line in git(repo, "log", "--reverse", "--format=%h\t%cI\t%s", rev).splitlines():
        sha, when, subject = line.split("\t", 2)
        files = [f for f in git(repo, "show", "--name-only", "--format=", sha).splitlines() if f]
        out.append((sha, when, subject, files))
    return out


def ids_in(text: str) -> set:
    found = set()
    for prefix, a, b in ID_IN_TEXT.findall(text):
        lo, hi = int(a), int(b or a)
        found |= {f"{prefix}-{n:04d}" for n in range(lo, hi + 1)}
    return found


def group_requests(tasks: list, arts: dict) -> dict:
    """Gom task thành yêu cầu: nối qua inputs (ART → task của ART, TASK) và blocked_by.
    Trả {task_id: TASK gốc (ID nhỏ nhất của nhóm)}."""
    parent = {t["id"]: t["id"] for t in tasks}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

    for t in tasks:
        for ref in oc.as_list(t.get("inputs")) + oc.as_list(t.get("blocked_by")):
            ref = str(ref)
            if ref.startswith("ART-") and ref in arts:
                union(t["id"], arts[ref].get("task"))
            elif ref.startswith("TASK-"):
                union(t["id"], ref)
    return {t: find(t) for t in parent}


def _mtime(p: Path):
    return dt.datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


def measure(project: Path, app_repo: str | None, mapping: dict) -> dict:
    root = oc.require_root(project)
    tasks = oc.load_registry(root, "task")
    arts = {a["id"]: a for a in oc.load_registry(root, "artifact")}
    decs = oc.load_registry(root, "decision")
    ctxs = oc.load_registry(root, "context")
    evds = oc.load_registry(root, "evidence")
    req_of = group_requests(tasks, arts)

    # Phiên: task trong frontmatter + số lần hook Stop chặn (dấu runtime)
    blocks = {}
    rt = oc.orc(root) / "runtime" / "sessions"
    for mp in sorted(rt.glob("*.yaml")) if rt.is_dir() else []:
        m = oc.load_yaml_file(mp) or {}
        if m.get("sid"):
            blocks[m["sid"]] = int(m.get("blocks") or 0)
    sessions = {}
    for sid in oc.session_ids(root):
        fm, _ = oc.split_frontmatter(oc.read_text(oc.content_path(root, sid)))
        fm = fm or {}
        sessions[sid] = {"task": fm.get("task"), "result": fm.get("result"),
                         "blocks": blocks.get(sid)}

    roots = sorted(set(req_of.values()))
    reqs = {r: {"root": r, "tasks": [], "arts": [], "decs": [], "ctxs": [], "evds": [],
                "sessions": [], "commits": []} for r in roots}
    for t in tasks:
        reqs[req_of[t["id"]]]["tasks"].append(t)
    art_req = {}
    for a in arts.values():
        r = req_of.get(a.get("task"))
        if r:
            reqs[r]["arts"].append(a)
            art_req[a["id"]] = r
    for d in decs:
        r = req_of.get(d.get("scope")) or art_req.get(d.get("scope"))
        if r:
            reqs[r]["decs"].append(d)
    for c in ctxs:
        if c.get("task") in req_of:
            reqs[req_of[c["task"]]]["ctxs"].append(c)
    for e in evds:
        if e.get("task") in req_of:
            reqs[req_of[e["task"]]]["evds"].append(e)
    sess_req = {}
    for sid, s in sessions.items():
        r = req_of.get(s["task"])
        if r:
            reqs[r]["sessions"].append(sid)
            sess_req[sid] = r

    def req_for_ids(found: set) -> set:
        out = set()
        for i in found:
            if i in req_of:
                out.add(req_of[i])
            elif i in art_req:
                out.add(art_req[i])
            elif i in sess_req:
                out.add(sess_req[i])
        return out

    repos = [("", project)]
    if app_repo:
        repos.append((app_repo.rstrip("/") + "/", project / app_repo))
    for prefix, repo in repos:
        for sha, when, subject, files in commits(repo):
            hit = req_for_ids(ids_in(subject))
            hit |= {r for r, s in mapping.items() if sha.startswith(s) or s.startswith(sha)}
            for r in hit & set(reqs):
                reqs[r]["commits"].append({"repo": prefix or "(gốc)", "sha": sha, "when": when,
                                           "files": [prefix + f for f in files]})

    rows = []
    for r in roots:
        q = reqs[r]
        coder = [t for t in q["tasks"] if oc.agent_for(t["owner"]) == "coder"]
        scope = [s for t in coder for s in oc.as_list(t.get("write_scope"))]
        research = [a for a in q["arts"] if a["type"] == "research"]
        plans = [a for a in q["arts"] if a["type"] == "plan"]
        reviews = [a for a in q["arts"] if a["type"] == "review_report"]
        gate_now = 0
        for p in plans:
            try:
                gate_now += len(oc.gate(root, p["id"]))
            except oc.OrcError:
                pass
        # Thời gian xấp xỉ: mtime file ART/CTX/session của yêu cầu (đầu → cuối)
        paths = ([oc.content_path(root, a["id"]) for a in q["arts"]]
                 + [oc.content_path(root, c["id"]) for c in q["ctxs"]]
                 + [oc.content_path(root, s) for s in q["sessions"]])
        times = sorted(t for t in map(_mtime, paths) if t)
        span = round((times[-1] - times[0]).total_seconds() / 60) if len(times) > 1 else None
        changed = sorted({f for c in q["commits"] for f in c["files"]
                          if not f.startswith(".orchestra/")})
        outside = [f for f in changed if not oc._in_scope(f, scope)]
        code_outside = [f for f in outside if not f.endswith(".md")]
        fcs = sorted({t.get("failure_class") for t in q["tasks"] if t.get("failure_class")})
        rows.append({
            "root": r,
            "title": next(t["title"] for t in q["tasks"] if t["id"] == r),
            "sessions": sorted(q["sessions"]),
            "session_results": [sessions[s]["result"] for s in sorted(q["sessions"])],
            "stop_hook_blocks": sum(sessions[s]["blocks"] or 0 for s in q["sessions"]),
            "tasks": len(q["tasks"]), "coder_tasks": len(coder),
            "research_stops": len(research), "dung_decisions": len(q["decs"]),
            "gate_reasons_now": gate_now,
            "needs_user_now": sum(1 for t in q["tasks"] if t.get("needs_user")),
            "blocked_sessions": sum(1 for s in q["sessions"] if sessions[s]["result"] == "blocked"),
            "attempts": sum(int(t.get("attempts") or 0) for t in q["tasks"]),
            "failure_classes": fcs,
            "reviews": len(reviews),
            "re_reviews": sum(1 for a in reviews if a.get("supersedes")),
            "reviews_draft": sum(1 for a in reviews if a.get("status") == "draft"),
            "ctx": len(q["ctxs"]),
            "ctx_graph": sum(1 for c in q["ctxs"] if c.get("source") == "graph"),
            "evd": len(q["evds"]),
            "evd_pass": sum(1 for e in q["evds"] if e.get("result") == "pass"),
            "evd_fail": sum(1 for e in q["evds"] if e.get("result") == "fail"),
            "evd_info": sum(1 for e in q["evds"] if e.get("result") == "info"),
            "evd_by_orc": 0,  # 0.1.0: orc không tự chạy lệnh nào; mọi EVD đến từ envelope (H2)
            "span_min": span,
            "commits": [f"{c['repo']}:{c['sha']}" for c in q["commits"]],
            "files_changed": len(changed),
            "files_outside_scope": outside,
            "code_outside_scope": code_outside,
        })
    return {"project": str(root), "rows": rows, "n_tasks": len(tasks),
            "kit_commits": commits(KIT, "main")}  # main = 0.1.0 đang chạy


def render(data: dict) -> str:
    rows = data["rows"]
    out = [f"# Baseline 0.1.0 — {data['project']}", "",
           "Sinh bởi `tools/phase0_baseline.py` (chỉ đọc). Số liệu tất định với cùng dữ liệu.", "",
           f"Task thật: **{data['n_tasks']}**, gom thành **{len(rows)}** yêu cầu.", "",
           "## Theo yêu cầu", "",
           "| Yêu cầu | Phiên | Task (coder) | Dừng chặng 1 | DEC Dung chốt | Gate ASK hiện tại "
           "| Hook Stop chặn | attempts | Review (lại / draft) | CTX (graph) | EVD pass/fail/info "
           "| Phút (mtime) | File đổi | Ngoài write_scope (code) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sess = ", ".join(f"{s}:{res}" for s, res in zip(r["sessions"], r["session_results"])) or "—"
        out.append(
            f"| {r['root']} {oc._short(r['title'], 40)} | {sess} | {r['tasks']} ({r['coder_tasks']}) "
            f"| {r['research_stops']} | {r['dung_decisions']} | {r['gate_reasons_now']} "
            f"| {r['stop_hook_blocks']} | {r['attempts']}"
            f"{' ' + ','.join(r['failure_classes']) if r['failure_classes'] else ''} "
            f"| {r['reviews']} ({r['re_reviews']} / {r['reviews_draft']}) | {r['ctx']} ({r['ctx_graph']}) "
            f"| {r['evd_pass']}/{r['evd_fail']}/{r['evd_info']} "
            f"| {r['span_min'] if r['span_min'] is not None else '—'} "
            f"| {r['files_changed'] if r['commits'] else '— (không ghép commit)'} "
            f"| {len(r['files_outside_scope'])} ({len(r['code_outside_scope'])}) |")
    tot = lambda k: sum(r[k] for r in rows)  # noqa: E731
    out += ["", "## Tổng", "",
            "| Chỉ số (mục O) | Giá trị | Nguồn |", "|---|---|---|",
            f"| Thời gian (phút, mtime đầu→cuối, tổng các yêu cầu) | "
            f"{sum(r['span_min'] or 0 for r in rows)} | mtime file ART/CTX/session — xấp xỉ, không gồm thời gian chờ trước file đầu tiên |",
            f"| Số lần dừng chờ Dung: chặng 1 | {tot('research_stops')} | ART research |",
            f"| Số câu Dung chốt (DEC) | {tot('dung_decisions')} | decisions.yaml theo scope |",
            f"| Phiên kết thúc `blocked` | {tot('blocked_sessions')} | sessions/S-x.md |",
            f"| Hook Stop chặn (handoff chưa hợp lệ) | {tot('stop_hook_blocks')} | runtime/sessions/*.yaml |",
            f"| Envelope bị từ chối | không đo được | 0.1.0 không ghi log khi `orc apply` từ chối |",
            f"| Review trả lại (attempts) | {tot('attempts')} | tasks.yaml |",
            f"| EVD tổng / do orc tự chạy | {tot('evd')} / {tot('evd_by_orc')} | evidence.yaml; mọi EVD là tự khai qua envelope (H2) |",
            f"| EVD `fail` | {tot('evd_fail')} | evidence.yaml |",
            f"| EVD `info` (phần lớn là \"chưa kiểm\") | {tot('evd_info')} | evidence.yaml |",
            f"| File commit ngoài write_scope (tổng / code) | {sum(len(r['files_outside_scope']) for r in rows)} / "
            f"{sum(len(r['code_outside_scope']) for r in rows)} | git show so với write_scope của task coder |",
            f"| Review report còn `draft` | {tot('reviews_draft')} / {tot('reviews')} | artifacts.yaml |",
            ""]
    out += ["## File ngoài write_scope (để người đọc phân loại)", ""]
    for r in rows:
        if r["files_outside_scope"]:
            out.append(f"- {r['root']}: " + ", ".join(f"`{f}`" for f in r["files_outside_scope"]))
    if not any(r["files_outside_scope"] for r in rows):
        out.append("- (không có)")
    out += ["", "## Commit đã ghép", ""]
    out += [f"- {r['root']}: {', '.join(r['commits']) or '(không có)'}" for r in rows]
    kc = data["kit_commits"]
    if kc:
        out += ["", "## Kit", "",
                f"- {len(kc)} commit, {kc[0][1][:10]} → {kc[-1][1][:10]}"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--app-repo", help="repo con, tương đối gốc dự án (ví dụ app)")
    ap.add_argument("--map", nargs="*", default=[], help="TASK-gốc=sha cho commit không nhắc ID")
    a = ap.parse_args(argv)
    mapping = dict(m.split("=", 1) for m in a.map)
    sys.stdout.write(render(measure(Path(a.project), a.app_repo, mapping)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
