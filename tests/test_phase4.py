"""Phase 4: FINDING-6 (guard Bash tin cậy cao), H7 (LLM chỉ propose DEC), F2 (journal rejected), F3 (khớp đường
dẫn kiểu gitignore), F4 (ENVIRONMENT_FAILURE), F5 (rollback v0.2 → 0.1.0), Agent/SubagentHandback."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "cli"))
sys.path.insert(0, str(KIT / "tools"))
import orc_approval as oa  # noqa: E402
import orc_core as oc  # noqa: E402
import orc_guard as og  # noqa: E402
import orc_verify as ov  # noqa: E402

PY = sys.executable


def cli(root, *args, stdin=None, env=None):
    r = subprocess.run([PY, str(KIT / "cli" / "orc"), "-C", str(root), *args], capture_output=True, env=env,
                       input=stdin.encode("utf-8") if stdin else None)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def say(root, text):
    og.log_prompt({"cwd": str(root), "session_id": "dung", "prompt": text})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        oc.cmd_init(self.root, "p", "g")

    def tearDown(self):
        self.tmp.cleanup()

    def journal(self):
        p = oc.journal_path(self.root)
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


# ---------------------------------------------------------------- F3

class TestPathMatching(unittest.TestCase):
    CASES = [
        ("app/src/a.ts", ["app/src/"], True),
        ("app/src/x/y.ts", ["app/src/"], True),
        ("app/srcx/a.ts", ["app/src/"], False),
        ("app/src/a.ts", ["app/src"], True),            # không glob: file hoặc thư mục cùng tên
        ("app/src", ["app/src/"], True),
        ("docs/a.md", ["docs/*.md"], True),
        ("docs/x/a.md", ["docs/*.md"], False),          # FINDING-3: `*` không qua `/`
        ("app/scripts/seed-carriers.ts", ["app/scripts/seed-carriers.*"], True),
        ("app/scripts/seed-carriers.x/y/z.ts", ["app/scripts/seed-carriers.*"], True),  # thư mục khớp ⇒ con
        ("supabase/migrations/2026_carriers_a.sql", ["supabase/migrations/2026*_carriers_*.sql"], True),
        ("supabase/migrations/sub/2026_carriers_a.sql", ["supabase/migrations/2026*_carriers_*.sql"], False),
        ("app/tests/a.test.ts", ["app/tests/**"], True),
        ("app/tests/x/a.test.ts", ["app/tests/**"], True),
        ("app/package.json", ["**/package.json"], True),
        ("package.json", ["**/package.json"], True),     # `**/` gồm cả gốc
        ("a/b/c/package.json", ["**/package.json"], True),
        ("x/node_modules/", ["**/node_modules/"], True),
        ("README.md", ["*.md"], True),
        ("docs/README.md", ["*.md"], False),            # neo ở gốc dự án (khác gitignore)
        ("./app/a.ts", ["app/"], True),
        ("app\\src\\a.ts", ["app/src/"], True),
        ("app/a.ts", [], False),
    ]

    def test_table(self):
        for path, pats, want in self.CASES:
            with self.subTest(path=path, pats=pats):
                self.assertEqual(og.match_path(path, pats), want)

    def test_apply_uses_new_semantics(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            oc.cmd_init(r, "p", "g")
            t = oc.new_task(r, title="x", owner="coder", write_scope=["docs/*.md"])["id"]
            oc.advance(r, t, "dispatched")
            with self.assertRaises(oc.OrcError):
                oc.apply_envelope(r, oc.parse_envelope(
                    f"msg: result\ntask_id: {t}\nstatus: done\noutputs: [docs/sub/a.md]\nsummary: x\n"))


# ---------------------------------------------------------------- FINDING-6 + Agent/SubagentHandback

class TestGuardFinding6(Base):
    def active(self, writable=(), protected=()):
        return {"tasks": [{"id": "TASK-0001", "status": "dispatched", "owner": "coder",
                           "write_scope": ["app/src/"], "artifacts": []}],
                "writable": list(writable), "protected": list(protected)}

    def d(self, tool, ti, active=None, **kw):
        return og.decide(self.root, active or self.active(), tool, ti, safe=False, **kw)[0]

    def test_phase3_false_positives_now_allowed(self):
        allow = [
            "cat > supabase/migrations/x.sql <<'EOF'\n-- chạy supabase db push sau khi duyệt\nselect 1;\nEOF",
            "echo \"$(cat <<'YAML'\nmsg: result\nsummary: \"a; b | c && d\"\nYAML\n)\" | orc apply -",
            "cd /d/WMS/app && grep -n \"updatePick\\|deletePick\" src/a.ts | head",
            "cd /d/WMS/app && (npm run build 2>&1 | tail -8; npm run test 2>&1 | tail -15)",
            "sed -n 52p src/shared/inventory/repo.ts | cut -c120-230",
            "git check-ignore -v app/src/a.ts",
            "orc new decision --summary \"Dung chốt: Q1; Q2 | Q3\"",
            "python - <<'EOF'\nopen('app/src/a.ts','w').write('x > y; rm -rf z')\nEOF",
            "npm run lint 2>&1 | grep -E \"error|Found\"",
            "git commit -m \"không push --force; xoá .orchestra/state\"",
        ]
        for cmd in allow:
            with self.subTest(cmd=cmd[:50]):
                self.assertEqual(self.d("Bash", {"command": cmd}), "allow")

    def test_high_confidence_denies(self):
        deny = ["git push", "git -C app push origin main", "git push --force-with-lease", "git merge feature",
                "git rebase main", "git reset --hard HEAD~1", "git -C app reset HEAD --hard", "git clean -fd",
                "git branch -D x", "supabase db push", "supabase db reset", "supabase functions deploy f",
                "supabase secrets set A=1", "npm publish", "firebase deploy", "vercel --prod",
                "gh release create v1", "rm -rf app", "rm -r x", "Remove-Item -Recurse app", "rmdir /s x",
                "find . -name '*.tmp' -delete", "psql -h db.example.com -c 'select 1'",
                "echo x > .orchestra/state/tasks.yaml", "echo x >> .orchestra/runtime/prompts.jsonl",
                "sed -i s/a/b/ .orchestra/config.yaml", "cp hook .git/hooks/pre-commit",
                "cp x app/.git/config", "echo x | tee .claude/settings.json",
                f"echo x > {(Path.home() / '.claude' / 'settings.json').as_posix()}", "echo x > ~/.claude/settings.json",
                "cat app/.env.local", "cp .env.example .env", "echo k > keys/server.pem",
                "mv x .orchestra/decisions/DEC-0001.md", "Set-Content -Path .orchestra/state/tasks.yaml -Value x"]
        for cmd in deny:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.d("Bash", {"command": cmd}), "deny")
        self.assertEqual(self.d("Bash", {"command": "psql -h localhost -c 'select 1'"}), "allow")
        self.assertEqual(self.d("Bash", {"command": "cat .orchestra/state/tasks.yaml"}), "allow")  # đọc được
        self.assertEqual(self.d("Bash", {"command": "cat .env.example"}), "allow")

    def test_own_artifact_writable_via_bash_and_edit(self):
        art = ".orchestra/artifacts/ART-0033.md"
        a = self.active(writable=[art])
        self.assertEqual(self.d("Bash", {"command": f"cat >> {art} <<'EOF'\nPASS\nEOF"}, a), "allow")
        self.assertEqual(self.d("Edit", {"file_path": art}, a), "allow")
        self.assertEqual(self.d("Edit", {"file_path": ".orchestra/artifacts/ART-0099.md"}, a), "deny")
        self.assertEqual(self.d("Bash", {"command": "cat >> .orchestra/artifacts/ART-0099.md"}, a), "deny")

    def test_edit_write_deny_always_and_scope(self):
        for f in (".orchestra/config.yaml", ".orchestra/state/tasks.yaml", ".orchestra/knowledge/K.md", ".git/config",
                  "app/.git/HEAD", ".claude/settings.json", str(Path.home() / ".claude" / "agents" / "x.md"),
                  "app/.env.local", "certs/a.key"):
            with self.subTest(f=f):
                self.assertEqual(self.d("Write", {"file_path": f}), "deny")
        self.assertEqual(self.d("Edit", {"file_path": "app/src/a.ts"}), "allow")
        self.assertEqual(self.d("Edit", {"file_path": "app/package.json"}), "deny")       # ngoài write_scope
        self.assertEqual(self.d("Write", {"file_path": str(Path(tempfile.gettempdir()) / "ed.py")}), "allow")
        a = self.active(protected=["config/prod.yaml"])
        self.assertEqual(self.d("Edit", {"file_path": "config/prod.yaml"}, a), "deny")

    def test_read_secrets(self):
        self.assertEqual(self.d("Read", {"file_path": str(self.root / "app/.env.local")}), "deny")
        self.assertEqual(self.d("Read", {"file_path": "app/.env.example"}), "allow")
        self.assertEqual(self.d("Grep", {"pattern": "x", "path": ".env"}), "deny")
        self.assertEqual(self.d("Read", {"file_path": "app/src/a.ts"}), "allow")

    def test_agent_tools_in_matrix(self):
        for tool in ("Agent", "SubagentHandback", "Task", "SendMessage"):
            with self.subTest(tool=tool):
                dec, reason, _ = og.decide(self.root, self.active(), tool, {"subagent_type": "coder"}, safe=False)
                self.assertEqual((dec, reason), ("allow", "tool không ghi file"))
        dec, reason, _ = og.decide(self.root, self.active(), "NewFancyTool", {}, safe=False)
        self.assertEqual(dec, "allow")
        self.assertIn("tool chưa phân loại", reason)

    def test_replay_real_shadow_log(self):
        import phase4_guard_replay as rp  # noqa: PLC0415
        log = KIT / "docs/phases/shadow-raw/guard-shadow.jsonl"
        res = rp.replay(log, self.root, {"883fcd3d-e75a-4804-8432-b3215e4b5a8c", "smoke-test"})
        self.assertEqual((res["total"], res["replayed"], res["old_deny"]), (511, 383, 109))
        # Còn đúng 1: lệnh trong log bị cắt ở 200 ký tự giữa đường dẫn `.orchestra/cont…` (file CTX được phép)
        self.assertEqual(len(res["new_deny"]), 1)
        self.assertEqual(res["new_deny"][0]["reason"], "deny_always: ghi .orchestra/cont")

    def test_active_json_writable(self):
        t = oc.new_task(self.root, title="r", owner="researcher")["id"]
        art = oc.new_artifact(self.root, "research", t)["id"]
        sid = oc.handoff_open(self.root, "orchestrator")
        oc.write_active(self.root)
        act = og.load_active(self.root)
        self.assertIn(f".orchestra/artifacts/{art}.md", act["writable"])
        self.assertIn(f".orchestra/sessions/{sid}.md", act["writable"])


# ---------------------------------------------------------------- H7

class TestDecisionAuthority(Base):
    def test_cli_paths_cannot_accept(self):
        code, _, err = cli(self.root, "new", "decision", "--summary", "x", "--status", "accepted")
        self.assertEqual(code, 1)
        self.assertIn("H7", err)
        self.assertEqual(cli(self.root, "new", "decision", "--summary", "x", "--status", "superseded")[0], 1)
        d = cli(self.root, "new", "decision", "--summary", "đề xuất")[1].strip()
        self.assertEqual(oc.find_entry(self.root, d)[2]["status"], "proposed")
        self.assertEqual(cli(self.root, "advance", d, "--to", "accepted")[0], 1)
        self.assertEqual(cli(self.root, "set", d, "status=accepted")[0], 1)
        t = oc.new_task(self.root, title="r", owner="researcher")["id"]
        und = oc.new_artifact(self.root, "research", t)["id"]
        self.assertEqual(cli(self.root, "advance", und, "--to", "accepted")[0], 1)
        oc.advance(self.root, t, "dispatched")
        oc.apply_envelope(self.root, oc.parse_envelope(
            f"msg: result\ntask_id: {t}\nstatus: done\nproposed_decisions: [{{summary: s, supersedes: {d}}}]\n"
            "summary: x\n"))
        self.assertTrue(all(x["status"] == "proposed" for x in oc.load_registry(self.root, "decision")))

    def test_accepted_dec_content_locked(self):
        d = oc.new_decision(self.root, "cũ", status="accepted")["id"]  # dữ liệu cũ / API nội bộ
        self.assertEqual(cli(self.root, "set", d, "summary=đổi lén")[0], 1)
        self.assertEqual(cli(self.root, "set", d, "scope=khác")[0], 1)

    def test_approval_flow_multi_ids(self):
        old = oc.new_decision(self.root, "cũ", status="accepted")["id"]
        t = oc.new_task(self.root, title="r", owner="researcher")["id"]
        und = oc.new_artifact(self.root, "research", t)["id"]
        d1 = oc.new_decision(self.root, "Q1: A", scope=und)["id"]
        d2 = oc.new_decision(self.root, "Q2: B", scope=und, supersedes=old)["id"]
        code, out, err = cli(self.root, "approval", "request", und, d1, d2)
        self.assertEqual(code, 0, err)
        line = next(l.strip() for l in out.splitlines() if l.strip().startswith("orc:approve"))
        self.assertTrue(line.startswith(f"orc:approve {und},{d1},{d2} "))
        self.assertEqual(cli(self.root, "approve", und, d1, d2)[0], 1)   # chưa có lời Dung
        say(self.root, f"Đồng ý\n{line}")
        code, out, err = cli(self.root, "approve", und, d1, d2)
        self.assertEqual(code, 0, err)
        st = {e["id"]: e["status"] for e in oc.load_registry(self.root, "decision")}
        self.assertEqual((st[d1], st[d2], st[old]), ("accepted", "accepted", "superseded"))
        self.assertEqual(oc.find_entry(self.root, und)[2]["status"], "accepted")
        self.assertEqual(oc.validate(self.root), [])

    def test_changed_dec_after_request_refused(self):
        d = oc.new_decision(self.root, "Q1: A")["id"]
        out = oa.request(self.root, [d])
        oc.set_fields(self.root, d, {"summary": "Q1: B (sửa sau khi xin duyệt)"})
        say(self.root, next(l.strip() for l in out.splitlines() if "orc:approve" in l))
        with self.assertRaises(oc.OrcError):
            oa.approve(self.root, [d])
        self.assertEqual(oc.find_entry(self.root, d)[2]["status"], "proposed")


# ---------------------------------------------------------------- F2

class TestJournalRejected(Base):
    def test_rejections_logged_semantics_unchanged(self):
        t = cli(self.root, "new", "task", "--title", "x")[1].strip()
        before = oc.journal_path(self.root).read_text(encoding="utf-8")
        code, out, err = cli(self.root, "set", t, "status=done")
        self.assertEqual(code, 1)
        self.assertIn("orc set", err)
        row = self.journal()[-1]
        self.assertEqual((row["event"], row["task"], row["operation"], row["actor"]),
                         ("rejected", t, "set", "orc set"))
        self.assertIn("orc advance", row["reason"])
        self.assertEqual(len(row["reason_hash"]), 16)
        self.assertTrue(oc.journal_path(self.root).read_text(encoding="utf-8").startswith(before))  # giữ journal cũ
        code, _, _ = cli(self.root, "apply", "-", stdin=f"msg: result\ntask_id: {t}\nstatus: done\nsummary: x\n")
        self.assertEqual(code, 1)  # task chưa dispatched
        self.assertEqual((self.journal()[-1]["task"], self.journal()[-1]["operation"]), (t, "apply"))
        self.assertEqual(cli(self.root, "new", "decision", "--summary", "x", "--status", "accepted")[0], 1)
        self.assertEqual(self.journal()[-1]["operation"], "new decision")
        n = len(self.journal())
        self.assertEqual(cli(self.root, "show", t)[0], 0)
        self.assertEqual(cli(self.root, "show", "TASK-0099")[0], 1)  # lệnh đọc lỗi: không ghi journal
        self.assertEqual(len(self.journal()), n)
        code, out, _ = cli(self.root, "validate")
        self.assertEqual((code, out.strip()), (0, "OK"))

    def test_safe_mode_does_not_write(self):
        n = len(self.journal())
        env = {**os.environ, "ORC_SAFE_MODE": "1"}
        self.assertEqual(cli(self.root, "new", "task", "--title", "x", env=env)[0], 1)
        self.assertEqual(len(self.journal()), n)


# ---------------------------------------------------------------- F4

class TestEnvironmentFailure(Base):
    def setUp(self):
        super().setUp()
        r = self.root
        py = Path(PY).as_posix()
        (r / "env.py").write_text("print('Error: An Application Control policy has blocked this file.')\n"
                                  "raise SystemExit(1)\n", encoding="utf-8")
        (r / "bad.py").write_text("print('# fail 2'); raise SystemExit(1)\n", encoding="utf-8")
        with open(r / ".orchestra/config.yaml", "a", encoding="utf-8") as f:
            f.write(f"verify:\n  commands:\n    lint: '\"{py}\" env.py'\n    test: '\"{py}\" bad.py'\n")
        git(r, "init", "-q")
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", "i")
        self.t = oc.new_task(r, title="c", owner="coder", write_scope=["src/"])["id"]
        oc.advance(r, self.t, "dispatched")

    def test_classify(self):
        self.assertEqual(ov.classify("lint", 1, False, "An Application Control policy has blocked this file")[0], "env")
        self.assertEqual(ov.classify("lint", 1, False, "Cannot find native binding")[0], "env")
        self.assertEqual(ov.classify("build", 127, False, "")[:2], ("env", "ENVIRONMENT_FAILURE"))
        self.assertEqual(ov.classify("test", 1, False, "# fail 2")[:2], ("fail", "TEST_FAILURE"))
        self.assertEqual(ov.classify("lint", 1, False, "1 error")[:2], ("fail", "LINT_FAILURE"))
        self.assertEqual(ov.classify("test", None, True, "")[:2], ("fail", "TEST_FAILURE"))  # timeout ≠ môi trường
        self.assertEqual(ov.classify("test", 0, False, "")[0], "pass")

    def test_verify_separates_env_from_project_failure(self):
        oc.apply_envelope(self.root, oc.parse_envelope(
            f"msg: result\ntask_id: {self.t}\nstatus: done\n"
            "evidence: [{kind: lint, result: pass, summary: lint ok}, {kind: test, result: pass, summary: t ok}]\n"
            "summary: x\n"))
        code, out, _ = cli(self.root, "verify", self.t)
        self.assertEqual(code, 6, out)  # test fail thật ⇒ FAIL
        self.assertIn("- lint: orc env | tự khai pass ['EVD-0001'] | không kiểm được (ENVIRONMENT_FAILURE)", out)
        self.assertIn("- test: orc fail | tự khai pass ['EVD-0002'] | LỆCH", out)
        self.assertIn("ENVIRONMENT_FAILURE lint: Windows Application Control chặn", out)
        lint = next(e for e in oc.load_registry(self.root, "evidence") if e["by"] == "orc" and e["kind"] == "lint")
        self.assertEqual(lint["result"], "info")
        self.assertTrue(lint["summary"].startswith("orc verify lint: ENVIRONMENT_FAILURE"))

    def test_only_env_is_incomplete(self):
        cfg = self.root / ".orchestra/config.yaml"
        oc.write_text(cfg, oc.read_text(cfg).replace("bad.py", "env.py"))
        t = oc.new_task(self.root, title="c2", owner="coder", write_scope=["src/"])["id"]
        oc.advance(self.root, t, "dispatched")
        code, out, _ = cli(self.root, "verify", t)
        self.assertEqual(code, 7, out)
        self.assertIn(f"VERIFY {t}: INCOMPLETE", out)


# ---------------------------------------------------------------- F5

class TestRollback(Base):
    def setUp(self):
        super().setUp()
        self.v01 = Path(self.tmp.name + "-v01")
        zp = Path(self.tmp.name + "-v01.zip")
        subprocess.run(["git", "-C", str(KIT), "archive", "--format=zip", "-o", str(zp), "main",
                        "cli", "templates", "VERSION"], check=True, capture_output=True)
        with zipfile.ZipFile(zp) as z:
            z.extractall(self.v01)
        zp.unlink()
        r = self.root
        t = oc.new_task(r, title="c", owner="coder", write_scope=["src/"])["id"]
        items = oc.load_registry(r, "task")
        items[0].update(level=2, risk_flags=["migration"])
        oc.save_registry(r, "task", items)
        oc.new_evidence(r, t, "orc verify scope ok", kind="scope", result="pass", by="orc")
        oc.new_evidence(r, t, "tự khai", kind="test", result="pass")
        d = oc.new_decision(r, "Q1")["id"]
        oa.request(r, [d])
        git(r, "init", "-q")
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", "v0.2")

    def tearDown(self):
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.v01, ignore_errors=True)
        super().tearDown()

    def rb(self, *extra):
        r = subprocess.run([PY, str(KIT / "tools/rollback_v02_to_v01.py"), "--project", str(self.root),
                            "--v01-kit", str(self.v01), *extra], capture_output=True)
        return r.returncode, r.stdout.decode("utf-8") + r.stderr.decode("utf-8")

    def v01_validate(self):
        r = subprocess.run([PY, str(self.v01 / "cli/orc"), "-C", str(self.root), "validate"], capture_output=True)
        return r.returncode, r.stdout.decode("utf-8")

    def test_v01_rejects_v02_data_then_rollback_fixes(self):
        code, out = self.v01_validate()
        self.assertEqual(code, 1)
        self.assertIn("trường lạ", out)
        before = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True).stdout
        code, out = self.rb()
        self.assertEqual(code, 0, out)
        self.assertIn("validate 0.1.0 trên bản sao: OK", out)
        self.assertEqual(subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"],
                                        capture_output=True).stdout, before)  # dry-run không ghi
        code, out = self.rb("--apply")
        self.assertEqual(code, 0, out)
        code, out = self.v01_validate()
        self.assertEqual((code, out.strip()), (0, "OK"))
        backups = list((self.root / ".orchestra").glob("rollback-v0.2-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "v02-only" / "journal.jsonl").is_file())
        self.assertTrue((backups[0] / "v02-only" / "approvals.yaml").is_file())
        ev = {e["summary"]: e for e in oc.load_registry(self.root, "evidence")}
        self.assertEqual(ev["[v0.2 scope] orc verify scope ok"]["kind"], "other")

    def test_apply_refused_when_orchestra_dirty(self):
        (self.root / ".orchestra/knowledge/KNOWLEDGE_MAP.md").write_text("đổi chưa commit", encoding="utf-8")
        code, out = self.rb("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("chưa commit", out)
        self.assertEqual(self.v01_validate()[0], 1)  # không ghi gì

    def test_refuses_v02_kit_as_v01(self):
        r = subprocess.run([PY, str(KIT / "tools/rollback_v02_to_v01.py"), "--project", str(self.root),
                            "--v01-kit", str(KIT)], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("không phải kit 0.1.0", r.stdout.decode("utf-8") + r.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
