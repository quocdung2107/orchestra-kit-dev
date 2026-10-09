"""`orc triage` — tính level tất định (v0.2 H1–H3; ADJUSTMENTS #6). Phase 5: **shadow**.

Mức = max các luật khớp (bảng H2). Tín hiệu máy: risk_paths L3, số file, số dòng diff, số module. Form khai báo có/không.
Ba lần tính (TRIAGED, PLANNED, VERIFYING); mỗi lần chỉ tăng so với lần trước. Thiếu dữ kiện ⇒ tối thiểu L1 — nhỏ
không mặc định an toàn. Shadow: ghi journal `event: triage`, không ghi `task.level`, không đổi luồng K.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import orc_core as oc
import orc_guard

FORM_L3 = ("schema_change", "data_migration", "security", "irreversible")
FORM_L2 = ("public_api", "new_dependency", "external_service", "user_visible", "uncertain")
FORM_KEYS = FORM_L3 + FORM_L2
DEFAULTS = {
    "mode": "shadow",
    "risk_paths_l3": ["**/migrations/", "supabase/", "**/auth/", "**/*rls*", "**/.github/", ".claude/", ".orchestra/",
                      "**/package.json", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock",
                      "**/.env", "**/.env.*"],
    "l3": {"files": 15, "lines": 400, "modules": 3},
    "l2": {"files": 5, "lines": 120, "modules": 1},
    "l0": {"files": 2, "lines": 40},
    "module_roots": [],
}


def config(root: Path) -> dict:
    user = oc.load_config(root).get("triage") or {}
    cfg = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def module_of(path: str, roots) -> str:
    """Tối đa 2 cấp thư mục dưới root dài nhất chứa path; không có root ⇒ 2 cấp thư mục đầu."""
    p = orc_guard._norm(path).rstrip("/")
    dirs = p.split("/")[:-1]
    for r in sorted((orc_guard._norm(x).rstrip("/") for x in roots or []), key=len, reverse=True):
        if r and (p == r or p.startswith(r + "/")):
            rest = p[len(r) + 1:].split("/")[:-1]
            return "/".join([r, *rest[:2]])
    return "/".join(dirs[:2]) or "."


def classify(files, lines, form, cfg) -> tuple:
    """(level, [luật khớp]). files: list đường dẫn hoặc None (chưa biết); lines: int hoặc None; form: dict hoặc None."""
    rules = []
    form = form or {}
    if files:
        risky = [f for f in files if orc_guard.match_path(f, cfg["risk_paths_l3"])]
        if risky:
            rules.append(("L3", f"risk_path: {', '.join(sorted(risky)[:5])}"))
    for k in FORM_L3:
        if form.get(k) is True:
            rules.append(("L3", f"form: {k}"))
    n_files = len(files) if files is not None else None
    n_mod = len({module_of(f, cfg["module_roots"]) for f in files}) if files else None
    if (n_files or 0) > cfg["l3"]["files"] or (lines or 0) > cfg["l3"]["lines"] or (n_mod or 0) > cfg["l3"]["modules"]:
        rules.append(("L3", f"kích thước: {n_files} file, {lines} dòng, {n_mod} module"))
    for k in FORM_L2:
        if form.get(k) is True:
            rules.append(("L2", f"form: {k}"))
    if (n_mod or 0) > cfg["l2"]["modules"] or (n_files or 0) > cfg["l2"]["files"] or (lines or 0) > cfg["l2"]["lines"]:
        rules.append(("L2", f"kích thước: {n_files} file, {lines} dòng, {n_mod} module"))
    if rules:
        return max(int(r[0][1]) for r in rules), rules
    all_no = form and all(form.get(k) is False for k in FORM_KEYS)
    small = (n_files is not None and n_files <= cfg["l0"]["files"] and n_mod == 1
             and (lines is None or lines <= cfg["l0"]["lines"]))
    if all_no and small:
        return 0, [("L0", f"{n_files} file, {lines if lines is not None else '?'} dòng, 1 module, form không cờ")]
    why = "thiếu dữ kiện (không mặc định L0)" if n_files is None or not form else f"{n_files} file, {n_mod} module"
    return 1, [("L1", why)]


# ---------------------------------------------------------------- dữ kiện theo lần tính

def _repos(root: Path) -> list:
    v = oc.load_config(root).get("verify") or {}
    return [str(r).strip("/") or "." for r in oc.as_list(v.get("repos"))] or ["."]


def expand_scope(root: Path, patterns) -> list:
    """Đếm file thật khớp write_scope (git ls-files ở các repo); mẫu không khớp file nào tính là 1 file sẽ tạo."""
    tracked = []
    for rel in _repos(root):
        r = subprocess.run(["git", "-C", str(root / rel), "ls-files", "-z"], capture_output=True)
        if r.returncode == 0:
            pre = "" if rel == "." else rel + "/"
            tracked += [pre + f for f in r.stdout.decode("utf-8", "replace").split("\0") if f]
    out = set()
    for p in patterns:
        hit = [f for f in tracked if orc_guard.match_path(f, [p])]
        out |= set(hit) if hit else {orc_guard._norm(p).rstrip("/")}
    return sorted(out)


def diff_stats(root: Path, tids) -> tuple:
    """(file đổi, số dòng thêm+xoá) kể từ checkpoint của các task coder."""
    import orc_verify  # noqa: PLC0415
    files, lines = set(), 0
    for tid in tids:
        try:
            cp = orc_verify.load_checkpoint(root, tid)
        except oc.OrcError:
            continue
        changed, ignored_new = orc_verify.changed_files(root, cp)
        files |= set(changed) | set(ignored_new)
        for rel, snap in cp["repos"].items():
            r = subprocess.run(["git", "-C", str(root / rel), "diff", "--numstat", snap["head"]], capture_output=True)
            for line in r.stdout.decode("utf-8", "replace").splitlines():
                a, d, *_ = line.split("\t")
                lines += (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
    return sorted(files), lines


def _events(root: Path, tid: str) -> list:
    p = oc.journal_path(root)
    rows = [json.loads(l) for l in oc.read_text(p).splitlines() if l.strip()] if p.exists() else []
    return [r for r in rows if r.get("id") == tid and r.get("event") in ("triage", "downgrade")]


def current(root: Path, tid: str):
    ev = _events(root, tid)
    return ev[-1]["level"] if ev else None


def run(root: Path, tid: str, stage: int, form=None, paths=None) -> dict:
    """Tính một lần triage cho task gốc K (hoặc task bất kỳ có write_scope); ghi journal (shadow)."""
    import orc_k  # noqa: PLC0415
    cfg = config(root)
    _, _, t = oc.find_entry(root, tid)
    prev_form = next((e.get("form") for e in reversed(_events(root, tid)) if e.get("form")), None)
    form = form if form is not None else prev_form
    files, lines = None, None
    kids = orc_k.coders(root, tid) if orc_k.is_root(t) else [t]
    if stage == 1:
        files = [orc_guard._norm(p) for p in paths] if paths else None
    elif stage == 2:
        files = expand_scope(root, sorted({str(s) for k in kids for s in oc.as_list(k.get("write_scope"))}))
    elif stage == 3:
        files, lines = diff_stats(root, [k["id"] for k in kids])
    else:
        raise oc.OrcError("stage phải là 1, 2 hoặc 3")
    computed, rules = classify(files, lines, form, cfg)
    prev = current(root, tid)
    level = max(computed, prev) if prev is not None else computed
    rec = {"event": "triage", "stage": stage, "level": level, "computed": computed, "previous": prev,
           "rules": [f"{lv}: {why}" for lv, why in rules], "files": len(files) if files is not None else None,
           "lines": lines, "form": form, "mode": cfg["mode"]}
    with oc.journal_context(extra=rec):
        oc.append_journal(root, [{"id": tid}])
    import orc_approval  # noqa: PLC0415
    orc_approval.shadow_log(root, {"task": tid, **rec})
    return rec


def downgrade(root: Path, tid: str, to: int, reason: str) -> dict:
    """Hạ mức chỉ khi Dung gõ `orc:downgrade TASK L<n> <lý do>` sau lần triage gần nhất (v0.2 H3)."""
    ev = _events(root, tid)
    if not ev:
        raise oc.OrcError(f"{tid}: chưa có triage để hạ")
    prefix = f"orc:downgrade {tid} L{to}".lower()
    import orc_approval  # noqa: PLC0415
    ok = any(r.get("ts", "") > ev[-1]["ts"] and any(" ".join(l.split()).lower().startswith(prefix)
                                                     for l in r.get("orc") or [])
             for r in orc_approval.prompt_lines(root))
    if not ok:
        raise oc.OrcError(f"{tid}: chưa thấy Dung gõ `orc:downgrade {tid} L{to} <lý do>` sau lần triage gần nhất")
    rec = {"event": "downgrade", "level": int(to), "previous": ev[-1]["level"], "reason": reason[:200],
           "mode": config(root)["mode"]}
    with oc.journal_context(extra=rec):
        oc.append_journal(root, [{"id": tid}])
    return rec


def show(root: Path, tid: str) -> str:
    ev = _events(root, tid)
    if not ev:
        return f"{tid}: chưa triage\n"
    out = [f"{tid}: level {ev[-1]['level']} (shadow — chưa ghi vào task)"]
    for e in ev:
        if e["event"] == "downgrade":
            out.append(f"- {e['ts'][:19]} hạ L{e['previous']} → L{e['level']} (Dung): {e.get('reason')}")
        else:
            out.append(f"- {e['ts'][:19]} lần {e['stage']}: tính L{e['computed']}, ghi L{e['level']}"
                       f" ({e.get('files')} file, {e.get('lines')} dòng) — " + "; ".join(e.get("rules") or []))
    return "\n".join(out) + "\n"


def render(rec: dict) -> str:
    return (f"TRIAGE (shadow) lần {rec['stage']}: L{rec['level']} (tính L{rec['computed']}"
            + (f", trước L{rec['previous']}" if rec.get("previous") is not None else "") + ") — "
            + "; ".join(rec["rules"]))


def load_form(path) -> dict:
    data = oc._yaml().safe_load(Path(path).read_text(encoding="utf-8")) if path else None
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) - set(FORM_KEYS):
        raise oc.OrcError(f"form chỉ gồm khoá {', '.join(FORM_KEYS)} (giá trị true/false)")
    if any(not isinstance(v, bool) for v in data.values()):
        raise oc.OrcError("form: mỗi giá trị phải là true hoặc false")
    return data
