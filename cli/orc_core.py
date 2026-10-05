"""orc — CLI tất định của orchestra-kit.

Mọi logic của Orchestrator (A) không cần LLM nằm ở đây: cấp ID, ghi registry
(.orchestra/state/, chỉ orc ghi — D4), chọn task ready, kiểm blocked_by, định
tuyến kết quả review theo failure_class, kiểm tra hợp lệ, brief, handoff.

Chỉ dùng Python stdlib + PyYAML (D8). PyYAML được import muộn để hook có thể
no-op ở thư mục không có .orchestra/ ngay cả khi máy chưa cài PyYAML.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = KIT_DIR / "templates"
ORC_DIR = ".orchestra"

KINDS = ("task", "artifact", "decision", "context", "evidence")
PREFIX = {"task": "TASK", "artifact": "ART", "decision": "DEC",
          "context": "CTX", "evidence": "EVD", "session": "S"}
KIND_OF_PREFIX = {v: k for k, v in PREFIX.items()}
REGISTRY_FILE = {"task": "tasks", "artifact": "artifacts", "decision": "decisions",
                 "context": "contexts", "evidence": "evidence"}
# Thư mục chứa file nội dung (ngoài state/) của từng loại.
CONTENT_DIR = {"artifact": "artifacts", "decision": "decisions",
               "context": "contexts", "evidence": "evidence", "session": "sessions"}

ID_RE = re.compile(r"^(TASK|ART|DEC|CTX|EVD|S)-(\d{4,})$")
ACC_RE = re.compile(r"^(ART-\d{4,})#(AC-\d+)$")

TASK_STATUS = ("pending", "ready", "dispatched", "in_review", "done", "failed", "blocked")
OWNER_RE = re.compile(r"^(orchestrator|researcher|reviewer|coder(-\d+)?)$")
ART_TYPES = ("plan", "research", "code_patch", "review_report")
ART_STATUS = ("draft", "accepted", "rejected")
DEC_STATUS = ("proposed", "accepted", "superseded")
EVD_KINDS = ("test", "lint", "build", "manual", "other")
EVD_RESULTS = ("pass", "fail", "info")
CTX_SOURCES = ("manual", "graph", "fallback")
GRAPH_STATES = ("none", "fresh", "stale", "degraded", "locked", "unavailable")
CTX_MAX_FILES = 12
FAILURE_CLASSES = ("IMPL_BUG", "SPEC_GAP", "DECISION_CONFLICT", "REGRESSION")
ENV_STATUS = ("done", "partial", "blocked", "failed")
HANDOFF_RESULTS = ("done", "partial", "blocked")
HANDOFF_SECTIONS = ("Đã làm", "File thay đổi", "Quyết định phát sinh",
                    "Câu hỏi mở", "Bước tiếp theo")
PLACEHOLDER = "_(điền)_"
SUMMARY_MAX = 200
MAX_ATTEMPTS = 2          # attempts > 2 → hỏi người dùng
MAX_STOP_BLOCKS = 3       # chống vòng lặp vô hạn ở hook Stop
BRIEF_MAX_CHARS = 6000    # ~1.5k token

FIELDS = {
    "task": {
        "id": None, "title": "", "status": "pending", "owner": "coder",
        "blocked_by": [], "context": [], "inputs": [], "outputs": [],
        "acceptance": [], "write_scope": [], "attempts": 0, "summary": "",
        "failure_class": None, "needs_user": False, "resume_status": None,
    },
    "artifact": {
        "id": None, "type": "plan", "task": None, "version": 1, "supersedes": None,
        "status": "draft", "summary": "", "depends_on": [], "paths": [],
    },
    "decision": {"id": None, "status": "proposed", "scope": "project",
                 "summary": "", "supersedes": None},
    "context": {"id": None, "task": None, "summary": "", "paths": [],
                "source": "manual", "graph_state": "none", "fingerprint": None, "truncated": False},
    "evidence": {"id": None, "task": None, "kind": "test", "result": "info",
                 "summary": "", "paths": []},
}
LIST_FIELDS = {k: {f for f, d in v.items() if isinstance(d, list)} for k, v in FIELDS.items()}
SESSION_FIELDS = ("id", "task", "role", "result")


class OrcError(Exception):
    """Lỗi người dùng/agent cần thấy; CLI in ra và thoát mã 1."""


def _yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - phụ thuộc máy
        raise OrcError("Thiếu PyYAML. Cài: python -m pip install --user pyyaml") from exc
    return yaml


def today() -> str:
    return _dt.date.today().isoformat()


# ---------------------------------------------------------------- vị trí & IO

def find_root(start) -> Path | None:
    """Tìm thư mục dự án chứa .orchestra/config.yaml, đi ngược lên từ start."""
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / ORC_DIR / "config.yaml").is_file():
            return d
    return None


def require_root(start=".") -> Path:
    root = find_root(start)
    if root is None:
        raise OrcError("Không thấy .orchestra/ ở thư mục này hay thư mục cha. Chạy `orc init`.")
    return root


def orc(root: Path) -> Path:
    return root / ORC_DIR


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def dump_yaml(data) -> str:
    return _yaml().safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


def load_yaml_file(path: Path):
    return _yaml().safe_load(read_text(path)) if path.exists() else None


def load_config(root: Path) -> dict:
    return load_yaml_file(orc(root) / "config.yaml") or {}


def registry_path(root: Path, kind: str) -> Path:
    return orc(root) / "state" / f"{REGISTRY_FILE[kind]}.yaml"


def load_registry(root: Path, kind: str) -> list:
    data = load_yaml_file(registry_path(root, kind))
    if data is None:
        return []
    if not isinstance(data, list):
        raise OrcError(f"{registry_path(root, kind).name}: phải là danh sách YAML")
    return data


REGISTRY_HEADER = "# Registry do `orc` quản lý. Không sửa tay (D4: single writer).\n"


def save_registry(root: Path, kind: str, items: list) -> None:
    write_text(registry_path(root, kind), REGISTRY_HEADER + dump_yaml(items or []))


def split_frontmatter(text: str):
    """Trả về (dict frontmatter | None, body)."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines(keepends=True)
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = _yaml().safe_load("".join(lines[1:i])) or {}
            return fm, "".join(lines[i + 1:])
    return None, text


def join_frontmatter(fm: dict, body: str) -> str:
    return "---\n" + dump_yaml(fm) + "---\n" + body


# ---------------------------------------------------------------- ID

def kind_of(id_: str) -> str:
    m = ID_RE.match(str(id_))
    if not m:
        raise OrcError(f"ID không hợp lệ: {id_}")
    return KIND_OF_PREFIX[m.group(1)]


def is_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def content_path(root: Path, id_: str) -> Path:
    return orc(root) / CONTENT_DIR[kind_of(id_)] / f"{id_}.md"


def session_ids(root: Path) -> list:
    d = orc(root) / "sessions"
    return sorted(p.stem for p in d.glob("S-*.md")) if d.is_dir() else []


def next_id(root: Path, kind: str) -> str:
    prefix = PREFIX[kind]
    if kind == "session":
        existing = session_ids(root)
    else:
        existing = [str(e.get("id")) for e in load_registry(root, kind) if isinstance(e, dict)]
    nums = [int(m.group(2)) for m in map(ID_RE.match, existing) if m and m.group(1) == prefix]
    return f"{prefix}-{(max(nums) if nums else 0) + 1:04d}"


def find_entry(root: Path, id_: str):
    kind = kind_of(id_)
    if kind == "session":
        raise OrcError("Session không nằm trong registry; dùng file sessions/S-x.md")
    items = load_registry(root, kind)
    for e in items:
        if isinstance(e, dict) and e.get("id") == id_:
            return kind, items, e
    raise OrcError(f"Không có {id_}")


def exists(root: Path, id_: str) -> bool:
    try:
        if kind_of(id_) == "session":
            return content_path(root, id_).exists()
        find_entry(root, id_)
        return True
    except OrcError:
        return False


def as_list(value) -> list:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def check_summary(summary) -> None:
    if summary is not None and len(str(summary)) > SUMMARY_MAX:
        raise OrcError(f"summary dài {len(str(summary))} ký tự (> {SUMMARY_MAX})")


def render_template(name: str, **values) -> str:
    text = read_text(TEMPLATES / name)
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


# ---------------------------------------------------------------- init

