"""State machine K (v0.2 mục K + I2; ADJUSTMENTS #2, #6; Dung chốt 2026-10-09 phương án A).

Phương án A (khi chưa gộp agent — Phase 7):
- **Task gốc** của yêu cầu (`workflow: k`, tạo bằng `orc new request`) đi K:
  NEW → TRIAGED → RESEARCHING → PLANNED → READY_FOR_IMPLEMENTATION (L0/L1) | APPROVAL_REQUIRED (L2/L3, chưa phân
  mức) → IMPLEMENTING → VERIFYING → DONE → INTEGRATED; phụ BLOCKED · FAILED · ABORTED.
  Chặng hiểu & thiết kế luôn dừng (ADJ #2) ⇒ không có TRIAGED → PLANNED.
- **Task con** (`parent`) giữ vòng ngắn pending → ready → dispatched → in_review → done, nhưng:
  task coder chỉ giao khi gốc ở IMPLEMENTING và approval của gốc còn hiệu lực; chỉ done khi lần `orc verify` sau khi
  nộp là PASS. Thất bại theo bảng I2 (RETRY/REPAIR/ROLLBACK/ESCALATE/ABORT); ROLLBACK chỉ in lệnh cho Dung.
- BLOCKED → trạng thái trước: `orc resume` khi Dung gõ `orc:resume GỐC`; ABORTED: `orc abort` khi Dung gõ `orc:abort GỐC`.
"""

from __future__ import annotations

import json
from pathlib import Path

import orc_core as oc

K_STATES = ("NEW", "TRIAGED", "RESEARCHING", "PLANNED", "READY_FOR_IMPLEMENTATION", "APPROVAL_REQUIRED",
            "IMPLEMENTING", "VERIFYING", "DONE", "INTEGRATED", "BLOCKED", "FAILED", "ABORTED")
CLOSED = ("done", "DONE", "INTEGRATED", "ABORTED")
K_MOVES = {
    ("NEW", "TRIAGED"), ("TRIAGED", "RESEARCHING"), ("RESEARCHING", "PLANNED"),
    ("PLANNED", "READY_FOR_IMPLEMENTATION"), ("PLANNED", "APPROVAL_REQUIRED"),
    ("READY_FOR_IMPLEMENTATION", "IMPLEMENTING"), ("APPROVAL_REQUIRED", "IMPLEMENTING"),
    ("IMPLEMENTING", "VERIFYING"), ("VERIFYING", "DONE"), ("VERIFYING", "IMPLEMENTING"), ("DONE", "INTEGRATED"),
}
RECOVERY = ("RETRY", "REPAIR", "ROLLBACK", "ESCALATE", "ABORT")
VERIFY_FAILURE = {"test": "TEST_FAILURE", "lint": "LINT_FAILURE", "build": "BUILD_FAILURE",
                  "typecheck": "TYPECHECK_FAILURE"}


def is_root(t: dict) -> bool:
    return (t or {}).get("workflow") == "k"


def is_closed(status) -> bool:
    return status in CLOSED


def k_project(root: Path) -> bool:
    return oc.load_config(root).get("workflow") == "k"


def parent_of(root: Path, t: dict):
    p = t.get("parent")
    return oc.find_entry(root, p)[2] if p else None


def children(root: Path, rid: str, tasks=None) -> list:
    return [t for t in (tasks or oc.load_registry(root, "task")) if t.get("parent") == rid]


def coders(root: Path, rid: str, tasks=None) -> list:
    return [t for t in children(root, rid, tasks) if oc.agent_for(t.get("owner")) == "coder"]


def child_arts(root: Path, rid: str, type_: str) -> list:
    kids = {t["id"] for t in children(root, rid)}
    return [a for a in oc.load_registry(root, "artifact") if a.get("task") in kids and a.get("type") == type_]


def request_ids(root: Path, rid: str) -> list:
    """Mọi ID thuộc yêu cầu (gốc, task con, artifact của chúng) — để gom DEC proposed vào một lần duyệt."""
    kids = [t["id"] for t in children(root, rid)]
    arts = [a["id"] for a in oc.load_registry(root, "artifact") if a.get("task") in set(kids)]
    return [rid, *kids, *arts]


# ---------------------------------------------------------------- I2: failure_class → recovery_action

