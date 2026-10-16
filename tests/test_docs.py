"""Test `orc docs index|check` (docs/INDEX.md làm bản đồ truy xuất)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT = REPO / "plugins" / "orchestra"  # gốc plugin (cli/, hooks/, templates/…)
sys.path.insert(0, str(KIT / "cli"))

import orc_core as oc  # noqa: E402

FM = """---
status: {status}
feature: {feature}
updated: 2026-10-06
summary: "{summary}"
read_when: "Sửa {feature}"
supersedes: null
---
"""


def doc(root, rel, status="current", feature="routing", summary="Tóm tắt", body="# Tài liệu\n"):
    oc.write_text(root / rel, FM.format(status=status, feature=feature, summary=summary) + body)


class TestDocs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()  # dự án chưa có .orchestra vẫn dùng được
        oc.write_text(self.root / "docs/INDEX.md",
                      "# INDEX\n\n## Đọc gì khi…\n\n| Tình huống | Đọc |\n|---|---|\n| Routing | x |\n")
        doc(self.root, "docs/architecture/invariants.md", feature="core")
        doc(self.root, "docs/features/routing/plan.md", status="open")
        doc(self.root, "docs/archive/old.md", status="archived",
            body="Xem docs/plans-open/khong-con.md\n")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        r = subprocess.run([sys.executable, str(KIT / "cli" / "orc"), "-C", str(self.root), "docs", *args],
                           capture_output=True)
        return r.returncode, r.stdout.decode("utf-8")

    def test_index_keeps_handwritten_part_and_is_idempotent(self):
        oc.docs_index(self.root)
        first = (self.root / "docs/INDEX.md").read_text(encoding="utf-8")
        self.assertIn("| Routing | x |", first)
        self.assertIn("### architecture", first)
        self.assertIn("### features/routing", first)
        self.assertIn("[features/routing/plan.md](features/routing/plan.md) | open", first)
        self.assertLess(first.index("### features/routing"), first.index("### archive"))
        oc.docs_index(self.root)
        self.assertEqual(first, (self.root / "docs/INDEX.md").read_text(encoding="utf-8"))

    def test_check_ok_with_archive_broken_link_as_warning(self):
        oc.docs_index(self.root)
        errs, warns = oc.docs_check(self.root)
        self.assertEqual(errs, [])
        self.assertTrue(any("khong-con.md" in w for w in warns))
        code, out = self.cli("check")
        self.assertEqual(code, 0, out)

    def test_check_rejects_missing_frontmatter_and_unindexed(self):
        oc.docs_index(self.root)
        oc.write_text(self.root / "docs/audits/new.md", "# không frontmatter\n")
        errs, _ = oc.docs_check(self.root)
        self.assertTrue(any("new.md: thiếu frontmatter" in e for e in errs))
        self.assertTrue(any("new.md: chưa có trong docs/INDEX.md" in e for e in errs))
        self.assertEqual(self.cli("check")[0], 1)

    def test_check_rejects_bad_status_long_summary(self):
        doc(self.root, "docs/features/x/a.md", status="draft", summary="a" * 201)
        oc.docs_index(self.root)
        errs, _ = oc.docs_check(self.root)
        self.assertTrue(any("status 'draft'" in e for e in errs))
        self.assertTrue(any("summary > 200" in e for e in errs))

    def test_check_requires_superseded_inside_archive(self):
        doc(self.root, "docs/features/routing/cu.md", status="superseded")
        doc(self.root, "docs/archive/superseded/cu2.md", status="superseded")
        oc.docs_index(self.root)
        errs, _ = oc.docs_check(self.root)
        self.assertTrue(any("features/routing/cu.md: status superseded" in e for e in errs))
        self.assertFalse(any("cu2.md" in e for e in errs))

    def test_check_finds_broken_path_in_code_comment(self):
        oc.docs_index(self.root)
        oc.write_text(self.root / "backend/store.py", "# xem docs/plans-open/routing.md\nx = 1\n")
        oc.write_text(self.root / "node_modules/pkg/a.js", "// docs/khong/co.md\n")
        errs, _ = oc.docs_check(self.root)
        self.assertEqual([e for e in errs if "đường dẫn gãy" in e],
                         ["backend/store.py: đường dẫn gãy docs/plans-open/routing.md"])

    def test_index_cli_creates_section_when_markers_missing(self):
        code, out = self.cli("index")
        self.assertEqual(code, 0, out)
        text = (self.root / "docs/INDEX.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(oc.INDEX_START), 1)


if __name__ == "__main__":
    unittest.main()