def cmd_init(root: Path, project_id: str, goal: str) -> list:
    o = orc(root)
    if (o / "config.yaml").exists():
        raise OrcError(f"{o} đã có config.yaml; không ghi đè.")
    kit_version = read_text(KIT_DIR / "VERSION").strip()
    created = []
    for d in ("state", "decisions", "artifacts", "contexts", "evidence", "sessions", "knowledge"):
        (o / d).mkdir(parents=True, exist_ok=True)
    write_text(o / "config.yaml", dump_yaml({
        "project_id": project_id, "kit_version": kit_version, "goal": goal}))
    created.append(o / "config.yaml")
    for kind in KINDS:
        save_registry(root, kind, [])
        created.append(registry_path(root, kind))
    write_text(o / ".gitignore",
               "# Dấu phiên đang mở của hook và cache graph, không commit\nruntime/\ncache/\n")
    created.append(o / ".gitignore")
    km = o / "knowledge" / "KNOWLEDGE_MAP.md"
    if not km.exists():
        write_text(km, render_template("KNOWLEDGE_MAP.md", project_id=project_id, date=today()))
        created.append(km)
    for d in ("decisions", "artifacts", "contexts", "evidence", "sessions"):
        keep = o / d / ".gitkeep"
        if not keep.exists():
            write_text(keep, "")
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        write_text(claude_md, render_template("CLAUDE.md", project_id=project_id, goal=goal))
        created.append(claude_md)
    return created


# ---------------------------------------------------------------- new

def make_entry(entity: str, /, **values) -> dict:
    entry = {k: (list(v) if isinstance(v, list) else v) for k, v in FIELDS[entity].items()}
    for k, v in values.items():
        if v is None:
            continue
        if k not in entry:
            raise OrcError(f"{entity} không có trường '{k}'")
        entry[k] = as_list(v) if k in LIST_FIELDS[entity] else v
    check_summary(entry.get("summary"))
    return entry


def add_entry(root: Path, kind: str, entry: dict) -> dict:
    items = load_registry(root, kind)
    entry["id"] = next_id(root, kind)
    errs = entry_errors(root, kind, entry, extra_ids={entry["id"]})
    if errs:
        raise OrcError("; ".join(errs))
    items.append(entry)
    save_registry(root, kind, items)
    return entry


def new_task(root: Path, **values) -> dict:
    return add_entry(root, "task", make_entry("task", **values))


def new_artifact(root: Path, type_: str, task: str, summary: str = "",
                 supersedes: str | None = None, depends_on=None) -> dict:
    if type_ not in ART_TYPES:
        raise OrcError(f"type phải là một trong {ART_TYPES}")
    version = 1
    if supersedes:
        _, _, old = find_entry(root, supersedes)
        if old.get("type") != type_:
            raise OrcError(f"{supersedes} là {old.get('type')}, không phải {type_}")
        version = int(old.get("version") or 1) + 1
    entry = make_entry("artifact", type=type_, task=task, summary=summary,
                       supersedes=supersedes, depends_on=depends_on, version=version)
    entry = add_entry(root, "artifact", entry)
    rel = f"{ORC_DIR}/artifacts/{entry['id']}.md"
    entry["paths"] = [rel]
    _replace_entry(root, "artifact", entry)
    body = render_template(f"artifact-{type_}.md", id=entry["id"], task=task or "")
    write_text(content_path(root, entry["id"]), join_frontmatter(dict(entry), body))
    return entry


def new_decision(root: Path, summary: str, scope: str = "project",
                 supersedes: str | None = None, status: str = "proposed") -> dict:
    entry = add_entry(root, "decision", make_entry(
        "decision", summary=summary, scope=scope, supersedes=supersedes, status=status))
    write_text(content_path(root, entry["id"]),
               render_template("decision.md", id=entry["id"], summary=summary,
                               scope=scope, date=today()))
    if status == "accepted" and supersedes:
        set_fields(root, supersedes, {"status": "superseded"})
    return entry


def new_context(root: Path, task: str, summary: str, paths=None) -> dict:
    entry = add_entry(root, "context", make_entry("context", task=task, summary=summary,
                                                  paths=paths))
    write_text(content_path(root, entry["id"]),
               render_template("context.md", id=entry["id"], task=task or ""))
    return entry


def new_evidence(root: Path, task: str, summary: str, kind: str = "test",
                 result: str = "info", paths=None, with_file: bool = True) -> dict:
    entry = make_entry("evidence", task=task, summary=summary, kind=kind, result=result,
                       paths=paths)
    entry = add_entry(root, "evidence", entry)
    if with_file:
        rel = f"{ORC_DIR}/evidence/{entry['id']}.md"
        entry["paths"] = as_list(entry["paths"]) + [rel]
        _replace_entry(root, "evidence", entry)
        write_text(content_path(root, entry["id"]),
                   render_template("evidence.md", id=entry["id"], task=task or ""))
    return entry


def tasks_from_plan(root: Path, art_id: str) -> list:
    """Tạo task từ khối ```yaml orc-tasks trong plan đã accepted."""
    _, _, art = find_entry(root, art_id)
    if art.get("type") != "plan":
        raise OrcError(f"{art_id} không phải plan")
    if art.get("status") != "accepted":
        raise OrcError(f"{art_id} chưa accepted; Dung duyệt rồi `orc set {art_id} status=accepted`")
    _, body = split_frontmatter(read_text(content_path(root, art_id)))
    m = re.search(r"```ya?ml orc-tasks\s*\n(.*?)```", body, re.S)
    if not m:
        raise OrcError(f"{art_id} không có khối ```yaml orc-tasks")
    specs = _yaml().safe_load(m.group(1)) or []
    if not isinstance(specs, list):
        raise OrcError("orc-tasks phải là danh sách")
    local = {}
    created = []
    for spec in specs:
        if not isinstance(spec, dict) or "key" not in spec or "title" not in spec:
            raise OrcError("Mỗi task trong orc-tasks cần 'key' và 'title'")
        blocked = [local.get(b, b) for b in as_list(spec.get("blocked_by"))]
        acceptance = [a if "#" in str(a) else f"{art_id}#{a}" for a in as_list(spec.get("acceptance"))]
        entry = new_task(root, title=spec["title"], owner=spec.get("owner", "coder"),
                         summary=spec.get("summary", ""), blocked_by=blocked,
                         acceptance=acceptance, write_scope=spec.get("write_scope"),
                         inputs=[art_id] + as_list(spec.get("inputs")),
                         context=spec.get("context"))
        local[spec["key"]] = entry["id"]
        created.append(entry)
    return created


# ---------------------------------------------------------------- set

def _replace_entry(root: Path, kind: str, entry: dict) -> None:
    items = load_registry(root, kind)
    for i, e in enumerate(items):
        if isinstance(e, dict) and e.get("id") == entry["id"]:
            items[i] = entry
            save_registry(root, kind, items)
            return
    raise OrcError(f"Không có {entry['id']}")


def parse_assignments(pairs) -> dict:
    out = {}
    for pair in pairs:
        if "=" not in pair:
            raise OrcError(f"Cần dạng key=value: {pair}")
        k, v = pair.split("=", 1)
        out[k.strip()] = _yaml().safe_load(v) if v.strip() else None
    return out


def set_fields(root: Path, id_: str, changes: dict) -> dict:
    if "id" in changes:
        raise OrcError("Không đổi được id")
    kind = kind_of(id_)
    if kind == "session":
        path = content_path(root, id_)
        if not path.exists():
            raise OrcError(f"Không có {id_}")
        fm, body = split_frontmatter(read_text(path))
        fm = fm or {}
        for k, v in changes.items():
            if k not in SESSION_FIELDS and k != "request":
                raise OrcError(f"session không có trường '{k}'")
            fm[k] = v
        write_text(path, join_frontmatter(fm, body))
        return fm
    _, _, entry = find_entry(root, id_)
    for k, v in changes.items():
        if k not in FIELDS[kind]:
            raise OrcError(f"{kind} không có trường '{k}'")
        entry[k] = as_list(v) if k in LIST_FIELDS[kind] else v
    errs = entry_errors(root, kind, entry)
    if errs:
        raise OrcError("; ".join(errs))
    _replace_entry(root, kind, entry)
    if kind == "artifact":
        path = content_path(root, id_)
        if path.exists():
            fm, body = split_frontmatter(read_text(path))
            fm = fm or {}
            for k in FIELDS["artifact"]:
                fm[k] = entry[k]
            write_text(path, join_frontmatter(fm, body))
    if kind == "decision" and changes.get("status") == "accepted" and entry.get("supersedes"):
        set_fields(root, entry["supersedes"], {"status": "superseded"})
    return entry


# ---------------------------------------------------------------- validate

