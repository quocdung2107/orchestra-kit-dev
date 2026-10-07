"""Phê duyệt của Dung (v0.2 N2; ADJUSTMENTS #4).

Approval bind với TASK + PLAN_HASH + WRITE_SCOPE_HASH + LEVEL + RISK_FLAGS + NONCE:
- `request`: orc tính binding, sinh nonce dùng một lần, in dòng Dung phải gõ `orc:approve TASK-x NONCE`.
- `approve`: chỉ nhận khi hook UserPromptSubmit đã ghi đúng dòng đó **sau** lúc yêu cầu, nonce chưa dùng và
  binding tính lại khớp. Plan, write_scope, level hoặc risk_flags đổi ⇒ approval cũ hết hiệu lực (`check`).
Giới hạn: process cùng user vẫn ghi thêm được dòng vào prompts.jsonl; chuỗi hash phát hiện sửa dòng cũ, không ngăn
thêm dòng mới (v0.2 N2). Guard (Phase 4) chặn tool ghi vào runtime/.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
from pathlib import Path

import orc_core as oc
import orc_guard

APPROVALS = "approvals.yaml"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def path(root: Path) -> Path:
    return oc.orc(root) / "state" / APPROVALS


def load(root: Path) -> list:
    return oc.load_yaml_file(path(root)) or []


def save(root: Path, items: list) -> None:
    oc.write_text(path(root), "# Phê duyệt (orc approve). Không sửa tay.\n" + oc.dump_yaml(items))


def plan_ids(root: Path, task: dict) -> list:
    ids = {str(a).split("#")[0] for a in oc.as_list(task.get("acceptance"))}
    for i in oc.as_list(task.get("inputs")):
        if oc.is_id(i) and oc.kind_of(i) == "artifact":
            ids.add(i)
    out = []
    for i in sorted(ids):
        try:
            if oc.find_entry(root, i)[2].get("type") == "plan":
                out.append(i)
        except oc.OrcError:
            out.append(i)  # tham chiếu gãy cũng đưa vào hash: đổi được phát hiện
    return out


def binding(root: Path, tid: str) -> dict:
    _, _, task = oc.find_entry(root, tid)
    parts = []
    for i in plan_ids(root, task):
        p = oc.content_path(root, i)
        body = oc.split_frontmatter(oc.read_text(p))[1] if p.exists() else "(mất)"
        parts.append(f"{i}\n{body}")
    return {"task": tid, "plans": plan_ids(root, task),
            "plan_hash": _sha("\n\0".join(parts)),
            "write_scope_hash": _sha(json.dumps(sorted(map(str, oc.as_list(task.get("write_scope")))))),
            "level": task.get("level"),
            "risk_flags": sorted(oc.as_list(task.get("risk_flags")))}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="microseconds")


def request(root: Path, tid: str) -> str:
    b = binding(root, tid)
    items = load(root)
    for a in items:
        if a.get("task") == tid and a.get("status") == "pending":
            a["status"] = "expired"
    nonce = secrets.token_hex(3).upper()
    items.append({"task": tid, "nonce": nonce, "status": "pending", "requested_at": _now(), "binding": b})
    save(root, items)
    _, _, task = oc.find_entry(root, tid)
    return (f"Dung gõ đúng dòng sau để duyệt {tid}:\n  orc:approve {tid} {nonce}\n"
            f"({oc._short(task.get('title'), 60)}; plan {', '.join(b['plans']) or '—'}; "
            f"write_scope {len(oc.as_list(task.get('write_scope')))} mục; level {b['level']}; "
            f"risk {b['risk_flags'] or '[]'})")


def prompt_lines(root: Path) -> list:
    """Dòng prompts.jsonl đã kiểm chuỗi hash. Chuỗi gãy ⇒ OrcError (không tin nhật ký đã bị sửa)."""
    p = orc_guard.prompts_path(root)
    if not p.exists():
        return []
    out, prev = [], "0" * 64
    for n, line in enumerate((l for l in oc.read_text(p).splitlines() if l.strip()), 1):
        rec = json.loads(line)
        if rec.get("prev") != prev:
            raise oc.OrcError(f"prompts.jsonl dòng {n}: chuỗi hash gãy — nhật ký lời Dung bị sửa, không duyệt")
        prev = _sha(line)
        out.append(rec)
    return out


def approve(root: Path, tid: str) -> dict:
    items = load(root)
    pend = [a for a in items if a.get("task") == tid and a.get("status") == "pending"]
    if not pend:
        raise oc.OrcError(f"{tid}: chưa có yêu cầu duyệt; chạy `orc approval request {tid}`")
    req = pend[-1]
    want = f"orc:approve {tid} {req['nonce']}".lower()
    hit = None
    for rec in prompt_lines(root):
        if rec.get("ts", "") <= req["requested_at"]:
            continue
        if any(" ".join(l.split()).lower() == want for l in rec.get("orc") or []):
            hit = rec
            break
    if hit is None:
        raise oc.OrcError(f"{tid}: chưa thấy Dung gõ `orc:approve {tid} {req['nonce']}` sau lúc yêu cầu "
                          f"({req['requested_at']})")
    now = binding(root, tid)
    if now != req["binding"]:
        changed = [k for k in now if now[k] != req["binding"].get(k)]
        req["status"] = "expired"
        save(root, items)
        raise oc.OrcError(f"{tid}: {', '.join(changed)} đã đổi sau yêu cầu duyệt; tạo yêu cầu mới")
    req.update(status="used", approved_at=_now(), prompt_sha256=hit["sha256"], session=hit.get("session"))
    save(root, items)
    with oc.journal_context(extra={"event": "approve", "nonce": req["nonce"]}):
        _, _, task = oc.find_entry(root, tid)
        oc.append_journal(root, [{"id": tid, "from": task.get("status"), "to": task.get("status")}])
    return req


def check(root: Path, tid: str) -> tuple:
    """(còn hiệu lực?, lý do)."""
    used = [a for a in load(root) if a.get("task") == tid and a.get("status") == "used"]
    if not used:
        return False, "chưa có approval"
    now = binding(root, tid)
    if now != used[-1]["binding"]:
        changed = [k for k in now if now[k] != used[-1]["binding"].get(k)]
        return False, f"hết hiệu lực: {', '.join(changed)} đã đổi sau khi duyệt"
    return True, f"approval {used[-1]['nonce']} lúc {used[-1]['approved_at']}"


def shadow_log(root: Path, event: dict) -> None:
    p = oc.orc(root) / "runtime" / "shadow.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), **event}, ensure_ascii=False) + "\n")
