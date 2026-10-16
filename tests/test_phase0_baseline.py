"""Phase 0: script đo baseline đọc dữ liệu thật, gom yêu cầu đúng, không ghi gì vào dự án."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT = REPO / "plugins" / "orchestra"  # gốc plugin (cli/, hooks/, templates/…)
sys.path.insert(0, str(KIT / "cli"))
sys.path.insert(0, str(REPO / "tools"))
import orc_core as oc  # noqa: E402
import phase0_baseline as pb  # noqa: E402


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if ".git" in p.relative_to(root).parts:
            continue
        h.update(p.relative_to(root).as_posix().encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class TestPhase0Baseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        oc.cmd_init(self.root, "p", "goal")
        r = self.root
        # Yêu cầu 1: research → plan → 1 coder task (review trả lại 1 lần)
        t1 = oc.new_task(r, title="Yêu cầu A", owner="researcher")["id"]
        und = oc.new_artifact(r, "research", t1)["id"]
        oc.new_decision(r, "Dung chốt X", scope=und, status="accepted")
        t2 = oc.new_task(r, title="Plan A", owner="researcher", inputs=[und])["id"]
        plan = oc.new_artifact(r, "plan", t2)["id"]
        oc.set_fields(r, plan, {"status": "accepted"})
        t3 = oc.new_task(r, title="Code A", owner="coder", inputs=[plan],
                         write_scope=["src/a.py"])["id"]
        oc.set_fields(r, t3, {"status": "dispatched"})
        oc.apply_envelope(r, oc.parse_envelope(
            f"msg: result\ntask_id: {t3}\nstatus: done\noutputs: [src/a.py]\n"
            "evidence: [{kind: test, result: pass, summary: 'tự khai'}]\nsummary: x\n"))
        oc.apply_envelope(r, oc.parse_envelope(
            f"msg: result\ntask_id: {t3}\nstatus: failed\nfailure_class: IMPL_BUG\nsummary: y\n"))
        # Yêu cầu 2: độc lập
        self.t4 = oc.new_task(r, title="Yêu cầu B", owner="researcher")["id"]
        self.t1, self.t3 = t1, t3
        # git: commit nhắc dạng khoảng TASK-0001..0003, có 1 file ngoài scope
        (r / "src").mkdir()
        (r / "src" / "a.py").write_text("a", encoding="utf-8")
        (r / "src" / "b.py").write_text("b", encoding="utf-8")
        git(r, "init", "-q")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m",
            "làm TASK-0001..0003")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ids_in_expands_ranges(self):
        self.assertEqual(pb.ids_in("x TASK-0006..0008, ART-0001 S-0002"),
                         {"TASK-0006", "TASK-0007", "TASK-0008", "ART-0001", "S-0002"})

    def test_measure_groups_and_counts_without_writing(self):
        before = tree_hash(self.root)
        data = pb.measure(self.root, None, {})
        self.assertEqual(tree_hash(self.root), before, "script không được ghi vào dự án")
        rows = {r["root"]: r for r in data["rows"]}
        self.assertEqual(sorted(rows), [self.t1, self.t4])
        a = rows[self.t1]
        self.assertEqual((a["tasks"], a["coder_tasks"]), (3, 1))
        self.assertEqual((a["research_stops"], a["dung_decisions"]), (1, 1))
        self.assertEqual(a["attempts"], 1)
        self.assertEqual(a["failure_classes"], ["IMPL_BUG"])
        self.assertEqual((a["evd"], a["evd_pass"], a["evd_by_orc"]), (1, 1, 0))
        self.assertIn("src/b.py", a["files_outside_scope"])
        self.assertNotIn("src/a.py", a["files_outside_scope"])
        self.assertEqual(rows[self.t4]["commits"], [])
        self.assertEqual(pb.render(data), pb.render(pb.measure(self.root, None, {})))

    def test_map_attaches_commit_without_ids(self):
        r = self.root
        (r / "c.txt").write_text("c", encoding="utf-8")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "không có ID")
        sha = subprocess.run(["git", "-C", str(r), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        rows = {x["root"]: x for x in pb.measure(r, None, {self.t4: sha})["rows"]}
        self.assertEqual([c.split(":")[1] for c in rows[self.t4]["commits"]], [sha])


if __name__ == "__main__":
    unittest.main()
