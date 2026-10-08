"""orc verify — kiểm chứng tất định V1/V2 (v0.2 J1, N3; ADJUSTMENTS #7, #8).

- Checkpoint khi giao task coder: HEAD từng repo, file bẩn/chưa track (+ sha256), mục ignored, và bản chụp
  mục `verify:` của config. Lệnh kiểm lấy từ bản chụp này, không từ config hiện tại (H8).
- Scope (V2): file đổi kể từ checkpoint so với write_scope. Đây là **phát hiện sau khi xảy ra** trên ranh
  giới ghi, không phải sandbox: không chặn được việc ghi, chỉ báo.
- Lệnh (V1/V2): env bỏ biến kiểu secret, cwd cố định trong gốc dự án, timeout giết cả cây tiến trình.
  Lệnh cố định vẫn chạy mã của dự án (test, script npm): không phải "an toàn", chỉ là "biết đang chạy gì".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import orc_core as oc
import orc_guard

COMMAND_NAMES = ("test", "typecheck", "lint", "build")
DEFAULT_TIMEOUT = 600
# Mẫu khớp kiểu gitignore, neo ở gốc dự án (orc_guard.match_path — FINDING-3): `**/` = mọi cấp, kể cả gốc
DEFAULT_RISK = ["**/migrations/", "supabase/", "**/auth/", "**/*rls*", "**/.github/", ".claude/", ".orchestra/",
                "**/package.json", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock", "**/.env",
                "**/.env.*"]
DEFAULT_GUARD = ["**/package.json", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock"]
# Thư mục sinh ra khi build/test (gitignore): không tính là "ghi ngoài scope". Ghi vào đây không bị phát hiện.
DEFAULT_ARTIFACTS = ["**/node_modules/", "**/dist/", "**/build/", "**/coverage/", "**/.vite/", "**/__pycache__/",
                     "**/*.tsbuildinfo"]
# F4: chữ ký lỗi MÔI TRƯỜNG tin cậy cao — lệnh không chạy được, không phải dự án sai.
# Không xếp vào đây: timeout (có thể test treo), "Cannot find module" (có thể import sai trong code).
ENV_SIGNS = [
    ("Windows Application Control chặn", re.compile(r"Application Control policy has blocked", re.I)),
    ("thiếu native binding", re.compile(r"Cannot find native binding", re.I)),
    ("không tìm thấy lệnh", re.compile(r"is not recognized as an internal or external command|command not found"
                                      r"|No such file or directory.*\b(?:npm|node|npx|python[0-9.]*)\b", re.I)),
    ("không có quyền chạy", re.compile(r"\bEACCES\b|Access is denied\.", re.I)),
]
FAILURE_OF = {"test": "TEST_FAILURE", "lint": "LINT_FAILURE", "build": "BUILD_FAILURE",
              "typecheck": "TYPECHECK_FAILURE"}
SECRET_ENV = re.compile(r"TOKEN|SECRET|PASSW|KEY|CREDENTIAL|AUTH|COOKIE|SESSION|PRIVATE", re.I)
# Không bắt chữ "service_role" trần: README/script nhắc tên biến là bình thường (replay Phase 2: 2 báo nhầm).
# Khoá thật của Supabase là JWT ⇒ mẫu JWT bắt được.
SECRET_TEXT = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}")),
    ("AWS key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("API key", re.compile(r"\b(?:sk|pk|ghp|gho|xox[abp])[-_][A-Za-z0-9_-]{20,}")),
    ("mật khẩu/khoá gán cứng", re.compile(
        r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]
MAX_SCAN_BYTES = 1_000_000


# ---------------------------------------------------------------- cấu hình

def normalize(vcfg) -> dict:
    """Chuẩn hoá mục `verify:` của config. Lỗi ⇒ OrcError (fail-closed)."""
    if not isinstance(vcfg, dict):
        raise oc.OrcError("config.yaml: `verify` phải là mapping")
    timeout = int(vcfg.get("timeout", DEFAULT_TIMEOUT))
    cmds = {}
    for name, spec in (vcfg.get("commands") or {}).items():
        if name not in COMMAND_NAMES:
            raise oc.OrcError(f"verify.commands: '{name}' không thuộc {COMMAND_NAMES}")
        if isinstance(spec, str):
            spec = {"run": spec}
        if not isinstance(spec, dict) or not str(spec.get("run") or "").strip():
            raise oc.OrcError(f"verify.commands.{name}: cần `run`")
        cmds[name] = {"run": str(spec["run"]), "cwd": str(spec.get("cwd", ".")).replace("\\", "/"),
                      "timeout": int(spec.get("timeout", timeout))}
    repos = [str(r).replace("\\", "/").strip("/") or "." for r in oc.as_list(vcfg.get("repos")) or ["."]]
    return {"repos": repos, "commands": cmds,
            "risk_paths": oc.as_list(vcfg.get("risk_paths")) or DEFAULT_RISK,
            "guard_paths": oc.as_list(vcfg.get("guard_paths")) or DEFAULT_GUARD,
            "artifact_paths": oc.as_list(vcfg.get("artifact_paths")) or DEFAULT_ARTIFACTS}


def project_verify_config(root: Path):
    v = oc.load_config(root).get("verify")
    return normalize(v) if v else None


# ---------------------------------------------------------------- git

def git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if r.returncode != 0:
        raise oc.OrcError(f"git {' '.join(args)} ở {repo}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8", "replace")


def _z(text: str) -> list:
    return [p for p in text.split("\0") if p]


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _prefix(rel: str) -> str:
    return "" if rel == "." else rel + "/"


def repo_snapshot(root: Path, rel: str) -> dict:
    d = root / rel
    head = git(d, "rev-parse", "HEAD").strip()
    dirty = set(_z(git(d, "diff", "--name-only", "-z", "HEAD")))
    dirty |= set(_z(git(d, "ls-files", "--others", "--exclude-standard", "-z")))
    ignored = sorted(e[3:] for e in _z(git(d, "status", "--porcelain=v1", "-z", "--ignored", "-unormal"))
                     if e.startswith("!! "))
    return {"head": head, "dirty": {p: _sha(d / p) for p in sorted(dirty)}, "ignored": ignored}


def match_any(path: str, patterns) -> bool:
    return orc_guard.match_path(path, list(patterns))


# ---------------------------------------------------------------- checkpoint

def checkpoint_path(root: Path, tid: str) -> Path:
    return oc.orc(root) / "state" / "checkpoints" / f"{tid}.json"


def make_checkpoint(root: Path, tid: str, vcfg: dict | None = None) -> str | None:
    """Ghi checkpoint (nếu chưa có) và trả sha256 nội dung; None nếu dự án chưa cấu hình verify."""
    vcfg = vcfg or project_verify_config(root)
    if vcfg is None:
        return None
    path = checkpoint_path(root, tid)
    if path.exists():  # giao lại (sửa lỗi) giữ checkpoint gốc: scope tính từ trước mọi thay đổi
        return None
    data = {"task": tid, "created": dt.datetime.now().isoformat(timespec="seconds"), "verify": vcfg,
            "repos": {rel: repo_snapshot(root, rel) for rel in vcfg["repos"]}}
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    oc.write_text(path, text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_checkpoint(root: Path, tid: str) -> dict:
    path = checkpoint_path(root, tid)
    if not path.exists():
        raise oc.OrcError(f"{tid}: chưa có checkpoint (giao task bằng `orc advance {tid} --to dispatched` "
                          "khi config đã có mục verify)")
    text = oc.read_text(path)
    want = None
    jp = oc.journal_path(root)
    for line in (oc.read_text(jp).splitlines() if jp.exists() else []):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("id") == tid and row.get("checkpoint"):
            want = row["checkpoint"]
    if want != hashlib.sha256(text.encode("utf-8")).hexdigest():
        raise oc.OrcError(f"{tid}: checkpoint không khớp journal (bị sửa hoặc không do orc tạo); "
                          "không verify")
    return json.loads(text)


# ---------------------------------------------------------------- V2 scope

def changed_files(root: Path, cp: dict) -> tuple:
    """(file đổi kể từ checkpoint, mục ignored mới), đường dẫn tương đối gốc dự án."""
    changed, ignored_new = set(), set()
    for rel, snap in cp["repos"].items():
        d, pre = root / rel, _prefix(rel)
        cand = set(_z(git(d, "diff", "--name-only", "-z", snap["head"])))
        cand |= set(_z(git(d, "ls-files", "--others", "--exclude-standard", "-z")))
        dirty0 = snap["dirty"]
        for p in cand - set(dirty0):
            changed.add(pre + p)
        for p, h in dirty0.items():  # bẩn từ trước: chỉ tính khi nội dung đổi
            if _sha(d / p) != h:
                changed.add(pre + p)
        now = {e[3:] for e in _z(git(d, "status", "--porcelain=v1", "-z", "--ignored", "-unormal"))
               if e.startswith("!! ")}
        ignored_new |= {pre + p for p in now - set(snap["ignored"])}
    changed = {p for p in changed if not p.startswith(".orchestra/")}
    ignored_new = {p for p in ignored_new if not p.startswith(".orchestra/")
                   and not match_any(p, cp["verify"]["artifact_paths"])}
    return sorted(changed), sorted(ignored_new)


def added_text(root: Path, cp: dict, path: str) -> str:
    for rel, snap in cp["repos"].items():
        pre = _prefix(rel)
        if pre and not path.startswith(pre):
            continue
        sub = path[len(pre):]
        d = root / rel
        f = d / sub
        if not f.is_file() or f.stat().st_size > MAX_SCAN_BYTES:
            return ""
        tracked = git(d, "ls-files", "-z", "--", sub)
        if tracked:
            diff = git(d, "diff", "-U0", snap["head"], "--", sub)
            return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
        return f.read_bytes().decode("utf-8", "replace")
    return ""


def scan_secrets(root: Path, cp: dict, files: list) -> list:
    hits = []
    for f in files:
        text = added_text(root, cp, f)
        for label, rx in SECRET_TEXT:
            if rx.search(text):
                hits.append(f"{f}: {label}")
    return hits


# ---------------------------------------------------------------- V1/V2 lệnh

def safe_env() -> dict:
    return {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}


def _kill_tree(p: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def count_tests(log: str) -> dict:
    out = {}
    for key in ("pass", "fail"):
        m = re.findall(rf"^(?:#|ℹ)\s*{key}\s+(\d+)\s*$", log, re.M)
        if m:
            out[key] = int(m[-1])
    return out


def run_command(root: Path, name: str, spec: dict, logdir: Path) -> dict:
    cwd = (root / spec["cwd"]).resolve()
    base = root.resolve()
    if cwd != base and base not in cwd.parents:
        raise oc.OrcError(f"verify.commands.{name}.cwd '{spec['cwd']}' nằm ngoài gốc dự án")
    if not cwd.is_dir():
        raise oc.OrcError(f"verify.commands.{name}.cwd '{spec['cwd']}' không tồn tại")
    kw = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
          else {"start_new_session": True})
    start = time.monotonic()
    p = subprocess.Popen(spec["run"], shell=True, cwd=str(cwd), env=safe_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    timed_out = False
    try:
        out, _ = p.communicate(timeout=spec["timeout"])
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(p)
        out, _ = p.communicate()
    secs = round(time.monotonic() - start, 1)
    logdir.mkdir(parents=True, exist_ok=True)
    log_path = logdir / f"{name}.log"
    log_path.write_bytes(out)
    text = out.decode("utf-8", "replace")
    result, fclass, sign = classify(name, p.returncode, timed_out, text)
    return {"name": name, "run": spec["run"], "cwd": spec["cwd"], "exit": p.returncode,
            "timed_out": timed_out, "seconds": secs, "log": log_path.relative_to(root).as_posix(),
            "log_sha256": hashlib.sha256(out).hexdigest(), "counts": count_tests(text),
            "result": result, "failure_class": fclass, "env_sign": sign}


def classify(name: str, exit_code, timed_out: bool, log: str) -> tuple:
    """(pass|fail|env, failure_class, chữ ký). env = ENVIRONMENT_FAILURE: không tính là lỗi của dự án (F4)."""
    if exit_code == 0 and not timed_out:
        return "pass", None, None
    if not timed_out:
        for label, rx in ENV_SIGNS:
            if rx.search(log):
                return "env", "ENVIRONMENT_FAILURE", label
        if exit_code in (126, 127, 9009):  # không chạy được / không tìm thấy lệnh (sh, cmd.exe)
            return "env", "ENVIRONMENT_FAILURE", f"exit {exit_code}"
    return "fail", FAILURE_OF.get(name, "TEST_FAILURE"), None


# ---------------------------------------------------------------- verify

def _evd(root: Path, tid: str, kind: str, result: str, summary: str, details: dict, paths=None) -> str:
    with oc.state_lock(root):  # chỉ khoá lúc ghi; lệnh kiểm chạy lâu không giữ khoá
        e = oc.new_evidence(root, tid, oc._short(summary, oc.SUMMARY_MAX), kind=kind, result=result,
                            paths=paths, by="orc")
        body = (f"# Evidence {e['id']} (task {tid}) — tạo bởi `orc verify`\n\n"
                "```yaml orc-verify\n" + oc.dump_yaml(details) + "```\n")
        fm = {"id": e["id"], "task": tid, "kind": kind, "result": result, "by": "orc"}
        oc.write_text(oc.content_path(root, e["id"]), oc.join_frontmatter(fm, body))
    return e["id"]


def verify(root: Path, tid: str, scope_override=None) -> dict:
    """Chạy V2 scope + lệnh kiểm; tạo EVD `by: orc`. Không đổi trạng thái task (Phase 2: song song)."""
    _, _, task = oc.find_entry(root, tid)
    cp = load_checkpoint(root, tid)
    vcfg = cp["verify"]
    scope = oc.as_list(scope_override if scope_override is not None else task.get("write_scope"))
    changed, ignored_new = changed_files(root, cp)
    outside = [f for f in changed + ignored_new if not oc._in_scope(f, scope)]
    risky = [f for f in changed if match_any(f, vcfg["risk_paths"])]
    guard = [f for f in changed if match_any(f, vcfg["guard_paths"])]
    secrets = scan_secrets(root, cp, changed)
    scope_ok = not outside and not secrets
    evds = [_evd(root, tid, "scope", "pass" if scope_ok else "fail",
                 f"orc verify scope: {len(changed)} file đổi, {len(outside)} ngoài write_scope, "
                 f"{len(secrets)} nghi bí mật, {len(risky)} risk_path",
                 {"changed": changed, "ignored_new": ignored_new, "outside_scope": outside,
                  "risk_paths_hit": risky, "secrets": secrets, "write_scope": scope,
                  "base": {r: s["head"] for r, s in cp["repos"].items()}})]
    runs = []
    logdir = oc.orc(root) / "runtime" / "verify" / tid
    for name, spec in vcfg["commands"].items():
        if guard:
            res = {"name": name, "run": spec["run"], "result": "fail", "skipped": True,
                   "reason": "file định nghĩa lệnh đổi kể từ checkpoint: " + ", ".join(guard)}
            summary = f"orc verify {name}: KHÔNG chạy — {', '.join(guard)} đổi kể từ checkpoint"
        else:
            res = run_command(root, name, spec, logdir)
            c = res["counts"]
            extra = f", pass {c.get('pass')}/fail {c.get('fail')}" if c else ""
            head = f"{res['failure_class']} ({res['env_sign']}) — " if res["result"] == "env" else ""
            summary = (f"orc verify {name}: {head}`{spec['run']}` exit {res['exit']}"
                       f"{' (timeout)' if res['timed_out'] else ''} trong {res['seconds']}s{extra}")
        runs.append(res)
        evd_result = "info" if res["result"] == "env" else res["result"]
        evds.append(_evd(root, tid, name, evd_result, summary, res,
                         paths=[res["log"]] if res.get("log") else None))
    with oc.state_lock(root):  # gắn EVD vào task để reviewer thấy trong `orc show --pack`
        _, _, task = oc.find_entry(root, tid)
        oc.set_fields(root, tid, {"outputs": oc.as_list(task.get("outputs")) + evds})
    return {"task": tid, "evidence": evds, "scope_ok": scope_ok, "outside": outside, "secrets": secrets,
            "risky": risky, "guard": guard, "runs": runs,
            "compare": compare(root, tid, dict([("scope", "pass" if scope_ok else "fail")]
                                               + [(r["name"], r["result"]) for r in runs]))}


def compare(root: Path, tid: str, orc_results: dict) -> list:
    """So EVD tự khai (by agent) với kết quả orc theo kind. LỆCH = tự khai pass mà orc fail."""
    agent = {}
    for e in oc.load_registry(root, "evidence"):
        if e.get("task") == tid and e.get("by", "agent") != "orc":
            agent.setdefault(e.get("kind"), []).append(e)
    rows = []
    for kind, res in orc_results.items():
        claims = agent.get(kind, [])
        passes = [e["id"] for e in claims if e.get("result") == "pass"]
        if res == "env":
            verdict = "không kiểm được (ENVIRONMENT_FAILURE)"
        elif res == "fail" and passes:
            verdict = "LỆCH"
        elif not claims:
            verdict = "không có tự khai"
        else:
            verdict = "khớp"
        rows.append({"kind": kind, "orc": res, "agent_pass": passes,
                     "agent_other": [e["id"] for e in claims if e.get("result") != "pass"], "verdict": verdict})
    return rows


def overall(res: dict) -> str:
    """PASS | FAIL (lỗi của dự án) | INCOMPLETE (chỉ còn lỗi môi trường: chưa kiểm được, không phải fail)."""
    got = {r["orc"] for r in res["compare"]}
    return "FAIL" if "fail" in got else "INCOMPLETE" if "env" in got else "PASS"


EXIT_CODE = {"PASS": 0, "FAIL": 6, "INCOMPLETE": 7}


def render(res: dict) -> str:
    lines = [f"VERIFY {res['task']}: {overall(res)}"]
    for r in res["compare"]:
        lines.append(f"- {r['kind']}: orc {r['orc']} | tự khai pass {r['agent_pass'] or '-'} | {r['verdict']}")
    if res["outside"]:
        lines.append("Ngoài write_scope: " + ", ".join(res["outside"]))
    if res["secrets"]:
        lines.append("Nghi bí mật: " + "; ".join(res["secrets"]))
    if res["guard"]:
        lines.append("Không chạy lệnh vì đổi: " + ", ".join(res["guard"]))
    for r in res["runs"]:
        if r.get("result") == "env":
            lines.append(f"ENVIRONMENT_FAILURE {r['name']}: {r.get('env_sign')} — lệnh không chạy được, chưa kiểm "
                         f"(log {r.get('log')})")
    if res["risky"]:
        lines.append("Chạm risk_paths: " + ", ".join(res["risky"]))
    lines.append("EVD: " + ", ".join(res["evidence"]))
    return "\n".join(lines) + "\n"
