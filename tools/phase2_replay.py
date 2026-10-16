"""Phase 2 — phát lại yêu cầu thật của 0.1.0 trên thư mục tạm, chạy `orc verify` thật, so với EVD tự khai.

    python tools/phase2_replay.py --project D:/WMS --app-repo app --work <thư mục tạm> \
        --request TASK-0001=21ff20b:904d9db ...

Mỗi --request: <TASK gốc>=<commit dự án>:<commit repo con>. Cho mỗi yêu cầu:
1. Clone (chỉ đọc nguồn) dự án và repo con vào --work; node_modules và samples/ chép một lần.
2. Đưa cây về trạng thái *trước* yêu cầu: repo con ở commit cha; ở repo gốc các file không thuộc .orchestra/
   về bản của commit cha (registry vẫn ở commit của yêu cầu để có task, write_scope và EVD tự khai).
3. Ghi mục `verify:` vào config bản sao, tạo checkpoint bằng API nội bộ (task đã done nên không advance được),
   rồi đưa cây về commit của yêu cầu (= thay đổi thật của coder).
4. `orc_verify.verify` với scope = hợp write_scope các task coder của yêu cầu (commit gộp theo yêu cầu),
   so kết quả orc với EVD tự khai của từng task coder.
Không ghi gì vào --project.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT = REPO / "plugins" / "orchestra"  # gốc plugin (cli/, hooks/, templates/…)
sys.path.insert(0, str(KIT / "cli"))
sys.path.insert(0, str(REPO / "tools"))
import orc_core as oc  # noqa: E402
import orc_verify as ov  # noqa: E402
import phase0_baseline as pb  # noqa: E402

VERIFY = {"repos": [".", "app"], "timeout": 900,
          "commands": {"test": {"run": "npm run test", "cwd": "app"},
                       "lint": {"run": "npm run lint", "cwd": "app"},
                       "build": {"run": "npm run build", "cwd": "app"}}}


def g(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout


def prepare(project: Path, app_repo: str, work: Path) -> Path:
    root = work / "WMS"
    if not root.exists():
        subprocess.run(["git", "clone", "-q", str(project), str(root)], check=True)
        subprocess.run(["git", "clone", "-q", str(project / app_repo), str(root / app_repo)], check=True)
        print(f"chép node_modules và samples vào {root} ...", file=sys.stderr)
        shutil.copytree(project / app_repo / "node_modules", root / app_repo / "node_modules", symlinks=True)
        if (project / "samples").is_dir():
            shutil.copytree(project / "samples", root / "samples")
    return root


def replay(root: Path, app_repo: str, req: str, sha: str, app_sha: str) -> list:
    app = root / app_repo
    g(root, "checkout", "-q", "-f", sha)
    g(root, "clean", "-q", "-fd")
    g(app, "checkout", "-q", "-f", f"{app_sha}^")
    g(app, "clean", "-q", "-fd")
    # repo gốc: file ngoài .orchestra về bản commit cha
    added, deleted = [], []
    for line in g(root, "diff", "--name-status", f"{sha}^", sha).splitlines():
        st, path = line.split("\t", 1)
        if path.startswith(".orchestra/"):
            continue
        if st.startswith("A"):
            (root / path).unlink()
            added.append(path)
        else:
            g(root, "checkout", "-q", f"{sha}^", "--", path)
            if st.startswith("D"):
                deleted.append(path)
    tasks = oc.load_registry(root, "task")
    req_of = pb.group_requests(tasks, {a["id"]: a for a in oc.load_registry(root, "artifact")})
    coder = [t for t in tasks if req_of[t["id"]] == req and oc.agent_for(t["owner"]) == "coder"]
    scope = sorted({s for t in coder for s in oc.as_list(t.get("write_scope"))})
    target = coder[-1]["id"]
    with open(root / ".orchestra/config.yaml", "a", encoding="utf-8") as f:
        f.write("\n" + oc.dump_yaml({"verify": VERIFY}))
    cp = ov.checkpoint_path(root, target)
    if cp.exists():
        cp.unlink()
    sha_cp = ov.make_checkpoint(root, target)
    with oc.journal_context(actor="phase2_replay", extra={"checkpoint": sha_cp}):
        oc.append_journal(root, [{"id": target, "from": "replay", "to": "dispatched"}])
    # thay đổi thật của yêu cầu
    g(root, "checkout", "-q", "-f", sha, "--", ".")
    for path in deleted:
        (root / path).unlink()
    g(app, "checkout", "-q", "-f", app_sha)
    res = ov.verify(root, target, scope_override=scope)
    orc_results = {r["kind"]: r["orc"] for r in res["compare"]}
    rows = []
    for t in coder:
        for r in ov.compare(root, t["id"], orc_results):
            rows.append({"request": req, "task": t["id"], **r})
    print(ov.render(res), file=sys.stderr)
    return [{"request": req, "commit": f"{sha}/{app_sha}", "target": target, "scope_files": len(scope),
             "outside": res["outside"], "secrets": res["secrets"], "risky": res["risky"],
             "runs": [(r["name"], r["result"], r.get("seconds"), r.get("counts")) for r in res["runs"]],
             "rows": rows}]


def render(results: list) -> str:
    out = ["# Phase 2 — phát lại yêu cầu thật với `orc verify`", "",
           "Sinh bởi `tools/phase2_replay.py` trên bản clone tạm (nguồn chỉ đọc).", "",
           "## Kết quả orc theo yêu cầu", "",
           "| Yêu cầu | Commit (gốc/app) | Lệnh (kết quả, giây, số test) | Ngoài write_scope | Nghi bí mật | Risk path |",
           "|---|---|---|---|---|---|"]
    for r in results:
        runs = "; ".join(f"{n} {res} {s}s {c or ''}" for n, res, s, c in r["runs"])
        out.append(f"| {r['request']} | {r['commit']} | {runs} | {', '.join(r['outside']) or '0'} "
                   f"| {len(r['secrets'])} | {', '.join(r['risky']) or '-'} |")
    out += ["", "## So với EVD tự khai (từng task coder)", "",
            "| Yêu cầu | Task | Kind | orc | Tự khai pass | Tự khai khác | Kết luận |", "|---|---|---|---|---|---|---|"]
    lech = 0
    for r in results:
        for x in r["rows"]:
            lech += x["verdict"] == "LỆCH"
            out.append(f"| {x['request']} | {x['task']} | {x['kind']} | {x['orc']} | {len(x['agent_pass'])} "
                       f"| {len(x['agent_other'])} | {x['verdict']} |")
    out += ["", f"**LỆCH (tự khai pass, orc fail): {lech}**", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--app-repo", default="app")
    ap.add_argument("--work", required=True)
    ap.add_argument("--request", nargs="+", required=True)
    a = ap.parse_args(argv)
    root = prepare(Path(a.project), a.app_repo, Path(a.work))
    results = []
    for spec in a.request:
        req, shas = spec.split("=", 1)
        sha, app_sha = shas.split(":", 1)
        results += replay(root, a.app_repo, req, sha, app_sha)
    sys.stdout.write(render(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
