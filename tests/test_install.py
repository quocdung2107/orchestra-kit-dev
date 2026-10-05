"""Test bộ cài trên thư mục ~/.claude giả (không đụng máy thật)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent


def install(claude_dir):
    return subprocess.run([sys.executable, str(KIT / "install.py"), "--claude-dir",
                           str(claude_dir), "--no-path"], capture_output=True, text=True,
                          encoding="utf-8")


class TestInstall(unittest.TestCase):
    def test_install_is_idempotent_and_keeps_settings(self):
        with tempfile.TemporaryDirectory() as d:
            cd = Path(d)
            (cd / "settings.json").write_text(json.dumps({
                "model": "sonnet",
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo khác"}]}]},
            }), encoding="utf-8")
            for _ in range(2):
                r = install(cd)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            s = json.loads((cd / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(s["model"], "sonnet")
            self.assertEqual(len(s["hooks"]["SessionStart"]), 1)
            self.assertEqual(len(s["hooks"]["Stop"]), 2)  # hook cũ + hook kit
            self.assertIn("stop_check", s["hooks"]["Stop"][1]["hooks"][0]["command"])
            self.assertTrue((cd / "agents" / "coder.md").is_file())
            self.assertTrue((cd / "commands" / "plan.md").is_file())
            self.assertTrue(list(cd.glob("settings.json.bak-orchestra-*")))

    def test_refuses_existing_real_dir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "agents").mkdir()
            (Path(d) / "agents" / "mine.md").write_text("x", encoding="utf-8")
            r = install(d)
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue((Path(d) / "agents" / "mine.md").is_file())


if __name__ == "__main__":
    unittest.main()
