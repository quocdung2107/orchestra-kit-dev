# PHASE 2 — `orc verify` + kiểm phạm vi bằng git (H2, H3, H8)

Nguồn: v0.2 mục O (phase 2), J1 (V1, V2), N3, W8; ADJUSTMENTS #7 (môi trường thực thi), #8 (write scope
là mutation boundary + detection, không phải sandbox).

## Phạm vi

1. **Checkpoint** khi `orc advance <task coder> --to dispatched` lần đầu (dự án có mục `verify:`):
   `.orchestra/state/checkpoints/<TASK>.json` gồm HEAD từng repo, file bẩn/chưa track + sha256 lúc đó,
   danh sách `git status --ignored`, và **bản chụp mục `verify:` của config**. sha256 của file checkpoint
   ghi vào dòng journal của chuyển `→ dispatched` (sửa file checkpoint ⇒ verify từ chối).
2. **`orc verify TASK`** (không đổi trạng thái task — chạy song song với 0.1.0):
   - V2 scope: file đổi so với checkpoint (`git diff --name-only <head>` + file chưa track + mục ignored mới)
     ở mọi repo trong `verify.repos`, so với write_scope (ngữ nghĩa `_in_scope` cũ — FINDING-3);
     liệt kê file khớp `risk_paths`; quét bí mật đơn giản trên dòng thêm/file mới. → EVD `scope`.
   - Lệnh định nghĩa kiểm (`guard_paths`, mặc định `package.json`, lockfile) đổi kể từ checkpoint ⇒
     **không chạy lệnh**, EVD fail (lệnh cố định ≠ lệnh an toàn: script npm đổi được nội dung lệnh).
   - V1/V2 lệnh: `test, typecheck, lint, build` lấy từ **bản chụp tại checkpoint**, không từ config hiện tại.
     Môi trường (ADJUSTMENTS #7): env bỏ biến có tên chứa TOKEN/SECRET/KEY/PASSW/CREDENTIAL/AUTH/COOKIE/
     SESSION/PRIVATE; cwd cố định trong gốc dự án; timeout (mặc định 600 s) và giết cả cây tiến trình.
     Log đầy đủ ở `.orchestra/runtime/verify/` (gitignore); EVD lưu exit code, thời gian, sha256 log, số test.
   - EVD do orc tạo có `by: orc`; EVD từ envelope `by: agent` (mục cũ không có trường = agent).
     Envelope không được khai kind `scope|typecheck`.
   - In bảng so sánh EVD tự khai với kết quả orc (`LỆCH` khi tự khai pass mà orc fail).
3. `commands/review.md`, `auto.md`: chạy `orc verify <T>` trước reviewer; reviewer thấy EVD `by: orc` trong `--pack`.

Ngoài phạm vi: chặn DONE khi verify fail (state machine, Phase 4); guard PreToolUse (Phase 3); đổi ngữ nghĩa glob.

## Acceptance criteria

- AC-2.1: Lệnh kiểm đọc từ bản chụp checkpoint; sửa `config.yaml` sau checkpoint không đổi lệnh chạy;
  sửa file checkpoint ⇒ verify từ chối.
- AC-2.2: File đổi ngoài write_scope (tracked, untracked, ignored mới) ⇒ EVD scope fail liệt kê file;
  file bẩn từ trước checkpoint không bị tính nếu không đổi.
- AC-2.3: `package.json` đổi kể từ checkpoint ⇒ lệnh không chạy, EVD fail.
- AC-2.4: Env truyền cho lệnh không chứa biến có tên kiểu secret; cwd ngoài gốc bị từ chối; timeout giết lệnh.
- AC-2.5: EVD tự khai `pass` mà orc `fail` ⇒ báo `LỆCH`.
- AC-2.6 (cổng v0.2): phát lại 5 yêu cầu thật (commit thật của `D:\WMS`, `D:\WMS\app`) trên thư mục tạm:
  không có EVD tự khai nào sai mà không bị phát hiện.
- AC-2.7: Toàn bộ test xanh; 0.1.0 vẫn chạy khi dự án không có mục `verify:`.

## Cách test

- `tests/test_phase2.py`: repo git tạm, config `verify:` với lệnh Python nhỏ; các AC-2.1–2.5, 2.7.
- `tools/phase2_replay.py`: clone `D:\WMS` và `D:\WMS\app` vào thư mục tạm, đặt checkpoint = commit trước,
  checkout commit của yêu cầu, chạy `orc verify` thật (`npm run test/lint/build`), so với EVD tự khai trong
  registry. Không ghi vào `D:\WMS`.

## Kết quả

Code: `cli/orc_verify.py` (mới), `cli/orc_core.py` (checkpoint khi `advance → dispatched` task coder, lệnh
`orc verify`, EVD `by`, kind `typecheck|scope` chỉ orc tạo, `--pack` hiện `by`). `commands/review.md`,
`commands/auto.md`: chạy `orc verify` trước reviewer. `agents/reviewer.md`: đọc `by=orc` là bằng chứng.
`SCHEMA.md` §4, §8.

Thiết kế khoá: `orc verify` **không** giữ khoá state khi chạy lệnh (lệnh kiểm có thể vài phút); chỉ khoá lúc ghi EVD.

Phát lại 5 yêu cầu thật (`tools/phase2_replay.py`, bảng đầy đủ `docs/phases/PHASE-2-replay.md`):

| Kiểm | Kết quả orc | So với tự khai |
|---|---|---|
| test (`npm run test`) | pass cả 5; số test 8, 13, 20, 30, 30 — trùng số ghi trong EVD tự khai | khớp mọi dòng |
| build (`npm run build`) | pass cả 5 | khớp mọi dòng |
| scope (git so với write_scope) | 0 file ngoài write_scope ở cả 5 (trùng baseline Phase 0); risk_paths: 3 migration (TASK-0006), `app/.github/workflows/deploy.yml` (TASK-0023) | không có tự khai |
| lint (`npm run lint`) | fail cả 5 — **lỗi môi trường** (Application Control chặn binary oxlint) | 13 `LỆCH`, không lọt, nhưng không chứng minh tự khai sai (FINDING-4) |

Lần chạy đầu: quét bí mật báo nhầm 2 file vì chữ `service_role` trần (README hướng dẫn "không dùng
service_role", script seed đọc biến môi trường). Đã bỏ mẫu chữ trần; khoá thật là JWT, vẫn bị mẫu JWT bắt.
Chạy lại: 0 nghi bí mật.

W8 "`git status --ignored` đủ bắt ghi file bị gitignore": **chỉ một phần**. Bắt được thư mục/file ignored *mới*;
không bắt được file ghi thêm vào thư mục ignored đã có từ trước, và cố ý bỏ qua thư mục build (`artifact_paths`:
node_modules, dist, build, coverage, .vite, __pycache__, *.tsbuildinfo). Có test ghi lại giới hạn này.

Giới hạn còn lại (ADJUSTMENTS #7, #8 — ghi rõ, không gọi là sandbox):
- Lệnh kiểm chạy mã của dự án (test, script npm) với quyền của Dung: đọc/ghi file, mạng, không bị cô lập.
- Env chỉ bỏ biến theo tên; secret đặt trong file (`.npmrc`, `.env`) vẫn đọc được.
- Scope là phát hiện sau khi xảy ra; `.orchestra/` không nằm trong kiểm scope (orc tự ghi ở đó).
- Glob `*` khớp cả `/` (FINDING-3).
- `orc verify` chưa chặn `done` khi fail: chỉ là bằng chứng song song cho reviewer và Dung (state machine ở Phase 4).
- Replay dùng API nội bộ tạo checkpoint (task cũ đã done) và scope = hợp write_scope của yêu cầu (commit gộp).

## Test

`python -m unittest discover -s tests`: **100 passed + 1 skipped (Ran 101)** — 85 cũ + 16 mới (`tests/test_phase2.py`).

## AC

- AC-2.1 đạt (`test_commands_come_from_checkpoint_not_current_config`, `test_tampered_checkpoint_refused`).
- AC-2.2 đạt (tracked đã commit, untracked, ignored mới, file bẩn từ trước bị đổi; file bẩn không đổi không tính).
- AC-2.3 đạt. AC-2.4 đạt (env, cwd, timeout giết cây tiến trình). AC-2.5 đạt.
- AC-2.6 **đạt có điều kiện**: test/build/scope trên 5 yêu cầu thật khớp tự khai, không có tự khai sai nào lọt.
  Lint không kiểm được vì môi trường; mọi tự khai lint bị báo `LỆCH` (không lọt) nhưng chưa xác nhận đúng/sai → FINDING-4.
- AC-2.7 đạt (`test_no_verify_config_keeps_v01_behaviour`; toàn bộ test cũ xanh).