def entry_errors(root: Path, kind: str, e: dict, extra_ids=frozenset()) -> list:
    """Lỗi của một mục registry (schema + tham chiếu)."""
    errs = []
    eid = e.get("id")
    label = eid or f"<{kind}>"
    if not is_id(eid) or kind_of(eid) != kind:
        errs.append(f"{label}: id sai định dạng cho {kind}")
    missing = [f for f in FIELDS[kind] if f not in e]
    if missing:
        errs.append(f"{label}: thiếu trường {missing}")
    unknown = [f for f in e if f not in FIELDS[kind]]
    if unknown:
        errs.append(f"{label}: trường lạ {unknown}")
    if e.get("summary") is not None and len(str(e.get("summary"))) > SUMMARY_MAX:
        errs.append(f"{label}: summary > {SUMMARY_MAX} ký tự")
    for f in LIST_FIELDS[kind]:
        if f in e and not isinstance(e[f], list):
            errs.append(f"{label}: {f} phải là danh sách")

    def ref(value, field, want=None):
        if value in (None, ""):
            return
        if not is_id(value):
            errs.append(f"{label}: {field} = {value!r} không phải ID")
            return
        if want and kind_of(value) != want:
            errs.append(f"{label}: {field} = {value} phải là {want}")
            return
        if value not in extra_ids and not exists(root, value):
            errs.append(f"{label}: {field} tham chiếu {value} không tồn tại")

    if kind == "task":
        if e.get("status") not in TASK_STATUS:
            errs.append(f"{label}: status '{e.get('status')}' không hợp lệ")
        if not OWNER_RE.match(str(e.get("owner"))):
            errs.append(f"{label}: owner '{e.get('owner')}' không hợp lệ")
        if not str(e.get("title") or "").strip():
            errs.append(f"{label}: thiếu title")
        if e.get("failure_class") not in (None, *FAILURE_CLASSES):
            errs.append(f"{label}: failure_class '{e.get('failure_class')}' không hợp lệ")
        if not isinstance(e.get("attempts"), int) or e.get("attempts") < 0:
            errs.append(f"{label}: attempts phải là số nguyên ≥ 0")
        if e.get("resume_status") not in (None, *TASK_STATUS):
            errs.append(f"{label}: resume_status không hợp lệ")
        for b in as_list(e.get("blocked_by")):
            ref(b, "blocked_by", "task")
            if b == eid:
                errs.append(f"{label}: tự chặn chính nó")
        for c in as_list(e.get("context")):
            ref(c, "context", "context")
        for f in ("inputs", "outputs"):
            for v in as_list(e.get(f)):
                if is_id(v):
                    ref(v, f)
        for a in as_list(e.get("acceptance")):
            m = ACC_RE.match(str(a))
            if not m:
                errs.append(f"{label}: acceptance '{a}' phải dạng ART-x#AC-n")
                continue
            ref(m.group(1), "acceptance", "artifact")
            if exists(root, m.group(1)) and acceptance_text(root, str(a)) is None:
                errs.append(f"{label}: {a} không có trong {m.group(1)}")
    elif kind == "artifact":
        if e.get("type") not in ART_TYPES:
            errs.append(f"{label}: type '{e.get('type')}' không hợp lệ")
        if e.get("status") not in ART_STATUS:
            errs.append(f"{label}: status '{e.get('status')}' không hợp lệ")
        if not isinstance(e.get("version"), int) or e.get("version") < 1:
            errs.append(f"{label}: version phải là số nguyên ≥ 1")
        ref(e.get("task"), "task", "task")
        ref(e.get("supersedes"), "supersedes", "artifact")
        for d in as_list(e.get("depends_on")):
            ref(d, "depends_on")
    elif kind == "decision":
        if e.get("status") not in DEC_STATUS:
            errs.append(f"{label}: status '{e.get('status')}' không hợp lệ")
        ref(e.get("supersedes"), "supersedes", "decision")
        if not str(e.get("scope") or "").strip():
            errs.append(f"{label}: thiếu scope")
    elif kind == "context":
        ref(e.get("task"), "task", "task")
        if e.get("source") not in CTX_SOURCES:
            errs.append(f"{label}: source '{e.get('source')}' không hợp lệ")
        if e.get("graph_state") not in GRAPH_STATES:
            errs.append(f"{label}: graph_state '{e.get('graph_state')}' không hợp lệ")
        if not isinstance(e.get("truncated"), bool):
            errs.append(f"{label}: truncated phải là true/false")
        fp = e.get("fingerprint")
        if fp is not None and not (isinstance(fp, dict) and isinstance(fp.get("files"), dict)):
            errs.append(f"{label}: fingerprint phải có dạng {{graph, files}}")
    elif kind == "evidence":
        ref(e.get("task"), "task", "task")
        if e.get("kind") not in EVD_KINDS:
            errs.append(f"{label}: kind '{e.get('kind')}' không hợp lệ")
        if e.get("result") not in EVD_RESULTS:
            errs.append(f"{label}: result '{e.get('result')}' không hợp lệ")
    return errs


def acceptance_text(root: Path, ref: str):
    m = ACC_RE.match(ref)
    if not m:
        return None
    path = content_path(root, m.group(1))
    if not path.exists():
        return None
    _, body = split_frontmatter(read_text(path))
    pat = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?" + re.escape(m.group(2)) + r"\b.*$", re.M)
    hit = pat.search(body)
    return hit.group(0).strip() if hit else None


def session_errors(root: Path, path: Path, require_complete: bool) -> list:
    errs = []
    label = path.stem
    try:
        fm, body = split_frontmatter(read_text(path))
    except Exception as exc:  # YAML hỏng
        return [f"{label}: frontmatter lỗi YAML ({exc})"]
    if fm is None:
        return [f"{label}: thiếu frontmatter"]
    for f in SESSION_FIELDS:
        if f not in fm:
            errs.append(f"{label}: thiếu trường {f}")
    if fm.get("id") != label:
        errs.append(f"{label}: id trong frontmatter ({fm.get('id')}) khác tên file")
    task = fm.get("task")
    if task not in (None, "", "-"):
        if not is_id(task) or kind_of(task) != "task" or not exists(root, task):
            errs.append(f"{label}: task {task} không tồn tại")
    result = fm.get("result")
    allowed = HANDOFF_RESULTS if require_complete else (*HANDOFF_RESULTS, "pending")
    if result not in allowed:
        errs.append(f"{label}: result '{result}' phải là {'|'.join(allowed)}")
    if require_complete:
        for sec in HANDOFF_SECTIONS:
            content = section_body(body, sec)
            if content is None:
                errs.append(f"{label}: thiếu mục '## {sec}'")
            elif not content or content == PLACEHOLDER:
                errs.append(f"{label}: mục '{sec}' chưa điền (ghi 'Không có' nếu trống)")
    return errs


def section_body(body: str, title: str):
    m = re.search(r"^##\s+" + re.escape(title) + r"\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return m.group(1).strip() if m else None


def validate(root: Path) -> list:
    errs = []
    cfg = load_config(root)
    for f in ("project_id", "kit_version"):
        if not cfg.get(f):
            errs.append(f"config.yaml: thiếu {f}")
    for kind in KINDS:
        try:
            items = load_registry(root, kind)
        except Exception as exc:
            errs.append(f"{REGISTRY_FILE[kind]}.yaml: {exc}")
            continue
        seen = set()
        for e in items:
            if not isinstance(e, dict):
                errs.append(f"{REGISTRY_FILE[kind]}.yaml: mục không phải mapping: {e!r}")
                continue
            if e.get("id") in seen:
                errs.append(f"{e.get('id')}: ID trùng")
            seen.add(e.get("id"))
            errs.extend(entry_errors(root, kind, e))
            if kind in ("artifact", "decision") and is_id(e.get("id")):
                path = content_path(root, e["id"])
                if not path.exists():
                    errs.append(f"{e['id']}: thiếu file {path.relative_to(root).as_posix()}")
                elif kind == "artifact":
                    errs.extend(_artifact_file_errors(path, e))
        # File nội dung không có trong registry
        if kind in CONTENT_DIR:
            d = orc(root) / CONTENT_DIR[kind]
            for p in d.glob(f"{PREFIX[kind]}-*.md") if d.is_dir() else []:
                if p.stem not in seen:
                    errs.append(f"{p.stem}: có file nhưng không có trong registry")
    for p in (orc(root) / "sessions").glob("S-*.md"):
        errs.extend(session_errors(root, p, require_complete=False))
    return errs


def _artifact_file_errors(path: Path, entry: dict) -> list:
    try:
        fm, _ = split_frontmatter(read_text(path))
    except Exception as exc:
        return [f"{entry['id']}: frontmatter lỗi YAML ({exc})"]
    if fm is None:
        return [f"{entry['id']}: file thiếu frontmatter"]
    errs = []
    for k in FIELDS["artifact"]:
        if k not in fm:
            errs.append(f"{entry['id']}: frontmatter thiếu {k}")
        elif fm[k] != entry.get(k):
            errs.append(f"{entry['id']}: frontmatter {k}={fm[k]!r} khác registry {entry.get(k)!r}")
    return errs


# ---------------------------------------------------------------- phiên & handoff

def marker_path(root: Path, key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    return orc(root) / "runtime" / "sessions" / f"{safe}.yaml"


def handoff_open(root: Path, role: str, task: str | None = None, key: str | None = None,
                 request: str = "") -> str:
    if task not in (None, "", "-") and not exists(root, task):
        raise OrcError(f"Không có {task}")
    if key:
        m = load_yaml_file(marker_path(root, key))
        if m and not m.get("closed"):
            raise OrcError(f"Phiên này đã mở {m.get('sid')}; mỗi phiên chỉ 1 yêu cầu (D5)")
    sid = next_id(root, "session")
    fm = {"id": sid, "task": task if task not in (None, "", "-") else None, "role": role,
          "result": "pending", "request": request, "date": today()}
    body = render_template("session.md", placeholder=PLACEHOLDER)
    write_text(content_path(root, sid), join_frontmatter(fm, body))
    if key:
        write_text(marker_path(root, key), dump_yaml(
            {"sid": sid, "opened": _dt.datetime.now().isoformat(timespec="seconds"),
             "blocks": 0, "closed": False}))
    return sid


def open_marker(root: Path, key: str | None):
    if not key:
        return None
    m = load_yaml_file(marker_path(root, key))
    return m if m and not m.get("closed") else None


def handoff_errors(root: Path, sid: str) -> list:
    path = content_path(root, sid)
    if not path.exists():
        return [f"{sid}: chưa có file handoff {path.relative_to(root).as_posix()}"]
    return session_errors(root, path, require_complete=True)


def close_marker(root: Path, key: str, how: str = "handoff") -> None:
    path = marker_path(root, key)
    m = load_yaml_file(path) or {}
    m.update({"closed": True, "closed_by": how,
              "closed_at": _dt.datetime.now().isoformat(timespec="seconds")})
    write_text(path, dump_yaml(m))


def stop_check(root: Path, key: str | None) -> dict | None:
    """Logic hook Stop. Trả về JSON chặn, hoặc None nếu cho dừng."""
    m = open_marker(root, key)
    if not m:
        return None  # phiên chưa mở task/S-ID → không chặn (Dung chốt Q4)
    errs = handoff_errors(root, m["sid"]) + validate(root)
    if not errs:
        close_marker(root, key)
        return None
    if int(m.get("blocks", 0)) >= MAX_STOP_BLOCKS:
        close_marker(root, key, how="gave_up")
        return None
    m["blocks"] = int(m.get("blocks", 0)) + 1
    write_text(marker_path(root, key), dump_yaml(m))
    rel = content_path(root, m["sid"]).relative_to(root).as_posix()
    reason = (f"[orchestra] Chưa thể kết thúc: handoff {m['sid']} ({rel}) chưa hợp lệ "
              f"(lần chặn {m['blocks']}/{MAX_STOP_BLOCKS}). Điền đủ 5 mục, đặt result "
              f"done|partial|blocked, rồi chạy `orc validate --handoff`.\n- "
              + "\n- ".join(errs[:15]))
    return {"decision": "block", "reason": reason}


# ---------------------------------------------------------------- next & route

def promote(root: Path) -> list:
    """pending/blocked có blocked_by đã done hết → ready (hoặc resume_status)."""
    items = load_registry(root, "task")
    status = {t["id"]: t.get("status") for t in items}
    changed = []
    for t in items:
        blockers = as_list(t.get("blocked_by"))
        clear = all(status.get(b) == "done" for b in blockers)
        if t["status"] == "pending" and clear:
            t["status"] = "ready"
            changed.append(t["id"])
        elif t["status"] == "blocked" and blockers and clear and not t.get("needs_user"):
            t["status"] = t.get("resume_status") or "ready"
            t["resume_status"] = None
            changed.append(t["id"])
    if changed:
        save_registry(root, "task", items)
    return changed


def agent_for(owner: str) -> str:
    return "coder" if str(owner).startswith("coder") else str(owner)


def next_report(root: Path) -> str:
    promoted = promote(root)
    tasks = load_registry(root, "task")
    lines = []
    if promoted:
        lines.append("Đã chuyển sang ready/resume: " + ", ".join(promoted))
    ask = [t for t in tasks if t.get("needs_user")]
    for t in ask:
        lines.append(f"HỎI DUNG: {t['id']} [{t['status']}] {t.get('failure_class') or ''} — {t['title']}")
    review = [t for t in tasks if t["status"] == "in_review"]
    for t in review:
        lines.append(f"REVIEW: {t['id']} → /review {t['id']} (agent reviewer)")
    ready = [t for t in tasks if t["status"] == "ready"]
    for t in ready:
        lines.append(f"READY: {t['id']} owner={t['owner']} → agent {agent_for(t['owner'])} — {t['title']}")
    if ready:
        lines.append(f"NEXT: {ready[0]['id']}")
    elif not review and not ask:
        lines.append("NEXT: (không có task ready)")
    return "\n".join(lines)


ENVELOPE_KEYS = {"msg", "task_id", "status", "outputs", "evidence",
                 "proposed_decisions", "summary", "failure_class"}


def parse_envelope(text: str) -> dict:
    text = text.strip()
    fence = re.match(r"^```(?:ya?ml)?\s*\n(.*?)\n```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        env = _yaml().safe_load(text)
    except Exception as exc:
        raise OrcError(f"Envelope không phải YAML hợp lệ: {exc}") from exc
    if not isinstance(env, dict):
        raise OrcError("Envelope phải là mapping YAML (không văn xuôi)")
    extra = set(env) - ENVELOPE_KEYS
    if extra:
        raise OrcError(f"Envelope có khoá lạ: {sorted(extra)}")
    if env.get("msg") != "result":
        raise OrcError("Envelope cần msg: result")
    for k in ("task_id", "status", "summary"):
        if not env.get(k):
            raise OrcError(f"Envelope thiếu {k}")
    if env["status"] not in ENV_STATUS:
        raise OrcError(f"status phải là {'|'.join(ENV_STATUS)}")
    for k in ("outputs", "evidence", "proposed_decisions"):
        env[k] = as_list(env.get(k))
    check_summary(env["summary"])
    if env.get("failure_class") not in (None, *FAILURE_CLASSES):
        raise OrcError(f"failure_class phải là {'|'.join(FAILURE_CLASSES)}")
    return env


def _in_scope(path: str, scope: list) -> bool:
    p = path.replace("\\", "/").lstrip("./")
    for s in scope:
        s = str(s).replace("\\", "/").lstrip("./")
        if fnmatch.fnmatch(p, s) or p == s.rstrip("/") or p.startswith(s.rstrip("/") + "/"):
            return True
    return False


def apply_envelope(root: Path, env: dict) -> str:
    """Ghi kết quả subagent vào state và định tuyến tất định. Trả về dòng ROUTE."""
    _, _, task = find_entry(root, env["task_id"])
    tid = task["id"]
    phase = task["status"]
    if phase not in ("dispatched", "in_review"):
        raise OrcError(f"{tid} đang {phase}; chỉ nhận envelope khi dispatched hoặc in_review")
    reviewing = phase == "in_review"
    if env.get("failure_class") and not reviewing:
        raise OrcError("failure_class chỉ dành cho kết quả review")
    if reviewing and env["status"] != "done" and not env.get("failure_class"):
        raise OrcError("Review không đạt phải có failure_class")

    # Kiểm tra trước khi ghi bất cứ thứ gì
    outputs = []
    for o in env["outputs"]:
        o = str(o)
        if is_id(o):
            if not exists(root, o):
                raise OrcError(f"outputs: {o} không tồn tại")
        elif (not reviewing and agent_for(task["owner"]) == "coder"
              and not _in_scope(o, as_list(task.get("write_scope")))):
            raise OrcError(f"outputs: {o} nằm ngoài write_scope {task.get('write_scope')}")
        outputs.append(o)
    for ev in env["evidence"]:
        if isinstance(ev, str):
            if not (is_id(ev) and kind_of(ev) == "evidence" and exists(root, ev)):
                raise OrcError(f"evidence: {ev} không tồn tại")
        elif isinstance(ev, dict):
            unknown = set(ev) - {"kind", "result", "summary", "paths"}
            if unknown or not ev.get("summary"):
                raise OrcError("evidence mới cần summary; chỉ có kind/result/summary/paths")
            check_summary(ev["summary"])
        else:
            raise OrcError("evidence phải là EVD-ID hoặc mapping")
    for d in env["proposed_decisions"]:
        if isinstance(d, dict):
            if not d.get("summary"):
                raise OrcError("proposed_decisions cần summary")
            check_summary(d["summary"])
        elif not isinstance(d, str):
            raise OrcError("proposed_decisions phải là chuỗi hoặc mapping")

    # Ghi
    evd_ids = []
    for ev in env["evidence"]:
        if isinstance(ev, str):
            evd_ids.append(ev)
        else:
            e = new_evidence(root, tid, ev["summary"], kind=ev.get("kind", "test"),
                             result=ev.get("result", "info"), paths=ev.get("paths"),
                             with_file=False)
            evd_ids.append(e["id"])
    dec_ids = []
    for d in env["proposed_decisions"]:
        if isinstance(d, str):
            d = {"summary": d}
        dec_ids.append(new_decision(root, d["summary"], scope=d.get("scope", tid),
                                    supersedes=d.get("supersedes"))["id"])

    _, _, task = find_entry(root, tid)
    for o in outputs + evd_ids:
        if o not in task["outputs"]:
            task["outputs"].append(o)
    task["summary"] = env["summary"]
    status, fc = env["status"], env.get("failure_class")
    route = ""
    if not reviewing:
        if status == "done":
            if agent_for(task["owner"]) == "coder":
                task["status"], route = "in_review", f"/review {tid}"
            else:
                task["status"], route = "done", "orc next"
        elif status == "partial":
            task["status"], route = "ready", f"chạy lại {tid} (partial)"
        elif status == "blocked":
            task.update(status="blocked", needs_user=True)
            route = f"HỎI DUNG: {tid} bị chặn"
        else:
            task.update(status="failed", needs_user=True)
            route = f"HỎI DUNG: {tid} thất bại"
    elif status == "done" and not fc:
        task.update(status="done", failure_class=None)
        route = "orc next"
    else:
        task["failure_class"] = fc
        if fc == "IMPL_BUG":
            task["attempts"] = int(task.get("attempts") or 0) + 1
            if task["attempts"] > MAX_ATTEMPTS:
                task.update(status="blocked", needs_user=True)
                route = f"HỎI DUNG: {tid} đã thử {task['attempts']} lần"
            else:
                task["status"] = "ready"
                route = f"trả {tid} về coder (attempt {task['attempts']})"
        elif fc == "SPEC_GAP":
            plans = [a.split("#")[0] for a in task["acceptance"]]
            fix = new_task(root, title=f"Lập lại plan cho {tid}", owner="researcher",
                           inputs=[tid] + sorted(set(plans)),
                           summary=f"SPEC_GAP từ review {tid}; plan mới phải supersedes plan cũ")
            task.update(status="blocked", resume_status="ready",
                        blocked_by=task["blocked_by"] + [fix["id"]])
            route = f"{fix['id']} → researcher replan (supersedes)"
        elif fc == "DECISION_CONFLICT":
            task.update(status="blocked", needs_user=True)
            route = f"HỎI DUNG: {tid} xung đột quyết định"
        elif fc == "REGRESSION":
            fix = new_task(root, title=f"Sửa regression của {tid}", owner="coder",
                           write_scope=task["write_scope"], inputs=[tid],
                           acceptance=task["acceptance"],
                           summary=f"REGRESSION phát hiện khi review {tid}; chặn merge")
            task.update(status="blocked", resume_status="in_review",
                        blocked_by=task["blocked_by"] + [fix["id"]])
            route = f"CHẶN MERGE {tid}; {fix['id']} → coder"
    _replace_entry(root, "task", task)
    extra = []
    if evd_ids:
        extra.append("evidence " + ",".join(evd_ids))
    if dec_ids:
        extra.append("quyết định chờ duyệt " + ",".join(dec_ids))
    return f"ROUTE: {tid} → {task['status']}; {route}" + (f" ({'; '.join(extra)})" if extra else "")


# ---------------------------------------------------------------- show & brief

def show(root: Path, id_: str, meta: bool = False, pack: bool = False) -> str:
    kind = kind_of(id_)
    if kind == "session":
        path = content_path(root, id_)
        if not path.exists():
            raise OrcError(f"Không có {id_}")
        fm, body = split_frontmatter(read_text(path))
        return dump_yaml(fm) if meta else read_text(path)
    _, _, e = find_entry(root, id_)
    if pack:
        if kind != "task":
            raise OrcError("--pack chỉ dành cho TASK")
        # Gói cho reviewer: acceptance + outputs + evidence, không có summary của coder.
        lines = [f"task: {e['id']}", f"title: {e['title']}", "acceptance:"]
        for a in e["acceptance"]:
            lines.append(f"  - {a}: {acceptance_text(root, a) or '(không tìm thấy)'}")
        lines.append("write_scope: " + json.dumps(e["write_scope"], ensure_ascii=False))
        lines.append("outputs:")
        for o in e["outputs"]:
            if is_id(o) and kind_of(o) == "evidence":
                continue
            lines.append(f"  - {o}")
        lines.append("evidence:")
        for o in e["outputs"]:
            if is_id(o) and kind_of(o) == "evidence":
                _, _, ev = find_entry(root, o)
                lines.append(f"  - {o}: kind={ev['kind']} result={ev['result']} paths={ev['paths']}")
        return "\n".join(lines) + "\n"
    out = dump_yaml(e)
    if meta:
        return out
    if kind == "task":
        acc = [f"- {a}: {acceptance_text(root, a) or '(không tìm thấy)'}" for a in e["acceptance"]]
        return out + ("\n# acceptance\n" + "\n".join(acc) + "\n" if acc else "")
    path = content_path(root, id_)
    return out + ("\n" + read_text(path) if path.exists() else "")


def _short(text, n=120) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def latest_handoff(root: Path):
    best = None
    for sid in session_ids(root):
        fm, body = split_frontmatter(read_text(content_path(root, sid)))
        if fm and fm.get("result") in HANDOFF_RESULTS:
            best = (sid, fm, body)
    return best


def brief_text(root: Path, key: str | None = None, max_chars: int = BRIEF_MAX_CHARS) -> str:
    cfg = load_config(root)
    tasks = load_registry(root, "task")
    decisions = load_registry(root, "decision")
    out = [f"# Orchestra brief — {cfg.get('project_id')} (kit {cfg.get('kit_version')})",
           f"Mục tiêu: {_short(cfg.get('goal'), 300)}"]
    m = open_marker(root, key)
    if m:
        out.append(f"Phiên này đang mở {m['sid']} (handoff bắt buộc trước khi dừng).")
    elif key:
        out.append(f"Mở phiên khi nhận yêu cầu có tạo/làm task: "
                   f"`orc handoff open --key {key} --role orchestrator --task <TASK-x|-> "
                   f"--request \"...\"`")
    ask = [t for t in tasks if t.get("needs_user")]
    if ask:
        out.append("\n## Cần Dung quyết")
        out += [f"- {t['id']} [{t['status']}] {t.get('failure_class') or ''} {_short(t['title'], 80)}"
                for t in ask]
    open_tasks = [t for t in tasks if t.get("status") != "done"]
    out.append(f"\n## Task mở ({len(open_tasks)})")
    out += [f"- {t['id']} [{t['status']}] {t['owner']}: {_short(t['title'], 70)}"
            + (f" — {_short(t.get('summary'), 100)}" if t.get("summary") else "")
            for t in open_tasks[:12]] or ["- (không có)"]
    ready = [t["id"] for t in open_tasks if t["status"] == "ready"]
    out.append("Ready: " + (", ".join(ready) if ready else "(không có)"))
    h = latest_handoff(root)
    if h:
        sid, fm, body = h
        out.append(f"\n## Handoff gần nhất: {sid} (task {fm.get('task')}, {fm.get('role')}, "
                   f"{fm.get('result')})")
        for sec in ("Bước tiếp theo", "Câu hỏi mở", "Quyết định phát sinh"):
            text = section_body(body, sec)
            if text:
                out.append(f"{sec}: {_short(text, 400)}")
    accepted = [d for d in decisions if d.get("status") == "accepted"]
    proposed = [d for d in decisions if d.get("status") == "proposed"]
    if accepted:
        out.append("\n## Quyết định đang hiệu lực")
        out += [f"- {d['id']} ({d['scope']}): {_short(d['summary'], 160)}" for d in accepted[-12:]]
    if proposed:
        out.append("\n## Quyết định chờ Dung duyệt")
        out += [f"- {d['id']} ({d['scope']}): {_short(d['summary'], 160)}" for d in proposed[-8:]]
    graph_line = graph_brief_line(root)
    if graph_line:
        out.append(graph_line)
    out.append("\nLệnh: `orc next`, `orc show <ID> --meta`, /plan /run /review /next /handoff")
    text = "\n".join(out)
    if len(text) > max_chars:
        text = text[: max_chars - 40].rstrip() + "\n… (brief bị cắt)"
    return text


# ---------------------------------------------------------------- gate & report

ASK_SECTION = "Cần Dung quyết"
NOTHING_TO_ASK = {"không có", "không", "none", "-"}


def plan_tasks_block(body: str):
    m = re.search(r"```ya?ml orc-tasks\s*\n(.*?)```", body, re.S)
    if not m:
        return None
    try:
        specs = _yaml().safe_load(m.group(1)) or []
    except Exception:
        return None
    return specs if isinstance(specs, list) else None


def gate(root: Path, art_id: str) -> list:
    """Plan có tự chạy tiếp được không. Trả danh sách lý do phải hỏi Dung (rỗng = đi tiếp)."""
    _, _, art = find_entry(root, art_id)
    if art.get("type") != "plan":
        raise OrcError(f"{art_id} không phải plan")
    _, body = split_frontmatter(read_text(content_path(root, art_id)))
    reasons = []
    asks = section_body(body, ASK_SECTION)
    if asks is None:
        reasons.append(f"plan thiếu mục '## {ASK_SECTION}'")
    else:
        lines = [l.strip() for l in re.sub(r"<!--.*?-->", "", asks, flags=re.S).splitlines()]
        lines = [l for l in lines if l and l.lstrip("-* ").strip().lower().rstrip(".") not in NOTHING_TO_ASK]
        reasons += [f"plan hỏi: {l.lstrip('-* ').strip()}" for l in lines]
    specs = plan_tasks_block(body)
    if not specs:
        reasons.append("plan không có khối orc-tasks hợp lệ")
    elif any(not isinstance(t, dict) or str(t.get("title", "")).strip() in ("", "...")
             for t in specs):
        reasons.append("plan còn task mẫu chưa điền (title '...')")
    if re.search(r"^\s*-\s*AC-1:\s*\.\.\.\s*$", body, re.M):
        reasons.append("plan còn tiêu chí mẫu chưa điền (AC-1: ...)")
    if not re.search(r"^\s*[-*]?\s*(?:\*\*)?AC-\d+\b", body, re.M):
        reasons.append("plan không có tiêu chí chấp nhận AC-n")
    scopes = {art_id, art.get("task")}
    for d in load_registry(root, "decision"):
        if d.get("status") == "proposed" and d.get("scope") in scopes:
            reasons.append(f"quyết định chờ duyệt {d['id']}: {_short(d['summary'], 160)}")
    return reasons


UNDERSTANDING_SECTIONS = ("Tôi hiểu yêu cầu là", "Thiết kế sơ bộ",
                          "Chưa rõ / thiếu thông tin", "Câu hỏi cho Dung")


def ask_text(root: Path, art_id: str) -> str:
    """Trích nguyên văn phần hiểu yêu cầu + câu hỏi của artifact research để chuyển cho Dung."""
    _, _, art = find_entry(root, art_id)
    if art.get("type") != "research":
        raise OrcError(f"{art_id} không phải research")
    _, body = split_frontmatter(read_text(content_path(root, art_id)))
    out, errs = [f"# {art_id}: {art.get('summary') or 'Hiểu yêu cầu & thiết kế'}"], []
    for sec in UNDERSTANDING_SECTIONS:
        text = section_body(body, sec)
        text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S).strip() if text is not None else None
        if text is None:
            errs.append(f"thiếu mục '## {sec}'")
        elif not text or text == PLACEHOLDER:
            errs.append(f"mục '{sec}' chưa điền")
        else:
            out += ["", f"## {sec}", text]
    if errs:
        raise OrcError(f"{art_id}: " + "; ".join(errs))
    return "\n".join(out) + "\n"


def report(root: Path, task_id: str) -> str:
    """Báo cáo tất định cho một yêu cầu: task gốc, plan, task con, review, evidence, quyết định."""
    _, _, root_task = find_entry(root, task_id)
    arts = load_registry(root, "artifact")
    tasks = load_registry(root, "task")
    evidence = {e["id"]: e for e in load_registry(root, "evidence")}
    plans = [a for a in arts if a.get("type") == "plan" and a.get("task") == task_id]
    plan_ids = {a["id"] for a in plans}
    kids = [t for t in tasks if plan_ids & set(as_list(t.get("inputs"))) and t["id"] != task_id]
    # task sinh ra khi định tuyến (replan, sửa regression) trỏ inputs tới task con
    kid_ids = {t["id"] for t in kids}
    kids += [t for t in tasks if t["id"] not in kid_ids and kid_ids & set(as_list(t.get("inputs")))]
    out = [f"# Báo cáo {task_id}: {root_task['title']}", ""]
    for a in plans:
        out.append(f"- Plan {a['id']} v{a['version']} [{a['status']}]: {a['summary']}")
    out += ["", "## Task", "| Task | Trạng thái | Lần | Kết quả |", "|---|---|---|---|"]
    for t in kids:
        flag = f" ⚠ {t['failure_class']}" if t.get("failure_class") else ""
        ask = " **cần Dung**" if t.get("needs_user") else ""
        out.append(f"| {t['id']} {_short(t['title'], 60)} | {t['status']}{flag}{ask} | "
                   f"{t.get('attempts', 0)} | {_short(t.get('summary'), 140)} |")
    out += ["", "## Bằng chứng"]
    for t in kids:
        evs = [evidence[o] for o in as_list(t.get("outputs")) if o in evidence]
        if evs:
            res = ", ".join(f"{e['kind']}:{e['result']}" for e in evs)
            out.append(f"- {t['id']}: {res}")
        reviews = [a for a in arts if a.get("task") == t["id"] and a.get("type") == "review_report"]
        for r in reviews:
            out.append(f"  - review {r['id']} [{r['status']}] `{(r.get('paths') or [''])[0]}`")
        files = [o for o in as_list(t.get("outputs")) if not is_id(o)]
        if files:
            out.append("  - file: " + ", ".join(f"`{f}`" for f in files))
    scopes = {task_id} | plan_ids | {t["id"] for t in kids}
    decs = [d for d in load_registry(root, "decision") if d.get("scope") in scopes]
    if decs:
        out += ["", "## Quyết định"]
        out += [f"- {d['id']} [{d['status']}]: {d['summary']}" for d in decs]
    ask = [t for t in kids if t.get("needs_user")]
    open_ = [t for t in kids if t["status"] != "done"]
    out += ["", "## Kết luận",
            ("Xong toàn bộ task." if not open_ else
             f"Còn {len(open_)} task chưa xong: " + ", ".join(f"{t['id']}[{t['status']}]" for t in open_))]
    if ask:
        out.append("Cần Dung quyết: " + ", ".join(t["id"] for t in ask))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- graph & context

def graph_adapter(root: Path):
    """Adapter theo mục `graph:` của config.yaml. Import muộn, không phụ thuộc engine (D8)."""
    from graph_adapter import GraphAdapter  # noqa: PLC0415 - cùng thư mục cli/
    return GraphAdapter(root, load_config(root).get("graph"))


def graph_brief_line(root: Path) -> str:
    """Một dòng trạng thái graph cho brief. Không bao giờ làm hỏng brief."""
    try:
        if not load_config(root).get("graph"):
            return ""
        st = graph_adapter(root).status()
    except Exception as exc:  # graph chỉ là accelerator
        return f"Graph: lỗi đọc trạng thái ({_short(exc, 80)}) — dùng fallback"
    extra = ""
    if st["state"] == "stale":
        extra = f", {len(st['changed'])} file đổi → `orc graph update`"
    elif st["problems"]:
        extra = f" — {_short(st['problems'][0], 100)}"
    return f"Graph: {st['state']} ({st['files']} file, {st['nodes']} node){extra}"


def _ctx_block(root: Path, ctx_id: str) -> dict:
    _, body = split_frontmatter(read_text(content_path(root, ctx_id)))
    m = re.search(r"```ya?ml orc-context\s*\n(.*?)```", body, re.S)
    if not m:
        raise OrcError(f"{ctx_id}: thiếu khối ```yaml orc-context")
    data = _yaml().safe_load(m.group(1)) or {}
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise OrcError(f"{ctx_id}: orc-context cần 'files' là danh sách")
    return data


def ctx_seal(root: Path, ctx_id: str) -> dict:
    """Đăng ký metadata CTX do Context Builder viết: nguồn, trạng thái graph, hash từng file (D4)."""
    if kind_of(ctx_id) != "context":
        raise OrcError(f"{ctx_id} không phải CTX")
    data = _ctx_block(root, ctx_id)
    source = data.get("source")
    if source not in ("graph", "fallback"):
        raise OrcError(f"{ctx_id}: source phải là graph|fallback")
    budget = int((load_config(root).get("graph") or {}).get("max_files", CTX_MAX_FILES))
    files, hashes = [], {}
    for item in data["files"]:
        if not isinstance(item, dict) or not item.get("path") or not item.get("reason"):
            raise OrcError(f"{ctx_id}: mỗi file cần path và reason")
        rel = str(item["path"]).replace("\\", "/")
        full = root / rel
        if not full.is_file():
            raise OrcError(f"{ctx_id}: không có file {rel}")
        files.append(rel)
        hashes[rel] = hashlib.md5(full.read_bytes()).hexdigest()
    if not files:
        raise OrcError(f"{ctx_id}: chưa chọn file nào")
    if len(files) > budget:
        raise OrcError(f"{ctx_id}: {len(files)} file vượt budget {budget}")
    graph_state, graph_fp = "none", None
    try:
        if load_config(root).get("graph"):
            st = graph_adapter(root).status()
            graph_state, graph_fp = st["state"], st["fingerprint"]
    except Exception:  # noqa: BLE001 - graph lỗi không chặn CTX
        graph_state = "unavailable"
    if source == "graph" and graph_state != "fresh":
        raise OrcError(f"{ctx_id}: source=graph nhưng graph đang {graph_state}; "
                       "cập nhật graph hoặc ghi source: fallback")
    return set_fields(root, ctx_id, {
        "source": source, "graph_state": graph_state, "paths": files,
        "truncated": bool(data.get("truncated", False)),
        "fingerprint": {"graph": graph_fp, "files": hashes}})


def ctx_check(root: Path, ctx_id: str) -> list:
    """File nào trong CTX đã đổi/mất kể từ lúc seal (chống dùng context cũ — F5)."""
    _, _, e = find_entry(root, ctx_id)
    fp = e.get("fingerprint") or {}
    if not fp.get("files"):
        raise OrcError(f"{ctx_id} chưa seal (`orc ctx seal {ctx_id}`)")
    changed = []
    for rel, digest in fp["files"].items():
        full = root / rel
        if not full.is_file():
            changed.append(f"{rel} (mất)")
        elif hashlib.md5(full.read_bytes()).hexdigest() != digest:
            changed.append(f"{rel} (đổi)")
    return changed


def _graph_cmd(root: Path, a) -> int:
    from graph_adapter import GraphError  # noqa: PLC0415
    ad = graph_adapter(root)
    try:
        if a.action == "status":
            res = ad.status()
        elif a.action == "update":
            res = ad.update(force=a.force)
        elif a.action == "query":
            res = ad.query(a.args, limit=a.limit)
        elif a.action == "affected":
            res = ad.affected(" ".join(a.args), depth=a.depth, limit=a.limit)
        elif a.action == "explain":
            res = ad.explain(" ".join(a.args), limit=a.limit)
        elif a.action == "view":
            res = ad.view()
            if a.open and res["pages"] and hasattr(os, "startfile"):
                os.startfile(res["pages"][0])  # noqa: S606 - mở file HTML cục bộ
        else:
            if len(a.args) != 2:
                raise OrcError("orc graph path A B")
            res = ad.path(a.args[0], a.args[1])
    except GraphError as exc:
        print(dump_yaml({"state": "unavailable", "authoritative": False, "error": str(exc),
                         "hint": "Dùng fallback; graph không bắt buộc."}))
        return 4
    print(dump_yaml(res), end="")
    return 0


# ---------------------------------------------------------------- docs (INDEX.md)

DOC_FIELDS = ("status", "feature", "updated", "summary", "read_when", "supersedes")
DOC_STATUS = ("current", "open", "implemented", "superseded", "archived")
DOC_SCAN_EXT = {".md", ".ts", ".tsx", ".js", ".jsx", ".cjs", ".mjs", ".py", ".sql", ".yaml", ".yml"}
DOC_SKIP_DIRS = {"node_modules", "dist", "build", "release", "out", ".git", "__pycache__",
                 "build-tmp", "build-temp", ".venv"}
DOC_REF_RE = re.compile(r"(?<![\w/.-])(docs/[\w./-]+?\.md)\b")
INDEX_START, INDEX_END = "<!-- orc:docs:start -->", "<!-- orc:docs:end -->"


def docs_root(start) -> Path:
    """Gốc dự án cho lệnh docs: có .orchestra, hoặc thư mục gần nhất chứa docs/ hay .git."""
    root = find_root(start)
    if root:
        return root
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / "docs").is_dir() or (d / ".git").exists():
            return d
    raise OrcError("Không thấy thư mục dự án (cần docs/ hoặc .git)")


def docs_files(root: Path) -> list:
    d = root / "docs"
    return sorted(p for p in d.rglob("*.md") if p.name != "INDEX.md") if d.is_dir() else []


def doc_meta(path: Path):
    try:
        fm, _ = split_frontmatter(read_text(path))
    except Exception as exc:  # YAML hỏng
        return None, f"frontmatter lỗi YAML ({exc})"
    return fm, None


def _walk_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            if d in DOC_SKIP_DIRS or (d.startswith(".") and d not in (".orchestra", ".claude")):
                continue
            if d == "cache" and Path(dirpath).name == ".orchestra":
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in DOC_SCAN_EXT:
                yield p


def docs_check(root: Path) -> tuple:
    """Trả (lỗi, cảnh báo). Lỗi: frontmatter sai/thiếu, không có trong INDEX, đường dẫn docs/ gãy
    ở file không lưu trữ. Đường dẫn gãy bên trong tài liệu archived chỉ là cảnh báo (lịch sử)."""
    errs, warns = [], []
    index = root / "docs" / "INDEX.md"
    index_text = read_text(index) if index.exists() else ""
    if not index.exists():
        errs.append("thiếu docs/INDEX.md")
    archived = set()
    for p in docs_files(root):
        rel = p.relative_to(root).as_posix()
        if index.exists() and f"({rel.removeprefix('docs/')})" not in index_text:
            errs.append(f"{rel}: chưa có trong docs/INDEX.md (chạy `orc docs index`)")
        fm, bad = doc_meta(p)
        if bad:
            errs.append(f"{rel}: {bad}")
            continue
        if fm is None:
            errs.append(f"{rel}: thiếu frontmatter")
            continue
        missing = [f for f in DOC_FIELDS if f not in fm]
        if missing:
            errs.append(f"{rel}: frontmatter thiếu {missing}")
        if fm.get("status") not in DOC_STATUS:
            errs.append(f"{rel}: status '{fm.get('status')}' phải là {'|'.join(DOC_STATUS)}")
        if len(str(fm.get("summary") or "")) > SUMMARY_MAX:
            errs.append(f"{rel}: summary > {SUMMARY_MAX} ký tự")
        if not str(fm.get("summary") or "").strip():
            errs.append(f"{rel}: thiếu summary")
        for s in as_list(fm.get("supersedes")):
            if not (root / str(s)).exists():
                errs.append(f"{rel}: supersedes {s} không tồn tại")
        if fm.get("status") in ("archived", "superseded"):
            archived.add(rel)
        if fm.get("status") in ("archived", "superseded") and not rel.startswith("docs/archive/"):
            errs.append(f"{rel}: status {fm.get('status')} phải nằm trong docs/archive/ "
                        "(nội dung lỗi thời gom một nơi)")
    for p in _walk_text_files(root):
        rel = p.relative_to(root).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ref in sorted(set(DOC_REF_RE.findall(text))):
            if not (root / ref).exists():
                msg = f"{rel}: đường dẫn gãy {ref}"
                (warns if rel in archived else errs).append(msg)
    return errs, warns


def _md_cell(text) -> str:
    return " ".join(str(text or "").split()).replace("|", "\\|")


def docs_index(root: Path) -> str:
    """Sinh lại phần tự động của docs/INDEX.md từ frontmatter. Giữ nguyên phần viết tay."""
    groups = {}
    for p in docs_files(root):
        rel = p.relative_to(root / "docs").as_posix()
        fm, _ = doc_meta(p)
        fm = fm or {}
        parts = rel.split("/")
        if parts[0] == "features" and len(parts) > 2:
            group = "/".join(parts[:2])
        elif len(parts) > 1:
            group = parts[0]
        else:
            group = "(gốc docs)"
        groups.setdefault(group, []).append((rel, fm, p.stat().st_size))
    fixed = ("architecture", "decisions", "audits", "archive")
    order = (["architecture", "decisions"] + sorted(g for g in groups if g.startswith("features/"))
             + ["audits"] + sorted(g for g in groups if g not in fixed and not g.startswith("features/"))
             + ["archive"])
    lines = [INDEX_START, "",
             "<!-- Phần này do `orc docs index` sinh từ frontmatter. Không sửa tay; sửa frontmatter rồi chạy lại. -->",
             ""]
    for g in order:
        if g not in groups:
            continue
        lines += [f"### {g}", "", "| File | Trạng thái | Đọc khi | Tóm tắt | KB |", "|---|---|---|---|---|"]
        for rel, fm, size in groups[g]:
            lines.append(f"| [{rel}]({rel}) | {_md_cell(fm.get('status'))} | {_md_cell(fm.get('read_when'))} | "
                         f"{_md_cell(fm.get('summary'))} | {max(1, round(size / 1024))} |")
        lines.append("")
    if find_root(root) is not None:
        decs = [d for d in load_registry(root, "decision") if d.get("status") == "accepted"]
        if decs:
            lines += ["### Quyết định mới (orchestra)", ""]
            lines += [f"- {d['id']} ({_md_cell(d.get('scope'))}): {_md_cell(d.get('summary'))}" for d in decs]
            lines.append("")
    lines.append(INDEX_END)
    block = "\n".join(lines)
    index = root / "docs" / "INDEX.md"
    text = read_text(index) if index.exists() else "# INDEX — bản đồ truy xuất tài liệu\n\n"
    if INDEX_START in text and INDEX_END in text:
        head, rest = text.split(INDEX_START, 1)
        _, tail = rest.split(INDEX_END, 1)
        text = head + block + tail
    else:
        text = text.rstrip() + "\n\n## Danh mục theo nhóm (tự sinh)\n\n" + block + "\n"
    write_text(index, text)
    return f"đã cập nhật {index.relative_to(root).as_posix()} ({sum(len(v) for v in groups.values())} file)"


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orc", description="orchestra-kit CLI")
    p.add_argument("-C", dest="cwd", default=".", help="thư mục làm việc")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="tạo .orchestra/")
    s.add_argument("--project-id", required=True)
    s.add_argument("--goal", default="")

    s = sub.add_parser("brief", help="tóm tắt ≤ ~1.5k token")
    s.add_argument("--key", help="Claude session_id")

    s = sub.add_parser("new", help="tạo mục mới, in ra ID")
    s.add_argument("type", choices=("task", "artifact", "decision", "context", "evidence"))
    s.add_argument("--title")
    s.add_argument("--owner")
    s.add_argument("--summary", default="")
    s.add_argument("--task")
    s.add_argument("--type", dest="art_type")
    s.add_argument("--supersedes")
    s.add_argument("--depends-on", nargs="*")
    s.add_argument("--blocked-by", nargs="*")
    s.add_argument("--acceptance", nargs="*")
    s.add_argument("--write-scope", nargs="*")
    s.add_argument("--inputs", nargs="*")
    s.add_argument("--context", nargs="*")
    s.add_argument("--scope", default="project")
    s.add_argument("--status")
    s.add_argument("--kind", default="test")
    s.add_argument("--result", default="info")
    s.add_argument("--paths", nargs="*")
    s.add_argument("--from", dest="from_plan", help="tạo task từ plan ART đã accepted")

    s = sub.add_parser("set", help="sửa trường: orc set ID key=value ...")
    s.add_argument("id")
    s.add_argument("pairs", nargs="+")

    s = sub.add_parser("show", help="xem một ID")
    s.add_argument("id")
    s.add_argument("--meta", action="store_true", help="chỉ metadata (cho Orchestrator)")
    s.add_argument("--pack", action="store_true", help="gói cho reviewer")

    sub.add_parser("next", help="chọn task kế tiếp (tất định)")

    s = sub.add_parser("apply", help="nạp envelope YAML của subagent (file hoặc -)")
    s.add_argument("file")

    s = sub.add_parser("handoff", help="mở/kiểm handoff phiên")
    s.add_argument("action", choices=("open", "check"))
    s.add_argument("--key")
    s.add_argument("--task")
    s.add_argument("--role", default="orchestrator")
    s.add_argument("--request", default="")
    s.add_argument("--sid")

    s = sub.add_parser("gate", help="plan tự chạy tiếp được không (exit 3 = phải hỏi Dung)")
    s.add_argument("id")

    s = sub.add_parser("report", help="báo cáo cho một yêu cầu (TASK gốc)")
    s.add_argument("id")

    s = sub.add_parser("ask", help="trích phần hiểu yêu cầu + câu hỏi của ART research cho Dung")
    s.add_argument("id")

    s = sub.add_parser("graph", help="graph code (tuỳ chọn): status|update|query|affected|explain|path")
    s.add_argument("action", choices=("status", "update", "query", "affected", "explain", "path", "view"))
    s.add_argument("args", nargs="*")
    s.add_argument("--force", action="store_true")
    s.add_argument("--limit", type=int)
    s.add_argument("--depth", type=int, default=2)
    s.add_argument("--open", action="store_true", help="view: mở bản đồ trong trình duyệt")

    s = sub.add_parser("docs", help="docs/INDEX.md: index (sinh lại) | check (kiểm)")
    s.add_argument("action", choices=("index", "check"))

    s = sub.add_parser("ctx", help="context: seal|check CTX-x")
    s.add_argument("action", choices=("seal", "check"))
    s.add_argument("id")

    s = sub.add_parser("validate", help="kiểm tra toàn bộ .orchestra/")
    s.add_argument("--handoff", action="store_true", help="kiểm cả handoff phiên đang mở")
    s.add_argument("--key")
    return p


