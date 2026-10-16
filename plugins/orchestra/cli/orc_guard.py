"""Guard PreToolUse của orchestra-kit (v0.2 N1 sửa theo FINDING-6; ADJUSTMENTS #3, #8). Chỉ stdlib, không nạp YAML.

Nguyên tắc (Dung chốt 2026-10-08): **Bash không phải semantic sandbox.** Guard chỉ deny thao tác nguy hiểm nhận
diện được với độ tin cậy cao; mọi thứ khác do `orc verify` hậu kiểm (git diff/status, risk paths). Không suy
write_scope từ ngữ nghĩa Bash; write_scope chỉ kiểm trực tiếp cho Edit/Write. Đây là ranh giới + phát hiện,
không phải sandbox: script/`python -c` vẫn ghi được, V2 bắt sau.

- Edit/Write: `deny_always` (state/runtime/... của orchestra, `.claude/` dự án và `~/.claude/`, `.git/`, file bí mật,
  `protected_paths` của config) trừ file artifact/context/session được phép; khi có task đang chạy: chỉ write_scope
  (task coder) hoặc file được phép.
- Bash/PowerShell (mọi mode): bỏ thân heredoc và câu trong ngoặc kép có khoảng trắng, rồi khớp luật deny tin cậy cao
  (git phá huỷ, DB, publish/deploy, xoá đệ quy, ghi vào vùng deny_always, đọc file bí mật).
- Read/Grep: chặn đọc file bí mật. Web: không dùng khi đang sửa/kiểm code; khi research chỉ qua researcher-external.
- Agent/SubagentHandback/… : không ghi ⇒ cho qua. Tool lạ: cho qua, ghi "tool chưa phân loại".
SAFE_MODE (`ORC_SAFE_MODE=1`): Edit/Write chỉ kit + `.orchestra/config.yaml`; không đọc state.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent.parent
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
WEB_TOOLS = {"WebFetch", "WebSearch"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "LS"}
# Tool không ghi file của dự án (thấy trong shadow Phase 3 hoặc của Claude Code)
PASS_TOOLS = {"Agent", "Task", "SubagentHandback", "SendMessage", "TodoWrite", "ToolSearch", "AskUserQuestion",
              "Skill", "ExitPlanMode", "EnterPlanMode", "BashOutput", "KillShell", "ListAgents"}

# Vùng authority cao, tương đối gốc dự án (khớp kiểu gitignore, xem match_path)
DENY_PATHS = [".orchestra/", ".claude/", ".git/", "**/.git/"]
SECRET_PATHS = ["**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/id_rsa*", "**/id_ed25519*", "**/secrets/"]
SECRET_OK = re.compile(r"\.(example|sample|template)$")

DENY_SHELL = [
    ("git push", re.compile(r"\bgit\b(?:\s+-[Cc]\s+\S+)*\s+push\b")),
    ("git merge", re.compile(r"\bgit\b(?:\s+-[Cc]\s+\S+)*\s+merge\b")),
    ("git rebase", re.compile(r"\bgit\b(?:\s+-[Cc]\s+\S+)*\s+rebase\b")),
    ("git filter-branch", re.compile(r"\bgit\b(?:\s+-[Cc]\s+\S+)*\s+filter-(?:branch|repo)\b")),
    ("git reset --hard", re.compile(r"\bgit\b[^;&|\n]*\breset\s+(?:\S+\s+)*--hard\b")),
    ("git clean -f", re.compile(r"\bgit\b[^;&|\n]*\bclean\s+-\w*f")),
    ("git branch -D", re.compile(r"\bgit\b[^;&|\n]*\bbranch\s+(?:\S+\s+)*-D\b")),
    ("supabase db push/reset", re.compile(r"\bsupabase\s+db\s+(?:push|reset)\b")),
    ("supabase deploy/secrets", re.compile(r"\bsupabase\s+(?:functions\s+deploy|secrets\s+set)\b")),
    ("publish", re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b")),
    ("deploy", re.compile(r"\b(?:firebase|netlify)\s+deploy\b|\bvercel\b[^;&|\n]*--prod\b"
                          r"|\bgh\s+(?:release\s+create|pr\s+merge|workflow\s+run)\b")),
    ("xoá đệ quy", re.compile(r"\brm\s+(?:-\w*[rR]\w*|--recursive)\b|\bRemove-Item\b[^;&|\n]*-Recurse"
                             r"|\b(?:rmdir|rd|del)\s+/[sS]\b|\bfind\b[^;&|\n]*\s-delete\b", re.I)),
]
PSQL = re.compile(r"\bpsql\b")
LOCAL = re.compile(r"localhost|127\.0\.0\.1|::1")
# Thân heredoc tới dòng kết thúc, hoặc tới hết lệnh nếu không có dòng kết thúc (lệnh bị cắt)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?(?:\n\s*\2\b|\Z)", re.S)
# Chuỗi trong ngoặc; ngoặc không đóng (lệnh bị cắt/không hợp lệ) coi như tới hết lệnh
QUOTED = re.compile(r"'[^'\n]*(?:'|$)|\"(?:[^\"\\]|\\.)*(?:\"|$)", re.S)
SEGMENT = re.compile(r"&&|\|\||;|\||\n")
WRITE_OPS = re.compile(r"(?:^|\s)(?:\d?>>?|tee|sed|rm|mv|cp|touch|truncate|Set-Content|Add-Content|Out-File|"
                       r"New-Item|Copy-Item|Move-Item|Remove-Item|Clear-Content)(?=\s|$)")
REDIRECT = re.compile(r"(?<![<\d&])\d?>>?(?!&)\s*(\S+)")


# ---------------------------------------------------------------- khớp đường dẫn (F3)

def _norm(p: str) -> str:
    p = str(p).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _glob_re(pat: str) -> str:
    out, i = [], 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return "".join(out)


def match_path(path: str, patterns) -> bool:
    """Khớp kiểu gitignore, **neo ở gốc dự án**: `*`/`?` không qua `/`; `**` qua nhiều cấp; mẫu kết thúc `/` là
    thư mục (khớp mọi thứ bên dưới); mẫu khác khớp file đó hoặc mọi thứ dưới thư mục cùng tên."""
    p = _norm(path).rstrip("/")
    for raw in patterns or []:
        s = _norm(raw)
        if not s:
            continue
        base = _glob_re(s.rstrip("/"))
        if re.fullmatch(base + r"(?:/.*)?", p):
            return True
    return False


# ---------------------------------------------------------------- tiện ích

def bare_agent(name) -> str:
    """Tên agent bỏ namespace plugin: "orchestra:coder" → "coder" (kit cũ gọi bằng tên trần)."""
    s = str(name or "")
    return s[len("orchestra:"):] if s.startswith("orchestra:") else s


def find_root(start):
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / ".orchestra" / "config.yaml").is_file():
            return d
    return None


def safe_mode() -> bool:
    return os.environ.get("ORC_SAFE_MODE", "").strip().lower() in ("1", "true", "on", "yes")


def rel_path(root: Path, raw: str):
    """Đường dẫn tương đối gốc dự án (posix), hoặc None nếu nằm ngoài dự án."""
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def under(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def home_claude(raw: str) -> bool:
    return under(Path(os.path.expanduser(raw)), Path.home() / ".claude")


def is_secret(path: str) -> bool:
    return match_path(path, SECRET_PATHS) and not SECRET_OK.search(path)


def target_of(tool: str, ti: dict) -> str:
    if tool in WRITE_TOOLS or tool in READ_TOOLS:
        return str(ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or "")
    if tool in SHELL_TOOLS:
        return str(ti.get("command") or "")
    if tool in WEB_TOOLS:
        return str(ti.get("url") or ti.get("query") or "")
    if tool in ("Agent", "Task"):
        return str(ti.get("subagent_type") or ti.get("description") or "")
    return ""


def modes(active: dict) -> dict:
    tasks = active.get("tasks") or []
    impl = [t for t in tasks if t.get("status") == "dispatched" and str(t.get("owner", "")).startswith("coder")]
    research = [t for t in tasks if t.get("status") == "dispatched" and t not in impl]
    review = [t for t in tasks if t.get("status") == "in_review"]
    return {"implement": impl, "research": research, "verify": review}


# ---------------------------------------------------------------- Bash (FINDING-6)

def shell_view(cmd: str) -> str:
    """Bỏ thân heredoc; câu trong ngoặc có khoảng trắng thành Q, ngoặc quanh một từ (đường dẫn) được giữ lại.
    Không phân tích cú pháp shell — chỉ để luật deny không khớp vào dữ liệu/văn bản."""
    text = HEREDOC.sub("<<HEREDOC", cmd)

    def q(m):
        inner = m.group(0)[1:-1]
        return "Q" if (not inner or re.search(r"\s", inner)) else inner
    return QUOTED.sub(q, text)


def write_targets(view: str) -> list:
    """Đích ghi rõ ràng: sau chuyển hướng `>`/`>>`, và đối số của tee/sed -i/rm/mv/cp/… trong cùng đoạn lệnh."""
    out = [m.group(1) for m in REDIRECT.finditer(view)]
    for seg in SEGMENT.split(view):
        if WRITE_OPS.search(seg) and not seg.strip().startswith(("cat ", "echo ")):
            m = WRITE_OPS.search(seg)
            out += [w for w in seg[m.end():].split() if not w.startswith("-") and w not in ("Q", "<<HEREDOC")]
    return [t for t in out if t not in ("/dev/null", "$null", "nul", "NUL", "&1", "&2")]


def protected_hit(root: Path, raw: str, writable, protected) -> str | None:
    """Lý do nếu đường dẫn nằm trong vùng deny_always, ngược lại None."""
    if home_claude(raw):
        return "~/.claude"
    rel = rel_path(root, raw)
    if rel is None:
        return None
    if rel in writable:
        return None
    if match_path(rel, DENY_PATHS + list(protected or [])):
        return rel
    if is_secret(rel):
        return f"file bí mật {rel}"
    return None


def decide_shell(root: Path, cmd: str, active: dict | None) -> tuple:
    view = shell_view(cmd)
    for label, rx in DENY_SHELL:
        if rx.search(view):
            return "deny", f"deny_always: {label}"
    if PSQL.search(view) and not LOCAL.search(cmd):
        return "deny", "deny_always: psql tới host ngoài localhost"
    writable = set((active or {}).get("writable") or [])
    protected = (active or {}).get("protected") or []
    for t in write_targets(view):
        hit = protected_hit(root, t, writable, protected)
        if hit:
            return "deny", f"deny_always: ghi {hit}"
    for tok in view.split():
        tok = tok.strip("();|&<>")
        if tok and is_secret(_norm(tok)):
            return "deny", f"deny_always: chạm file bí mật {tok}"
    return "allow", "không khớp luật deny tin cậy cao (hậu kiểm bằng orc verify)"


# ---------------------------------------------------------------- quyết định

def decide(root: Path, active, tool: str, ti: dict, agent_type: str | None = None,
           safe: bool | None = None, kit: Path = KIT_DIR) -> tuple:
    """(allow|deny, lý do, mode)."""
    safe = safe_mode() if safe is None else safe
    target = target_of(tool, ti)
    if safe:
        if tool in WRITE_TOOLS:
            p = Path(target) if Path(target).is_absolute() else root / target
            if under(p, kit) or rel_path(root, target) == ".orchestra/config.yaml":
                return "allow", "SAFE_MODE: sửa kit/cấu hình orchestra", "safe"
            return "deny", "SAFE_MODE: chỉ sửa kit và .orchestra/config.yaml", "safe"
        if tool in SHELL_TOOLS:
            return (*decide_shell(root, target, None), "safe")
        return "allow", "SAFE_MODE: tool không ghi", "safe"

    if active is None:
        raise RuntimeError("thiếu runtime/active.json")  # chế độ thật: fail-closed
    m = modes(active)
    mode = ("implement" if m["implement"] else "research" if m["research"]
            else "verify" if m["verify"] else "normal")
    writable = set(active.get("writable") or [])
    if tool in WRITE_TOOLS:
        hit = protected_hit(root, target, writable, active.get("protected"))
        if hit:
            return "deny", f"deny_always: ghi {hit}", mode
        rel = rel_path(root, target)
        if rel is None:
            if under(Path(target), Path(tempfile.gettempdir())):
                return "allow", "thư mục tạm của hệ thống", mode
            if mode == "normal":
                return "allow", "không có task đang chạy (ngoài dự án)", mode
            return "deny", f"{mode}: ghi ngoài dự án", mode
        if mode == "normal" or rel in writable:
            return "allow", ("không có task đang chạy" if mode == "normal"
                             else f"{mode}: file artifact/context được phép"), mode
        scope = [s for t in m["implement"] for s in t.get("write_scope") or []]
        if scope and match_path(rel, scope):
            return "allow", f"{mode}: trong write_scope", mode
        return "deny", f"{mode}: {rel} ngoài write_scope/artifact của task đang chạy", mode
    if tool in SHELL_TOOLS:
        return (*decide_shell(root, target, active), mode)
    if tool in READ_TOOLS:
        rel = rel_path(root, target) if target else None
        if (rel and is_secret(rel)) or (target and is_secret(_norm(target))):
            return "deny", f"deny_always: đọc file bí mật {target}", mode
        return "allow", "đọc", mode
    if tool in WEB_TOOLS:
        if mode in ("implement", "verify"):
            return "deny", f"{mode}: không dùng web khi đang sửa/kiểm code", mode
        if mode == "research" and bare_agent(agent_type) != "researcher-external":
            return "deny", "research: web chỉ qua subagent researcher-external", mode
        return "allow", f"{mode}: web", mode
    if tool in PASS_TOOLS:
        return "allow", "tool không ghi file", mode
    return "allow", f"tool chưa phân loại: {tool}", mode


def load_active(root: Path):
    path = root / ".orchestra" / "runtime" / "active.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def refresh_active(root: Path) -> None:
    """Shadow trên dự án vẫn chạy `orc` 0.1.0 (không ghi active.json): tự dựng lại từ registry khi cũ.
    Chỉ ghi `runtime/active.json` (gitignore), không đổi workflow. Chế độ thật không dùng đường này."""
    o = root / ".orchestra"
    act = o / "runtime" / "active.json"
    src = [o / "state" / "tasks.yaml", o / "state" / "artifacts.yaml", o / "state" / "contexts.yaml"]
    newest = max((p.stat().st_mtime for p in src if p.exists()), default=0)
    if act.exists() and act.stat().st_mtime >= newest:
        return
    import orc_core  # noqa: PLC0415 - nạp YAML chỉ khi registry đổi
    orc_core.write_active(root)


def shadow(payload: dict) -> dict | None:
    """Logic hook ở shadow. Trả bản ghi đã log (để test), None nếu không phải dự án orchestra."""
    t0 = time.perf_counter()
    root = find_root(payload.get("cwd") or ".")
    if root is None:
        return None
    tool, ti = payload.get("tool_name") or "", payload.get("tool_input") or {}
    try:
        if not safe_mode():
            refresh_active(root)
        decision, reason, mode = decide(root, None if safe_mode() else load_active(root), tool, ti,
                                        payload.get("agent_type"))
    except Exception as exc:  # noqa: BLE001 - chế độ thật sẽ exit 2
        decision, reason, mode = "deny", f"lỗi guard (fail-closed): {exc}", "error"
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": payload.get("session_id"),
           "agent_type": payload.get("agent_type"), "tool": tool, "target": target_of(tool, ti)[:200],
           "mode": mode, "decision": decision, "reason": reason,
           "ms": round((time.perf_counter() - t0) * 1000, 1)}
    log = root / ".orchestra" / "runtime" / "guard-shadow.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ---------------------------------------------------------------- nhật ký lời Dung (hook UserPromptSubmit)

ORC_LINE = re.compile(r"^\s*(orc:[a-z]+\b.*?)\s*$", re.M)


def _sha(text: str) -> str:
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompts_path(root: Path) -> Path:
    return root / ".orchestra" / "runtime" / "prompts.jsonl"


def log_prompt(payload: dict) -> dict | None:
    root = find_root(payload.get("cwd") or ".")
    if root is None:
        return None
    prompt = str(payload.get("prompt") or "")
    path = prompts_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
    from datetime import datetime  # noqa: PLC0415
    rec = {"ts": datetime.now().isoformat(timespec="microseconds"), "session": payload.get("session_id"),
           "sha256": _sha(prompt), "orc": ORC_LINE.findall(prompt),
           "prev": _sha(lines[-1]) if lines else "0" * 64}
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec
