"""F5 — quay lui dữ liệu `.orchestra/` từ v0.2 về schema 0.1.0 một cách an toàn.

    python tools/rollback_v02_to_v01.py --project D:/WMS --v01-kit C:/Users/quocd/orchestra-kit          # dry-run
    python tools/rollback_v02_to_v01.py --project D:/WMS --v01-kit C:/Users/quocd/orchestra-kit --apply

- Schema 0.1.0 lấy từ **chính code kit 0.1.0** (`--v01-kit`, FIELDS/enum của nó), không chép tay.
- Luôn chuyển trên **bản sao tạm** trước, rồi chạy `validate()` của kit 0.1.0 trên bản sao.
- `--apply` chỉ chạy khi: bản sao hợp lệ với 0.1.0, và `.orchestra/` trong git không có thay đổi chưa commit
  (để quay lại bằng git được). Trước khi ghi: chép nguyên `state/` vào `.orchestra/rollback-v0.2-<thời điểm>/`.
- Chuyển đổi: bỏ trường 0.1.0 không biết (task `level, risk_flags`; evidence `by`); kind evidence 0.1.0 không có
  (`typecheck, scope`) → `other` + ghi kind gốc vào đầu summary; file chỉ v0.2 (`journal.jsonl`, `approvals.yaml`,
  `checkpoints/`) chuyển vào thư mục sao lưu. Trạng thái 0.1.0 không biết ⇒ dừng, không đoán.
Không đụng code dự án, `runtime/` (gitignore), hay kit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

V02_ONLY = ["journal.jsonl", "approvals.yaml", "checkpoints"]
# Trạng thái task gốc K (Phase 4b) → trạng thái gần nhất của 0.1.0
K_TO_V01 = {"NEW": "pending", "TRIAGED": "pending", "PLANNED": "pending", "READY_FOR_IMPLEMENTATION": "pending",
            "APPROVAL_REQUIRED": "pending", "RESEARCHING": "dispatched", "IMPLEMENTING": "dispatched",
            "VERIFYING": "in_review", "DONE": "done", "INTEGRATED": "done", "BLOCKED": "blocked",
            "FAILED": "failed", "ABORTED": "failed"}


def load_v01(kit: Path):
    path = kit / "cli" / "orc_core.py"
    if not path.is_file():
        raise SystemExit(f"Không thấy {path}")
    sys.path.insert(0, str(kit / "cli"))
    spec = importlib.util.spec_from_file_location("orc_core_v01", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.path.pop(0)
    if "OPTIONAL_FIELDS" in vars(mod) or "journal_path" in vars(mod):
        raise SystemExit(f"{kit} không phải kit 0.1.0 (có tính năng v0.2)")
    return mod


def transform(v01, root: Path) -> list:
    """Chuyển registry ở `root` về schema 0.1.0. Trả danh sách thay đổi (để báo cáo)."""
    notes = []
    for kind in v01.KINDS:
        items = v01.load_registry(root, kind)
        allowed = v01.FIELDS[kind]
        for e in items:
            if not isinstance(e, dict):
                continue
            extra = [k for k in e if k not in allowed]
            for k in extra:
                if e[k] not in (None, [], "agent"):
                    notes.append(f"{e.get('id')}: bỏ {k}={e[k]!r}")
                del e[k]
            if kind == "evidence" and e.get("kind") not in v01.EVD_KINDS:
                old = e["kind"]
                e["kind"] = "other"
                e["summary"] = (f"[v0.2 {old}] " + str(e.get("summary") or ""))[: v01.SUMMARY_MAX]
                notes.append(f"{e['id']}: kind {old} → other")
            if kind == "task":
                for f in ("status", "resume_status"):
                    if e.get(f) in K_TO_V01:
                        notes.append(f"{e.get('id')}: {f} {e[f]} → {K_TO_V01[e[f]]}")
                        e[f] = K_TO_V01[e[f]]
                if e.get("failure_class") not in (None, *v01.FAILURE_CLASSES):
                    notes.append(f"{e.get('id')}: bỏ failure_class {e['failure_class']}")
                    e["failure_class"] = None
                if e.get("status") not in v01.TASK_STATUS:
                    raise SystemExit(f"{e.get('id')}: trạng thái '{e.get('status')}' 0.1.0 không có — dừng, không đoán")
        v01.save_registry(root, kind, items)
    return notes


def move_v02_only(state: Path, dest: Path) -> list:
    moved = []
    for name in V02_ONLY:
        p = state / name
        if p.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest / name))
            moved.append(name)
    return moved


def git_dirty(root: Path) -> list | None:
    r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", ".orchestra"],
                       capture_output=True, text=True, encoding="utf-8")
    return None if r.returncode else [l for l in r.stdout.splitlines() if l.strip()]


def run(project: Path, kit: Path, apply: bool) -> int:
    v01 = load_v01(kit)
    root = project.resolve()
    if not (root / ".orchestra" / "config.yaml").is_file():
        raise SystemExit(f"{root} không có .orchestra/config.yaml")
    before = v01.validate(root)
    print(f"validate 0.1.0 trên dữ liệu hiện tại: {'OK' if not before else f'{len(before)} lỗi'}")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        shutil.copytree(root / ".orchestra", tmp / ".orchestra", ignore=shutil.ignore_patterns("runtime", "cache"))
        notes = transform(v01, tmp)
        moved = move_v02_only(tmp / ".orchestra" / "state", tmp / "_v02")
        errs = v01.validate(tmp)
    print(f"bản sao sau chuyển: {len(notes)} thay đổi trường, chuyển ra {moved or 'không có file v0.2'}")
    for n in notes[:30]:
        print(f"  - {n}")
    if errs:
        print("validate 0.1.0 trên bản sao: LỖI — không quay lui được tự động:")
        print("\n".join(f"  - {e}" for e in errs[:30]))
        return 2
    print("validate 0.1.0 trên bản sao: OK")
    if not apply:
        print("dry-run: chưa ghi gì. Thêm --apply để quay lui thật.")
        return 0
    dirty = git_dirty(root)
    if dirty is None:
        raise SystemExit("Dự án không phải git repo: không quay lui (cần git để khôi phục nếu sai)")
    if dirty:
        raise SystemExit("`.orchestra/` có thay đổi chưa commit — commit trước rồi chạy lại:\n" + "\n".join(dirty))
    backup = root / ".orchestra" / f"rollback-v0.2-{dt.datetime.now():%Y%m%d%H%M%S}"
    shutil.copytree(root / ".orchestra" / "state", backup / "state")
    transform(v01, root)
    move_v02_only(root / ".orchestra" / "state", backup / "v02-only")
    after = v01.validate(root)
    print(f"đã quay lui; sao lưu: {backup.relative_to(root).as_posix()}; validate 0.1.0: "
          + ("OK" if not after else f"{len(after)} lỗi"))
    return 0 if not after else 2


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Quay lui .orchestra/ v0.2 → 0.1.0")
    ap.add_argument("--project", required=True)
    ap.add_argument("--v01-kit", required=True, help="thư mục kit 0.1.0 (có cli/orc_core.py)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    return run(Path(a.project), Path(a.v01_kit), a.apply)


if __name__ == "__main__":
    sys.exit(main())
