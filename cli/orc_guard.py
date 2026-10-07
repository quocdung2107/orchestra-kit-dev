"""Guard PreToolUse của orchestra-kit (v0.2 N1, K3; ADJUSTMENTS #3, #8). Chỉ stdlib, không nạp YAML.

Đọc `.orchestra/runtime/active.json` (orc ghi mỗi lần lưu registry) và quyết định allow/deny cho một tool call.
Phase 3: chỉ **shadow** — hook luôn cho qua, ghi quyết định vào `runtime/guard-shadow.jsonl`.

Ánh xạ trạng thái 0.1.0 → mode của v0.2:
  task coder `dispatched`      → IMPLEMENTING: Edit/Write chỉ trong write_scope; Bash allowlist; không web
  task khác `dispatched`       → RESEARCH/PLAN: Edit/Write chỉ file artifact của task; Bash đọc + orc
  task `in_review`             → VERIFYING: Edit/Write chỉ file artifact của task (report); Bash đọc/test
  không có task đang chạy      → bình thường (quyền của Dung)
  luôn luôn (deny_always)      → state/runtime/evidence của orchestra, .claude/, push/merge/rebase/reset --hard,
                                 --force, rm -r, supabase db push, psql ngoài localhost, npm publish
SAFE_MODE (`ORC_SAFE_MODE=1`, Dung đặt trước khi mở VS Code): chỉ sửa kit + `.orchestra/config.yaml`, không đọc
state — chạy được cả khi state/orc hỏng. Không có lối tắt tắt guard.

Guard là ranh giới + phát hiện, không phải sandbox: Bash/script vẫn ghi gián tiếp được (W1.2); V2 bắt sau.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import time
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent.parent
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
WEB_TOOLS = {"WebFetch", "WebSearch"}
DENY_PATHS = [".orchestra/state/**", ".orchestra/runtime/**", ".orchestra/evidence/**", ".claude/**"]
DENY_SHELL = [
    ("git push", re.compile(r"\bgit\b[^|;&]*\bpush\b")),
    ("git merge", re.compile(r"\bgit\b[^|;&]*\bmerge\b")),
    ("git rebase", re.compile(r"\bgit\b[^|;&]*\brebase\b")),
    ("git reset --hard", re.compile(r"\breset\s+--hard\b")),
    ("--force", re.compile(r"--force\b")),
    ("xoá đệ quy", re.compile(r"\brm\s+-[a-zA-Z]*[rR]|\brm\s+--recursive\b|Remove-Item\b[^|;&]*-Recurse", re.I)),
    ("supabase db push", re.compile(r"\bsupabase\s+db\s+push\b")),
    ("npm publish", re.compile(r"\bnpm\s+publish\b")),
    ("ghi state orchestra", re.compile(r"\.orchestra[\\/](state|runtime|evidence)\b")),
    ("sửa .claude/settings", re.compile(r"\.claude[\\/]settings")),
]
PSQL = re.compile(r"\bpsql\b")
LOCAL = re.compile(r"localhost|127\.0\.0\.1|::1")
SEGMENT = re.compile(r"&&|\|\||;|\|")
REDIRECT = re.compile(r"(?<![0-9&])>{1,2}(?!&)\s*(?!/dev/null|\$null|nul\b)\S")
READ_CMDS = {"ls", "dir", "cat", "type", "head", "tail", "grep", "rg", "find", "wc", "pwd", "echo", "which",
             "Get-ChildItem", "Get-Content", "Select-String", "Test-Path", "Get-Location", "sort", "diff", "cd",
             "sed"}
GIT_READ = {"status", "diff", "log", "show", "branch", "rev-parse", "ls-files", "blame"}
GIT_IMPL = GIT_READ | {"add", "commit", "checkout", "switch", "stash"}
TEST_CMD = re.compile(r"^(npm\s+(run\s+)?(test|lint|build|typecheck)\b|npx\s+(tsc|vitest|oxlint)\b|node\s+--test\b"
                      r"|python[0-9.]*(\.exe)?\s+-m\s+(unittest|pytest)\b|pytest\b|tsc\b)")
# Ở SAFE_MODE chỉ cho lệnh orc đọc (orc cũng tự từ chối lệnh đổi workflow)
ORC_SAFE_READ = {"brief", "show", "validate", "report", "gate", "ask", "graph"}


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
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def in_patterns(path: str, patterns) -> bool:
    p = path.replace("\\", "/")
    for s in patterns:
        s = str(s).replace("\\", "/")
        s = s[2:] if s.startswith("./") else s
        if fnmatch.fnmatch(p, s) or p == s.rstrip("/") or p.startswith(s.rstrip("/*") + "/"):
            return True
    return False


def under(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def target_of(tool: str, ti: dict) -> str:
    if tool in WRITE_TOOLS:
        return str(ti.get("file_path") or ti.get("notebook_path") or "")
    if tool in SHELL_TOOLS:
        return str(ti.get("command") or "")
    if tool in WEB_TOOLS:
        return str(ti.get("url") or ti.get("query") or "")
    return ""


def _first_word(seg: str) -> list:
    return seg.strip().split()


def orc_sub(words: list):
    """Lệnh con của `orc` nếu đoạn lệnh gọi orc (orc, orc.cmd, python .../orc), ngược lại None."""
    for i, w in enumerate(words):
        name = w.replace("\\", "/").rsplit("/", 1)[-1].strip('"\'')
        if name in ("orc", "orc.cmd"):
            j = i + 1
            while j < len(words) and words[j] == "-C":
                j += 2
            rest = words[j:]
            return rest[0] if rest else ""
        if i > 2:
            break
    return None


def shell_segment_ok(seg: str, mode: str) -> bool:
    words = _first_word(seg)
    if not words:
        return True
    head = words[0].strip('"\'')
    sub = orc_sub(words)
    if sub is not None:
        return True if mode != "safe" else sub in ORC_SAFE_READ
    if head in READ_CMDS:
        return not (head == "sed" and "-i" in words)
    if head == "git":
        args = [w for w in words[1:] if not w.startswith("-")]
        if words[1:2] == ["-C"]:
            args = [w for w in words[3:] if not w.startswith("-")]
        verb = args[0] if args else ""
        return verb in (GIT_IMPL if mode == "implement" else GIT_READ)
    if TEST_CMD.match(seg.strip()):
        return mode in ("implement", "verify", "research")
    return False


def decide_shell(cmd: str, mode: str, kit: Path) -> tuple:
    for label, rx in DENY_SHELL:
        if rx.search(cmd):
            if label == "ghi state orchestra" and all(orc_sub(_first_word(s)) is not None
                                                      for s in SEGMENT.split(cmd) if s.strip()):
                continue  # chính orc ghi state
            return "deny", f"deny_always: {label}"
    if PSQL.search(cmd) and not LOCAL.search(cmd):
        return "deny", "deny_always: psql tới host ngoài localhost"
    if mode == "normal":
        return "allow", "không có task đang chạy"
    if mode == "safe" and (str(kit).replace("\\", "/") in cmd.replace("\\", "/")):
        return "allow", "SAFE_MODE: lệnh trong thư mục kit"
    if REDIRECT.search(cmd):
        return "deny", f"{mode}: ghi file bằng chuyển hướng shell"
    bad = [s.strip() for s in SEGMENT.split(cmd) if s.strip() and not shell_segment_ok(s, mode)]
    if bad:
        return "deny", f"{mode}: lệnh ngoài allowlist: {bad[0][:80]}"
    return "allow", f"{mode}: allowlist"


def modes(active: dict) -> dict:
    tasks = active.get("tasks") or []
    impl = [t for t in tasks if t.get("status") == "dispatched" and str(t.get("owner", "")).startswith("coder")]
    research = [t for t in tasks if t.get("status") == "dispatched" and t not in impl]
    review = [t for t in tasks if t.get("status") == "in_review"]
    return {"implement": impl, "research": research, "verify": review}


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
            return (*decide_shell(target, "safe", kit), "safe")
        return "allow", "SAFE_MODE: tool không ghi", "safe"

    if active is None:
        raise RuntimeError("thiếu runtime/active.json")  # chế độ thật: fail-closed
    m = modes(active)
    mode = ("implement" if m["implement"] else "research" if m["research"]
            else "verify" if m["verify"] else "normal")
    if tool in WRITE_TOOLS:
        rel = rel_path(root, target)
        if rel is not None and in_patterns(rel, DENY_PATHS):
            return "deny", f"deny_always: ghi {rel}", mode
        if rel is None and "/.claude/" in target.replace("\\", "/") + "/":
            return "deny", "deny_always: ghi .claude", mode
        if mode == "normal":
            return "allow", "không có task đang chạy", mode
        if rel is None:
            return "deny", f"{mode}: ghi ngoài dự án", mode
        allowed = [a for t in m["research"] + m["verify"] + m["implement"] for a in t.get("artifacts") or []]
        scope = [s for t in m["implement"] for s in t.get("write_scope") or []]
        if rel in allowed or (scope and in_patterns(rel, scope)):
            return "allow", f"{mode}: trong write_scope/artifact của task", mode
        return "deny", f"{mode}: {rel} ngoài write_scope/artifact của task đang chạy", mode
    if tool in SHELL_TOOLS:
        return (*decide_shell(target, mode, KIT_DIR), mode)
    if tool in WEB_TOOLS:
        if mode in ("implement", "verify"):
            return "deny", f"{mode}: không dùng web khi đang sửa/kiểm code", mode
        if mode == "research" and agent_type != "researcher-external":
            return "deny", "research: web chỉ qua subagent researcher-external", mode
        return "allow", f"{mode}: web", mode
    return "allow", "tool không ghi", mode


def load_active(root: Path):
    path = root / ".orchestra" / "runtime" / "active.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def shadow(payload: dict) -> dict | None:
    """Logic hook ở shadow. Trả bản ghi đã log (để test), None nếu không phải dự án orchestra."""
    t0 = time.perf_counter()
    root = find_root(payload.get("cwd") or ".")
    if root is None:
        return None
    tool, ti = payload.get("tool_name") or "", payload.get("tool_input") or {}
    try:
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