def recovery(fc: str, level, attempts: int) -> str:
    """Bảng I2 (tất định). level None = chưa phân mức ⇒ coi như L2 (ADJ #6: nhỏ không mặc định an toàn)."""
    lv = 2 if level is None else int(level)
    if fc in ("ENVIRONMENT_FAILURE", "VALIDATION"):
        return "ESCALATE"  # RETRY tự động chỉ khi idempotent; orc không tự chạy lại — người quyết
    if fc in ("TEST_FAILURE", "LINT_FAILURE", "BUILD_FAILURE", "TYPECHECK_FAILURE", "IMPL_BUG"):
        return "REPAIR" if lv <= 2 and attempts <= oc.MAX_ATTEMPTS else "ESCALATE"
    if fc in ("REGRESSION", "SCOPE_VIOLATION"):
        return "ROLLBACK"  # rồi ESCALATE
    if fc == "SPEC_GAP":
        return "REPAIR" if lv <= 1 else "ESCALATE"
    if fc == "INTERNAL":
        return "ABORT"
    return "ESCALATE"  # DECISION_CONFLICT, CONTEXT_CONFLICT, APPROVAL_MISSING, REVIEW_REJECT, khác


# ---------------------------------------------------------------- task gốc

def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise oc.OrcError(msg)


def advance_root(root: Path, e: dict, to: str) -> tuple:
    """Chuyển task gốc theo bảng K, kiểm điều kiện. Trả (entry, ghi chú in cho A)."""
    rid, frm = e["id"], e.get("status")
    if (frm, to) not in K_MOVES:
        allowed = sorted(t for f, t in K_MOVES if f == frm)
        hint = {"BLOCKED": f"`orc resume {rid}` sau khi Dung gõ `orc:resume {rid}`"}.get(frm)
        raise oc.OrcError(f"{rid}: K không có {frm} → {to}"
                          + (f" (được: {', '.join(allowed)})" if allowed else "")
                          + (f"; {hint}" if hint else ""))
    note = ""
    tasks = oc.load_registry(root, "task")
    kids = coders(root, rid, tasks)
    level = e.get("level")
    if to == "PLANNED":
        res = [a for a in child_arts(root, rid, "research") if a.get("status") != "rejected"]
        _need(res, f"{rid}: chưa có ART research của yêu cầu (chặng hiểu & thiết kế luôn dừng — ADJ #2)")
        for a in res:
            oc.ask_text(root, a["id"])  # còn mục chưa điền ⇒ OrcError
        _need([a for a in child_arts(root, rid, "plan") if a.get("status") == "accepted"],
              f"{rid}: chưa có plan accepted (`orc gate` PROCEED rồi `orc advance PLAN --to accepted`)")
        _need(kids, f"{rid}: chưa có task coder (`orc new task --from PLAN`)")
    elif to == "READY_FOR_IMPLEMENTATION":
        _need(level in (0, 1), f"{rid}: level {level if level is not None else 'chưa phân mức'} ⇒ chỉ được "
                               "APPROVAL_REQUIRED (Q2; READY_FOR_IMPLEMENTATION chỉ cho L0/L1)")
    elif to == "IMPLEMENTING":
        import orc_approval  # noqa: PLC0415
        ok, why = orc_approval.check(root, rid)
        _need(ok, f"{rid}: APPROVAL_MISSING — {why}; Dung gõ dòng `orc:approve ...` rồi `orc approve ...`")
        if level == 3:
            _need([d for d in oc.load_registry(root, "decision") if d.get("status") == "accepted"
                   and d.get("scope") in set(request_ids(root, rid))], f"{rid}: L3 cần DEC accepted của yêu cầu")
    elif to == "VERIFYING":
        bad = [t["id"] for t in kids if t.get("status") not in ("in_review", "done")]
        _need(not bad, f"{rid}: task coder chưa nộp/đang chặn: {', '.join(bad)}")
    elif to == "DONE":
        bad = [t["id"] for t in kids if t.get("status") != "done"]
        _need(not bad, f"{rid}: task coder chưa done: {', '.join(bad)}")
    elif frm == "VERIFYING" and to == "IMPLEMENTING":
        _need([t for t in kids if t.get("status") != "done"], f"{rid}: mọi task coder đã done — advance DONE")
    entry = oc.set_fields(root, rid, {"status": to})
    if to in ("APPROVAL_REQUIRED", "READY_FOR_IMPLEMENTATION"):
        import orc_approval  # noqa: PLC0415
        ids = [rid] + [a["id"] for a in child_arts(root, rid, "research") if a.get("status") == "draft"]
        scope = set(request_ids(root, rid))
        ids += [d["id"] for d in oc.load_registry(root, "decision")
                if d.get("status") == "proposed" and d.get("scope") in scope]
        note = orc_approval.request(root, ids)
    return entry, note


