"""Phê duyệt của Dung (v0.2 N2; ADJUSTMENTS #4; H7 Phase 4).

- `request ID...`: orc tính binding cho từng ID, sinh nonce dùng một lần, in dòng Dung phải gõ
  `orc:approve ID1,ID2 NONCE`. Một lần duyệt có thể gồm nhiều ID (ADJUSTMENTS #2 "hỏi một lần").
  Binding: TASK = task + plan_hash + write_scope_hash + level + risk_flags (#4); DEC = nội dung DEC (summary, scope,
  supersedes, file); ART = nội dung thân.
- `approve ID...`: chỉ nhận khi hook UserPromptSubmit đã ghi đúng dòng đó **sau** lúc yêu cầu, nonce chưa dùng và
  mọi binding tính lại khớp. Khi đó DEC `proposed` → `accepted` (DEC cũ supersedes tự superseded), ART `draft` →
  `accepted`; TASK ghi approval. **Đây là đường duy nhất để một DEC/ART research thành accepted (H7).**
- `check TASK`: approval còn hiệu lực? Binding đổi ⇒ hết.
Giới hạn: process cùng user vẫn ghi thêm được dòng vào prompts.jsonl; chuỗi hash phát hiện sửa dòng cũ, không ngăn
thêm dòng mới (v0.2 N2). Nonce do orc in ra nên LLM cũng thấy: chống dùng lại/nhầm, không chống giả mạo.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
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
    items = oc.load_yaml_file(path(root)) or []
    for a in items:  # bản ghi Phase 3: {task, binding} ⇒ {ids, bindings}
        if "ids" not in a and a.get("task"):
            a["ids"] = [a["task"]]
            a["bindings"] = {a["task"]: a.get("binding")}
    return items


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


def _body(root: Path, id_: str) -> str:
    p = oc.content_path(root, id_)
    return oc.split_frontmatter(oc.read_text(p))[1] if p.exists() else "(mất)"


def binding(root: Path, id_: str) -> dict:
    kind = oc.kind_of(id_)
    _, _, e = oc.find_entry(root, id_)
    if kind == "task" and e.get("workflow") == "k":
        # Task gốc K (Phase 4b): plan accepted của task con + hợp write_scope + danh sách task coder
        import orc_k  # noqa: PLC0415
        plans = sorted(a["id"] for a in orc_k.child_arts(root, id_, "plan") if a.get("status") == "accepted")
        kids = orc_k.coders(root, id_)
        scope = sorted({str(s) for t in kids for s in oc.as_list(t.get("write_scope"))})
        return {"task": id_, "plans": plans,
                "plan_hash": _sha("\n\0".join(f"{i}\n{_body(root, i)}" for i in plans)),
                "write_scope_hash": _sha(json.dumps(scope)),
                "tasks": sorted(t["id"] for t in kids),
                "level": e.get("level"), "risk_flags": sorted(oc.as_list(e.get("risk_flags")))}
    if kind == "task":
        parts = [f"{i}\n{_body(root, i)}" for i in plan_ids(root, e)]
        return {"task": id_, "plans": plan_ids(root, e), "plan_hash": _sha("\n\0".join(parts)),
                "write_scope_hash": _sha(json.dumps(sorted(map(str, oc.as_list(e.get("write_scope")))))),
                "level": e.get("level"), "risk_flags": sorted(oc.as_list(e.get("risk_flags")))}
    if kind == "decision":
        return {"decision": id_, "summary": e.get("summary"), "scope": e.get("scope"),
                "supersedes": e.get("supersedes"), "file_hash": _sha(_body(root, id_))}
    if kind == "artifact":
        return {"artifact": id_, "type": e.get("type"), "task": e.get("task"), "body_hash": _sha(_body(root, id_))}
    raise oc.OrcError(f"{id_}: chỉ duyệt TASK, DEC hoặc ART")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="microseconds")


def _ids(ids) -> list:
    if isinstance(ids, str):
        ids = [ids]
    out = []
    for i in ids:
        out += [x for x in str(i).split(",") if x]
    # Agent hay chép cả nonce vào lệnh (`orc approve ART-1,DEC-2 5DA20D`): nonce không phải ID ⇒ bỏ qua.
    out = [x for x in out if oc.is_id(x) or not re.fullmatch(r"[0-9A-Fa-f]{6}", x)]
    if not out or len(set(out)) != len(out):
        raise oc.OrcError("cần danh sách ID không trùng")
    return out


def request(root: Path, ids) -> str:
    ids = _ids(ids)
    for i in ids:
        kind = oc.kind_of(i)
        status = oc.find_entry(root, i)[2].get("status")
        if kind == "decision" and status != "proposed":
            raise oc.OrcError(f"{i} đang {status}: chỉ duyệt DEC proposed")
        if kind == "artifact" and status != "draft":
            raise oc.OrcError(f"{i} đang {status}: chỉ duyệt ART draft")
    items = load(root)
    for a in items:
        if a.get("status") == "pending" and set(a.get("ids") or []) & set(ids):
            a["status"] = "expired"
    nonce = secrets.token_hex(3).upper()
    items.append({"ids": ids, "nonce": nonce, "status": "pending", "requested_at": _now(),
                  "bindings": {i: binding(root, i) for i in ids}})
    save(root, items)
    lines = [f"Dung gõ đúng dòng sau để duyệt:\n  orc:approve {','.join(ids)} {nonce}"]
    for i in ids:
        e = oc.find_entry(root, i)[2]
        lines.append(f"- {i}: {oc._short(e.get('title') or e.get('summary'), 100)}")
    return "\n".join(lines)


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


def approve(root: Path, ids) -> dict:
    ids = _ids(ids)
    items = load(root)
    pend = [a for a in items if a.get("status") == "pending" and a.get("ids") == ids]
    if not pend:
        raise oc.OrcError(f"{','.join(ids)}: chưa có yêu cầu duyệt đúng danh sách này; "
                          f"chạy `orc approval request {' '.join(ids)}`")
    req = pend[-1]
    want = f"orc:approve {','.join(ids)} {req['nonce']}".lower()
    hit = None
    for rec in prompt_lines(root):
        if rec.get("ts", "") <= req["requested_at"]:
            continue
        if any(" ".join(l.split()).lower() == want for l in rec.get("orc") or []):
            hit = rec
            break
    if hit is None:
        raise oc.OrcError(f"chưa thấy Dung gõ `orc:approve {','.join(ids)} {req['nonce']}` sau lúc yêu cầu "
                          f"({req['requested_at']})")
    changed = [f"{i}.{k}" for i in ids for k, v in binding(root, i).items() if v != req["bindings"][i].get(k)]
    if changed:
        req["status"] = "expired"
        save(root, items)
        raise oc.OrcError(f"{', '.join(changed)} đã đổi sau yêu cầu duyệt; tạo yêu cầu mới")
    req.update(status="used", approved_at=_now(), prompt_sha256=hit["sha256"], session=hit.get("session"))
    save(root, items)
    with oc.journal_context(extra={"event": "approve", "nonce": req["nonce"], "approved_ids": ids}):
        for i in ids:
            kind = oc.kind_of(i)
            if kind in ("decision", "artifact"):
                oc.set_fields(root, i, {"status": "accepted"})  # DEC: cascade supersedes trong set_fields
            else:
                st = oc.find_entry(root, i)[2].get("status")
                oc.append_journal(root, [{"id": i, "from": st, "to": st}])
    return req


def check(root: Path, tid: str) -> tuple:
    """(còn hiệu lực?, lý do) cho TASK."""
    used = [a for a in load(root) if a.get("status") == "used" and tid in (a.get("ids") or [])]
    if not used:
        return False, "chưa có approval"
    now = binding(root, tid)
    old = used[-1]["bindings"][tid]
    if now != old:
        changed = [k for k in now if now[k] != old.get(k)]
        return False, f"hết hiệu lực: {', '.join(changed)} đã đổi sau khi duyệt"
    return True, f"approval {used[-1]['nonce']} lúc {used[-1]['approved_at']}"


def shadow_log(root: Path, event: dict) -> None:
    p = oc.orc(root) / "runtime" / "shadow.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), **event}, ensure_ascii=False) + "\n")