def run(argv=None) -> int:
    args = build_parser().parse_args(argv)
    start = Path(args.cwd)
    if args.cmd == "init":
        for path in cmd_init(start.resolve(), args.project_id, args.goal):
            print(f"tạo {path}")
        return 0
    if args.cmd == "docs":  # chạy được cả ở dự án chưa có .orchestra/
        droot = docs_root(start)
        if args.action == "index":
            print(docs_index(droot))
            return 0
        errs, warns = docs_check(droot)
        for w in warns:
            print(f"cảnh báo: {w}")
        if errs:
            print("\n".join(errs))
            return 1
        print(f"OK ({len(docs_files(droot))} tài liệu, {len(warns)} cảnh báo)")
        return 0
    root = require_root(start)
    if args.cmd == "brief":
        print(brief_text(root, key=args.key))
    elif args.cmd == "new":
        print(_cmd_new(root, args))
    elif args.cmd == "set":
        set_fields(root, args.id, parse_assignments(args.pairs))
        print(f"đã cập nhật {args.id}")
    elif args.cmd == "show":
        sys.stdout.write(show(root, args.id, meta=args.meta, pack=args.pack))
    elif args.cmd == "next":
        print(next_report(root))
    elif args.cmd == "apply":
        text = (sys.stdin.buffer.read().decode("utf-8-sig") if args.file == "-"
                else read_text(Path(args.file)))
        print(apply_envelope(root, parse_envelope(text)))
    elif args.cmd == "handoff":
        if args.action == "open":
            print(handoff_open(root, args.role, task=args.task, key=args.key,
                               request=args.request))
        else:
            sid = args.sid or (open_marker(root, args.key) or {}).get("sid")
            if not sid:
                raise OrcError("Cần --sid hoặc --key của phiên đang mở")
            errs = handoff_errors(root, sid)
            if errs:
                print("\n".join(errs))
                return 1
            if args.key:
                close_marker(root, args.key)
            print(f"{sid}: handoff hợp lệ")
    elif args.cmd == "gate":
        reasons = gate(root, args.id)
        if reasons:
            print("ASK\n- " + "\n- ".join(reasons))
            return 3
        print("PROCEED")
    elif args.cmd == "report":
        sys.stdout.write(report(root, args.id))
    elif args.cmd == "ask":
        sys.stdout.write(ask_text(root, args.id))
    elif args.cmd == "graph":
        return _graph_cmd(root, args)
    elif args.cmd == "ctx":
        if args.action == "seal":
            e = ctx_seal(root, args.id)
            print(f"{args.id}: {e['source']}, graph {e['graph_state']}, {len(e['paths'])} file"
                  + (", truncated" if e["truncated"] else ""))
        else:
            changed = ctx_check(root, args.id)
            if changed:
                print("CTX CŨ — đọc lại các file này từ đĩa:\n- " + "\n- ".join(changed))
                return 5
            print(f"{args.id}: các file trong context chưa đổi")
    elif args.cmd == "validate":
        errs = validate(root)
        if args.handoff:
            if args.key:
                m = open_marker(root, args.key)
                if m:
                    errs += handoff_errors(root, m["sid"])
            else:
                rt = orc(root) / "runtime" / "sessions"
                for mp in rt.glob("*.yaml") if rt.is_dir() else []:
                    m = load_yaml_file(mp) or {}
                    if not m.get("closed"):
                        errs += handoff_errors(root, m["sid"])
        if errs:
            print("\n".join(errs))
            return 1
        print("OK")
    return 0


