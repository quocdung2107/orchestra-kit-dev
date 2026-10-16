"""Phase 5: orc triage (shadow) — bảng luật H2, module, đơn điệu, hạ mức bằng lời Dung, 3 lần trong vòng K."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT = REPO / "plugins" / "orchestra"  # gốc plugin (cli/, hooks/, templates/…)
sys.path.insert(0, str(KIT / "cli"))
sys.path.insert(0, str(REPO / "tests"))
import orc_core as oc  # noqa: E402
import orc_guard as og  # noqa: E402
import orc_triage as ot  # noqa: E402
from test_phase4b import Base as KBase  # noqa: E402

NO = {k: False for k in ot.FORM_KEYS}


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.cfg = {**ot.DEFAULTS, "l3": dict(ot.DEFAULTS["l3"]), "l2": dict(ot.DEFAULTS["l2"]),
                    "l0": dict(ot.DEFAULTS["l0"])}

    def lv(self, files, lines=None, form=None):
        return ot.classify(files, lines, form, self.cfg)[0]

    def test_rules(self):
        self.assertEqual(self.lv(["supabase/migrations/1.sql"], 3, NO), 3)            # risk path
        self.assertEqual(self.lv(["app/package.json"], 1, NO), 3)
        self.assertEqual(self.lv(["a/x.ts"], 1, {**NO, "schema_change": True}), 3)     # form L3
        self.assertEqual(self.lv([f"a/b/{i}.ts" for i in range(16)], 10, NO), 3)      # > 15 file
        self.assertEqual(self.lv(["a/b/x.ts"], 401, NO), 3)                            # > 400 dòng
        # Tổ hợp B (Dung chốt): > 3 module ⇒ L3 chỉ khi diff > 120 dòng; không thì luật L2 (> 1 module)
        self.assertEqual(self.lv(["a/1/x", "b/1/x", "c/1/x", "d/1/x"], 4, NO), 2)
        self.assertEqual(self.lv(["a/1/x", "b/1/x", "c/1/x", "d/1/x"], 121, NO), 3)
        self.assertEqual(self.lv(["a/1/x", "b/1/x", "c/1/x", "d/1/x"], None, NO), 2)  # lần 2 chưa biết dòng
        self.assertEqual(self.lv(["a/b/x.ts"], 1, {**NO, "user_visible": True}), 2)    # form L2
        self.assertEqual(self.lv(["a/1/x", "b/1/x"], 4, NO), 2)                        # > 1 module
        self.assertEqual(self.lv([f"a/b/{i}" for i in range(6)], 4, NO), 2)           # > 5 file
        self.assertEqual(self.lv(["a/b/x"], 121, NO), 2)                               # > 120 dòng
        self.assertEqual(self.lv(["a/b/x", "a/b/y", "a/b/z"], 30, NO), 1)             # 3 file 1 module
        self.assertEqual(self.lv(["a/b/x", "a/b/y"], 40, NO), 0)                       # L0 đủ điều kiện
        self.assertEqual(self.lv(["a/b/x", "a/b/y"], 41, NO), 1)                       # > 40 dòng ⇒ không L0

    def test_risk_keywords(self):
        lv = lambda text: ot.classify(["a/b/x", "a/b/y"], 10, NO, self.cfg, text=text)[0]  # noqa: E731
        self.assertEqual(lv("B1 chống CSV injection khi xuất CSV"), 3)
        self.assertEqual(lv("Sửa lỗi Đăng Nhập bằng OTP"), 3)          # tiếng Việt, không phân biệt hoa/thường
        self.assertEqual(lv("Thêm RLS cho bảng orders"), 3)
        self.assertEqual(lv("Dán {{ .Token }} vào template email"), 0)  # không có "token" trong danh sách
        self.assertEqual(lv("Sửa layout trang authors"), 0)             # ASCII khớp nguyên từ: authors ≠ auth
        self.assertEqual(lv("chặn file Excel > 20 MB"), 0)
        self.cfg["risk_keywords_l3"] = []
        self.assertEqual(lv("csv injection"), 0)                        # tắt được qua config

    def test_never_default_l0(self):
        self.assertEqual(self.lv(None, None, None), 1)              # không có gì
        self.assertEqual(self.lv(["a/b/x"], 3, None), 1)            # không có form
        self.assertEqual(self.lv(["a/b/x"], 3, {"user_visible": False}), 1)   # form khai thiếu cờ
        self.assertEqual(self.lv(None, None, NO), 1)                # form đủ nhưng không có đường dẫn

    def test_config_thresholds(self):
        self.cfg["l2"]["modules"] = 3
        self.assertEqual(self.lv(["a/1/x", "b/1/x"], 4, NO), 1)

    def test_module_of(self):
        self.assertEqual(ot.module_of("app/src/features/orders/Chat.tsx", ["app/src"]), "app/src/features/orders")
        self.assertEqual(ot.module_of("app/src/main.tsx", ["app/src"]), "app/src")
        self.assertEqual(ot.module_of("app/tests/a.test.ts", ["app/src"]), "app/tests")
        self.assertEqual(ot.module_of("README.md", []), ".")


class TestTriageCli(KBase):
    def test_monotonic_and_downgrade_needs_dung(self):
        R = self.ok("new", "request", "--title", "gốc")
        form = self.root / "form.yaml"
        form.write_text("schema_change: true\n", encoding="utf-8")
        self.assertIn("L3", self.ok("triage", "run", R, "--stage", "1", "--form", str(form)))
        form.write_text("".join(f"{k}: false\n" for k in ot.FORM_KEYS), encoding="utf-8")
        out = self.ok("triage", "run", R, "--stage", "1", "--form", str(form))
        self.assertIn("L3 (tính L1, trước L3)", out)  # chỉ tăng
        self.no("triage", "downgrade", R, "--to", "1", "--reason", "nhỏ")  # chưa có lời Dung
        self.say(f"orc:downgrade {R} L1 chỉ sửa chú thích")
        self.ok("triage", "downgrade", R, "--to", "1", "--reason", "chỉ sửa chú thích")
        self.assertIn(f"{R}: level 1", self.ok("triage", "show", R))
        self.assertIsNone(oc.find_entry(self.root, R)[2].get("level"))  # shadow: không ghi task.level
        out = self.ok("triage", "run", R, "--stage", "1", "--form", "-",
                      stdin="".join(f"{k}: false\n" for k in ot.FORM_KEYS))
        self.assertIn("lần 1", out)  # form qua stdin (dùng trong /auto)
        bad = self.root / "bad.yaml"
        bad.write_text("la: true\n", encoding="utf-8")
        self.no("triage", "run", R, "--stage", "1", "--form", str(bad))

    def test_three_stages_in_k_loop_shadow_only(self):
        R, UND, DEC, PLAN, C = self.to_planned()
        self.approve(R)  # vẫn bắt APPROVAL_REQUIRED: triage shadow không mở READY_FOR_IMPLEMENTATION
        self.implement(C)
        self.ok("advance", R, "--to", "VERIFYING")
        rows = [json.loads(l) for l in oc.journal_path(self.root).read_text(encoding="utf-8").splitlines()]
        tri = [r for r in rows if r.get("event") == "triage" and r.get("id") == R]
        self.assertEqual([r["stage"] for r in tri], [1, 2, 3])
        self.assertTrue(all(r["mode"] == "shadow" for r in tri))
        levels = [r["level"] for r in tri]
        self.assertEqual(levels, sorted(levels))  # đơn điệu
        self.assertEqual(tri[1]["files"], 1)      # write_scope app/ ⇒ file đang có trong git: app/status.txt
        self.assertGreaterEqual(tri[2]["files"], 1)
        self.assertIsNone(oc.find_entry(self.root, R)[2].get("level"))
        self.assertEqual(self.ok("validate"), "OK")


class TestReplayTool(unittest.TestCase):
    def test_replay_on_tiny_project_is_read_only(self):
        sys.path.insert(0, str(REPO / "tools"))
        import phase5_triage_replay as rp  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            oc.cmd_init(r, "p", "g")
            t = oc.new_task(r, title="Yêu cầu", owner="researcher")["id"]
            art = oc.new_artifact(r, "plan", t)["id"]
            c = oc.new_task(r, title="code", owner="coder", inputs=[art], write_scope=["src/"])["id"]
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "khởi tạo"]):
                subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                               capture_output=True)
            (r / "src").mkdir()
            (r / "src/a.py").write_text("a\n", encoding="utf-8")
            for args in (["add", "-A"], ["commit", "-q", "-m", f"{c} làm"]):
                subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                               capture_output=True)
            before = subprocess.run(["git", "-C", d, "status", "--porcelain"], capture_output=True).stdout
            rows = rp.replay(r, None, {}, [])
            self.assertEqual(subprocess.run(["git", "-C", d, "status", "--porcelain"], capture_output=True).stdout,
                             before)
            self.assertEqual((rows[0]["scope_files"], rows[0]["files3"], rows[0]["final"]), (1, 1, 1))
            self.assertIn("| L? |", rp.render(rows))
            self.assertEqual(og.match_path("src/a.py", ["src/"]), True)


if __name__ == "__main__":
    unittest.main()