def child_dispatch_check(root: Path, t: dict) -> None:
    """Task coder của yêu cầu K chỉ giao khi gốc IMPLEMENTING và approval của gốc còn hiệu lực (AC-4b.2)."""
    p = parent_of(root, t)
    if not is_root(p) or oc.agent_for(t.get("owner")) != "coder":
        return
    _need(p.get("status") == "IMPLEMENTING",
          f"{t['id']}: APPROVAL_MISSING — task gốc {p['id']} đang {p.get('status')}, chưa IMPLEMENTING")
    import orc_approval  # noqa: PLC0415
    ok, why = orc_approval.check(root, p["id"])
    _need(ok, f"{t['id']}: APPROVAL_MISSING — {p['id']}: {why}")


# ---------------------------------------------------------------- cổng verify trước khi done

def _journal(root: Path) -> list:
    p = oc.journal_path(root)
    return [json.loads(l) for l in oc.read_text(p).splitlines() if l.strip()] if p.exists() else []


def verify_gate(root: Path, t: dict) -> tuple:
    """(failure_class | None, chi tiết) từ lần `orc verify` mới nhất **sau** lần nộp gần nhất. Chưa có ⇒ OrcError."""
    _need(oc.load_config(root).get("verify"), f"{t['id']}: dự án K phải có mục `verify:` trong config (Q3)")
    rows = _journal(root)
    sub = max((i for i, r in enumerate(rows) if r.get("id") == t["id"] and r.get("to") == "in_review"), default=-1)
    ver = [r for r in rows[sub + 1:] if r.get("id") == t["id"] and r.get("event") == "verify"]
    _need(ver, f"{t['id']}: chưa chạy `orc verify {t['id']}` sau lần nộp gần nhất — chạy rồi nạp lại kết quả review")
    evd = {e["id"]: e for e in oc.load_registry(root, "evidence")}
    run = [evd[i] for i in ver[-1].get("evidence_ids", []) if i in evd]
    scope = [e for e in run if e.get("kind") == "scope"]
    if scope and scope[0].get("result") != "pass":
        return "SCOPE_VIOLATION", f"scope fail ({scope[0]['id']})"
    fails = [e for e in run if e.get("result") == "fail"]
    if fails:
        return VERIFY_FAILURE.get(fails[0].get("kind"), "TEST_FAILURE"), f"{fails[0]['id']}: {fails[0]['summary']}"
    env = [e for e in run if e.get("result") == "info"]
    if env:
        return "ENVIRONMENT_FAILURE", f"{env[0]['id']}: {env[0]['summary']}"
    return None, f"verify PASS ({', '.join(e['id'] for e in run)})"


def rollback_hint(root: Path, tid: str) -> str:
    """Lệnh Dung tự chạy để bỏ thay đổi của task (orc không tự reset — deny_always)."""
    try:
        import orc_verify  # noqa: PLC0415
        cp = orc_verify.load_checkpoint(root, tid)
    except oc.OrcError:
        return "không có checkpoint — xem `git diff` và khôi phục tay"
    return "; ".join(f"git -C {rel} diff {s['head']}  (xem) · git -C {rel} checkout {s['head']} -- <file cần bỏ>"
                     for rel, s in cp["repos"].items())


def escalate(root: Path, t: dict, reason: str) -> None:
    """ESCALATE ở task con ⇒ task gốc BLOCKED (nhớ trạng thái để resume)."""
    p = parent_of(root, t)
    if is_root(p) and p.get("status") not in ("BLOCKED", *CLOSED):
        with oc.journal_context(extra={"reason": oc._short(reason, 200), "from_task": t["id"]}):
            oc.set_fields(root, p["id"], {"status": "BLOCKED", "resume_status": p["status"], "needs_user": True})