def _cmd_new(root: Path, a) -> str:
    if a.type == "task":
        if a.from_plan:
            return "\n".join(t["id"] for t in tasks_from_plan(root, a.from_plan))
        if not a.title:
            raise OrcError("new task cần --title")
        return new_task(root, title=a.title, owner=a.owner or "coder", summary=a.summary,
                        blocked_by=a.blocked_by, acceptance=a.acceptance,
                        write_scope=a.write_scope, inputs=a.inputs, context=a.context)["id"]
    if a.type == "artifact":
        if not a.art_type or not a.task:
            raise OrcError("new artifact cần --type và --task")
        return new_artifact(root, a.art_type, a.task, summary=a.summary,
                            supersedes=a.supersedes, depends_on=a.depends_on)["id"]
    if a.type == "decision":
        if not a.summary:
            raise OrcError("new decision cần --summary")
        return new_decision(root, a.summary, scope=a.scope, supersedes=a.supersedes,
                            status=a.status or "proposed")["id"]
    if a.type == "context":
        return new_context(root, a.task, a.summary, paths=a.paths)["id"]
    return new_evidence(root, a.task, a.summary, kind=a.kind, result=a.result,
                        paths=a.paths)["id"]


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        return run(argv)
    except OrcError as exc:
        print(f"orc: {exc}", file=sys.stderr)
        return 1
