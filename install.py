"""Cài orchestra-kit vào Claude Code của máy này. Chạy lại được nhiều lần.

    python install.py                 # cài thật vào ~/.claude
    python install.py --dry-run       # chỉ in ra sẽ làm gì
    python install.py --claude-dir D  # cài vào thư mục khác (dùng cho test)

Làm 3 việc:
1. Liên kết ~/.claude/agents và ~/.claude/commands tới thư mục của kit.
   Windows: junction (máy không cho tạo symlink — Dung chốt Q1); nơi khác: symlink.
   Không đụng vào thư mục đã có sẵn mà không phải liên kết tới kit.
2. Thêm hook SessionStart và Stop vào settings.json (giữ cấu hình cũ, sao lưu trước khi ghi).
3. Thêm <kit>/cli vào PATH của user (Windows) để gọi được `orc`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
MARK = "orchestra-kit/hooks/"


def posix(p: Path) -> str:
    return str(p).replace("\\", "/")


def link_target(p: Path):
    """Đích của symlink/junction, hoặc None nếu p không phải liên kết."""
    try:
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            raw = os.readlink(p)
            if raw.startswith("\\\\?\\"):  # junction trên Windows: \\?\C:\...
                raw = raw[4:]
            return Path(raw).resolve()
    except OSError:
        return None
    return None


def ensure_link(link: Path, target: Path, dry: bool) -> str:
    current = link_target(link)
    if current is not None:
        if current == target.resolve():
            return f"đã có liên kết {link} → {target}"
        raise SystemExit(f"{link} đang trỏ tới {current}, không phải kit. Dừng, không sửa.")
    if link.exists():
        raise SystemExit(f"{link} đã tồn tại và không phải liên kết. Dừng, không sửa. "
                         f"Chuyển nội dung đi rồi chạy lại.")
    if dry:
        return f"[dry-run] sẽ tạo liên kết {link} → {target}"
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True,
                       capture_output=True)
        return f"tạo junction {link} → {target}"
    os.symlink(target, link, target_is_directory=True)
    return f"tạo symlink {link} → {target}"


def hook_entry(python: str, name: str) -> dict:
    return {"hooks": [{"type": "command",
                       "command": f'"{posix(Path(python))}" "{posix(KIT / "hooks" / name)}"',
                       "timeout": 30}]}


def merge_hooks(settings: dict, python: str) -> dict:
    hooks = settings.setdefault("hooks", {})
    for event, name in (("SessionStart", "session_start"), ("Stop", "stop_check")):
        groups = [g for g in hooks.get(event, [])
                  if not any(MARK in str(h.get("command", "")) for h in g.get("hooks", []))]
        groups.append(hook_entry(python, name))
        hooks[event] = groups
    return settings


def install_hooks(claude_dir: Path, python: str, dry: bool) -> str:
    path = claude_dir / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    merged = merge_hooks(settings, python)
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if dry:
        return f"[dry-run] settings.json sẽ thành:\n{text}"
    if path.exists():
        backup = path.with_name(f"settings.json.bak-orchestra-{dt.datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return f"ghi hook SessionStart + Stop vào {path}"


def add_to_path(dry: bool) -> str:
    cli = str(KIT / "cli")
    if os.name != "nt":
        return f"Thêm vào PATH thủ công: export PATH=\"{cli}:$PATH\""
    import winreg  # noqa: PLC0415
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        parts = [p for p in value.split(";") if p]
        if any(os.path.normcase(p.rstrip("\\/")) == os.path.normcase(cli) for p in parts):
            return f"PATH đã có {cli}"
        if dry:
            return f"[dry-run] sẽ thêm {cli} vào PATH của user"
        winreg.SetValueEx(key, "Path", 0, kind, ";".join(parts + [cli]))
    return f"thêm {cli} vào PATH của user (mở lại VS Code/terminal để có hiệu lực)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cài orchestra-kit")
    ap.add_argument("--claude-dir", default=str(Path.home() / ".claude"))
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-path", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        import yaml  # noqa: F401, PLC0415
    except ImportError:
        print("Thiếu PyYAML: python -m pip install --user pyyaml")
        return 1
    claude_dir = Path(a.claude_dir)
    for name in ("agents", "commands"):
        print(ensure_link(claude_dir / name, KIT / name, a.dry_run))
    print(install_hooks(claude_dir, a.python, a.dry_run))
    if not a.no_path:
        print(add_to_path(a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