def review_route(root: Path, task: dict, env: dict) -> tuple:
    """Định tuyến kết quả review cho task coder của yêu cầu K (I2). Trả (thay đổi task, route, escalate?)."""
    level = (parent_of(root, task) or {}).get("level")
    attempts = int(task.get("attempts") or 0)
    fc = env.get("failure_class")
    if env["status"] == "done" and not fc:
        fc, detail = verify_gate(root, task)
        if fc is None:
            return {"status": "done", "failure_class": None, "recovery_action": None}, f"done — {detail}", False
    else:
        detail = env.get("summary", "")
    action = recovery(fc, level, attempts + 1 if fc != "ENVIRONMENT_FAILURE" else attempts)
    ch = {"failure_class": fc, "recovery_action": action}
    if action == "REPAIR":
        if fc == "SPEC_GAP":  # L0/L1: lập lại plan như 0.1.0
            return None, "", False
        ch.update(status="ready", attempts=attempts + 1)
        return ch, f"REPAIR {fc}: trả về coder (attempt {attempts + 1}) — {detail}", False
    if action == "ROLLBACK":
        ch.update(status="blocked", needs_user=True)
        return ch, f"ROLLBACK + ESCALATE {fc}: Dung tự bỏ thay đổi — {rollback_hint(root, task['id'])}", True
    ch.update(status="blocked", needs_user=True)
    return ch, f"ESCALATE {fc}: HỎI DUNG — {detail}", True


# ---------------------------------------------------------------- lời Dung: resume / abort

def _dung_said(root: Path, line: str, after: str) -> bool:
    import orc_approval  # noqa: PLC0415
    want = " ".join(line.split()).lower()
    return any(r.get("ts", "") > after and any(" ".join(l.split()).lower() == want for l in r.get("orc") or [])
               for r in orc_approval.prompt_lines(root))


def _last_row_ts(root: Path, rid: str, to=None) -> str:
    rows = [r for r in _journal(root) if r.get("id") == rid and (to is None or r.get("to") == to)]
    return rows[-1]["ts"] if rows else ""


def resume(root: Path, rid: str) -> dict:
    _, _, e = oc.find_entry(root, rid)
    _need(is_root(e) and e.get("status") == "BLOCKED", f"{rid}: chỉ resume task gốc K đang BLOCKED")
    _need(_dung_said(root, f"orc:resume {rid}", _last_row_ts(root, rid, "BLOCKED")),
          f"{rid}: chưa thấy Dung gõ `orc:resume {rid}` sau lúc bị chặn")
    tasks = oc.load_registry(root, "task")
    for t in children(root, rid, tasks):
        if t.get("status") in ("blocked", "failed") and t.get("needs_user"):
            oc.set_fields(root, t["id"], {"status": "ready", "needs_user": False, "recovery_action": None})
    return oc.set_fields(root, rid, {"status": e.get("resume_status") or "IMPLEMENTING",
                                     "resume_status": None, "needs_user": False})


def abort(root: Path, rid: str) -> dict:
    _, _, e = oc.find_entry(root, rid)
    _need(is_root(e) and not is_closed(e.get("status")), f"{rid}: chỉ huỷ task gốc K chưa đóng")
    _need(_dung_said(root, f"orc:abort {rid}", _last_row_ts(root, rid)),
          f"{rid}: chưa thấy Dung gõ `orc:abort {rid}` sau lần đổi trạng thái gần nhất")
    return oc.set_fields(root, rid, {"status": "ABORTED", "needs_user": False})


def next_lines(root: Path, tasks: list) -> list:
    hint = {"NEW": "orc advance {id} --to TRIAGED", "TRIAGED": "orc advance {id} --to RESEARCHING",
            "RESEARCHING": "chặng 1 (researcher) → plan accepted → orc advance {id} --to PLANNED",
            "PLANNED": "orc advance {id} --to APPROVAL_REQUIRED (in dòng Dung phải gõ)",
            "APPROVAL_REQUIRED": "chờ Dung gõ dòng orc:approve → orc approve … → orc advance {id} --to IMPLEMENTING",
            "READY_FOR_IMPLEMENTATION": "chờ Dung xác nhận (orc:approve) → orc advance {id} --to IMPLEMENTING",
            "IMPLEMENTING": "giao task coder (READY bên dưới); nộp hết → orc advance {id} --to VERIFYING",
            "VERIFYING": "mọi task coder done → orc advance {id} --to DONE",
            "BLOCKED": "HỎI DUNG — Dung gõ orc:resume {id} rồi orc resume {id}"}
    return [f"K: {t['id']} [{t['status']}] → {hint[t['status']].format(id=t['id'])}"
            for t in tasks if is_root(t) and t.get("status") in hint]
