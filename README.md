# orchestra-kit

Bộ công cụ đa-agent dùng chung nhiều dự án cho Claude Code: CLI `orc`, 2 hook,
4 subagent, 5 lệnh. Thiết kế: [SCHEMA.md](SCHEMA.md).

## Cài dạng plugin (nhánh packaging, đang thử)

Repo này là marketplace `dung-kit`; plugin nằm ở `plugins/orchestra/`. Trong Claude Code:

```
/plugin install orchestra --marketplace quocdung2107/orchestra-kit
```

Repo private: máy cần đăng nhập git tới GitHub (vd `gh auth setup-git`). Lệnh của plugin có tiền tố
`/orchestra:` (vd `/orchestra:auto`), subagent là `orchestra:researcher`, `orchestra:coder`… Dự án đã bật
plugin thì hook toàn cục của kit cũ (từ rc-k-3) tự nhường, không chạy hai lần.

## Yêu cầu

- Python 3.10+ và PyYAML (`python -m pip install --user pyyaml`)
- git, Claude Code (CLI hoặc extension VS Code)

## Cài đặt (Windows, chạy một lần)

```powershell
cd $HOME\orchestra-kit
python -m unittest discover -s tests      # phải OK
python install.py --dry-run               # xem trước
python install.py
```

`install.py` làm 3 việc, chạy lại nhiều lần vẫn an toàn:

1. Tạo junction `~\.claude\agents` → `orchestra-kit\agents` và `~\.claude\commands` → `orchestra-kit\commands`
   (máy không cho tạo symlink nếu chưa bật Developer Mode). Dừng nếu hai thư mục đó đã có sẵn.
2. Sao lưu `~\.claude\settings.json` thành `settings.json.bak-orchestra-<giờ>` rồi thêm hook
   SessionStart + Stop, giữ nguyên cấu hình khác.
3. Thêm `orchestra-kit\cli` vào PATH của user để gọi `orc`.

Sau khi cài: **đóng và mở lại VS Code** để Claude Code nhận PATH, hook, agent, lệnh mới.

Kiểm tra:

```powershell
orc --help
```

Trong Claude Code: gõ `/` thấy `/plan /run /review /next /handoff`; gõ `/agents` thấy
`researcher, coder, reviewer, context-builder`.

## Dùng trong một dự án

```powershell
cd D:\du-an
orc init --project-id ten-du-an --goal "Mục tiêu một câu"
```

Mở phiên Claude Code mới trong dự án: brief tự nạp. Luồng: `/plan <yêu cầu>` → Dung duyệt plan →
`/run` → `/review <TASK>` → `/handoff`.

## Gỡ cài đặt

1. Khôi phục `~\.claude\settings.json` từ bản `.bak-orchestra-*`, hoặc xoá 2 mục hook có đường dẫn `orchestra-kit/hooks/`.
2. Xoá 2 junction: `cmd /c rmdir %USERPROFILE%\.claude\agents` và `...\commands` (`rmdir` chỉ xoá liên kết, không xoá file trong kit).
3. Bỏ `orchestra-kit\cli` khỏi PATH của user (Settings → Environment Variables).

Dùng hằng ngày: [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md).

## Phát triển kit

```powershell
python -m unittest discover -s tests -v
```
