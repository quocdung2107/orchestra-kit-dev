# PHASE 4 — Sửa trước khi bật guard thật (Dung duyệt 2026-10-08)

Nguồn: quyết định của Dung 2026-10-08 sau shadow Phase 3 (FINDING-6 chọn A + nguyên tắc chính thức; H7 là P0;
F2–F5; Agent/SubagentHandback). Phạm vi chỉ gồm các mục dưới. **Không** bật enforce, **không** làm state machine K
(mục O phase 4 của v0.2) — hai việc đó chờ Dung duyệt riêng. Không xây parser shell, không sandbox.

## Nguyên tắc (Dung chốt)

Bash không phải semantic sandbox. Guard chỉ deny thao tác nguy hiểm nhận diện được với độ tin cậy cao; còn lại
`orc verify` hậu kiểm (git diff/status, risk paths). Không suy write_scope từ Bash. write_scope kiểm trực tiếp cho
Edit/Write. False positive thấp và ổn định quan trọng hơn bắt mọi mutation qua Bash.

## Phạm vi

1. **FINDING-6 — guard Bash:** bỏ allowlist theo mode và bộ tách lệnh. Trước khi khớp: bỏ thân heredoc và nội dung
   chuỗi trích dẫn (không phân tích cú pháp). Deny tin cậy cao: git push/force/merge/rebase/reset --hard/clean -f/
   branch -D; DB (`supabase db push|reset`, psql ngoài localhost); publish/deploy; xoá đệ quy; ghi vào vùng
   `deny_always` (chuyển hướng, tee, `sed -i`, rm/mv/cp, lệnh PowerShell ghi) — trừ file artifact/context mà task
   đang mở được ghi. Đọc file bí mật (`.env*`, `*.pem`, `*.key`) bị chặn cả qua Read/Bash.
   `deny_always` mở rộng: `~/.claude/**`, `.claude/**` của dự án, `.orchestra/**` (trừ artifact/context/session
   được phép), `.git/**` (mọi repo), đường dẫn bí mật/config trong `guard.protected_paths` của config.
2. **H7 (P0):** LLM chỉ PROPOSE DEC. `orc new decision --status accepted|superseded` bị từ chối; `orc advance DEC`
   bị bỏ; `orc set` không sửa `summary/scope/supersedes` của DEC đã accepted. DEC chỉ thành accepted qua
   `orc approve` với token `orc:approve <ID,...> <NONCE>` do Dung gõ (cùng cơ chế approval task, mở rộng cho DEC và
   ART research; một lần duyệt có thể gồm nhiều ID — ADJUSTMENTS #2 "hỏi một lần"). ART research (ghi nhận câu trả lời
   của Dung) cũng chỉ accepted qua approve. `commands/auto.md` sửa theo.
3. **F2:** mọi lệnh `orc` ghi state bị từ chối (OrcError) ghi journal
   `{event: rejected, task, operation, reason, reason_hash, actor, ts}` trong chuỗi hash. Không đổi ngữ nghĩa lệnh
   (vẫn lỗi, mã thoát như cũ). Journal cũ giữ nguyên. SAFE_MODE không ghi (không đổi state).
4. **F3:** một hàm khớp đường dẫn kiểu gitignore, neo ở gốc dự án: `*`/`?` không qua `/`, `**` qua nhiều cấp,
   đuôi `/` = thư mục, mục không glob = file hoặc thư mục đó. Dùng chung cho apply, verify, guard.
5. **F4:** kết quả lệnh verify: `pass | fail (TEST/LINT/BUILD/TYPECHECK_FAILURE) | ENVIRONMENT_FAILURE` theo chữ ký
   lỗi môi trường tin cậy cao (Application Control chặn, thiếu native binding, không tìm thấy lệnh, exit 126/127).
   ENVIRONMENT_FAILURE: EVD `info`, không tính `LỆCH`, tổng kết `INCOMPLETE` (exit 7), không phải lỗi dự án.
6. **F5:** `tools/rollback_v02_to_v01.py`: dry-run mặc định trên bản sao tạm, chuyển registry về schema 0.1.0 (lấy
   FIELDS/enum từ chính kit 0.1.0), chạy `orc validate` **của 0.1.0** trên bản sao; `--apply` chỉ khi bản sao hợp lệ
   và `.orchestra/` trong git sạch; giữ bản sao lưu đầy đủ.
7. **Agent/SubagentHandback:** đưa vào bảng tool của guard (không ghi ⇒ cho qua, ghi `agent_type`); tool lạ cho qua
   nhưng ghi "tool chưa phân loại".

## Acceptance criteria

- AC-4.1: Phát lại 511 tool call shadow thật qua guard mới: không còn false positive của FINDING-6 (heredoc, chuỗi,
  `\|`, ngoặc, chữ trong nội dung); mọi deny còn lại được liệt kê và giải thích.
- AC-4.2: Các ca nguy hiểm vẫn bị deny (bảng test); Edit/Write vẫn kiểm write_scope.
- AC-4.3: Không đường CLI nào (new/set/advance/apply) tạo được DEC accepted hoặc ART research accepted mà không có
  token của Dung; approve gộp nhiều ID chạy đúng; binding đổi ⇒ từ chối.
- AC-4.4: Lệnh bị từ chối có đúng 1 dòng `rejected` trong journal; mã thoát/ thông báo không đổi; journal cũ hợp lệ.
- AC-4.5: Bảng test khớp đường dẫn (regression F3).
- AC-4.6: Log lint bị Application Control chặn ⇒ ENVIRONMENT_FAILURE, không LỆCH; phát lại 5 yêu cầu thật xác nhận.
- AC-4.7: Rollback: dự án có dữ liệu v0.2 → bản sao qua `orc validate` 0.1.0 = OK; từ chối `--apply` khi git bẩn.
- AC-4.8: Toàn bộ test xanh.

## Kết quả

**FINDING-6.** `cli/orc_guard.py` viết lại: bỏ allowlist theo mode, bỏ bộ tách lệnh. `shell_view` chỉ bỏ thân heredoc
và câu trong ngoặc có khoảng trắng (không phân tích cú pháp); luật deny tin cậy cao chạy trên đó; đích ghi chỉ lấy ở
dạng rõ ràng (`>`/`>>`, tee, sed/rm/mv/cp/…, lệnh PowerShell ghi) để bảo vệ vùng deny_always. `active.json` v2 có
`writable` (artifact/context của task chưa done, handoff đang mở) và `protected` (`guard.protected_paths`).
Phát lại 511 tool call thật của shadow Phase 3 (`PHASE-4-guard-replay.md`): phát lại 383 lệnh Bash/Read/Grep,
lẽ ra chặn **109 → 1**; lệnh còn lại là lệnh trong log bị cắt ở 200 ký tự giữa đường dẫn `.orchestra/cont…` (bản đầy
đủ là file CTX được phép ghi) — không phải false positive của guard. Edit/Write (38) không phát lại vì log không có
write_scope lúc đó; luật Edit/Write không đổi ngoài vùng deny_always mở rộng.

**H7.** `orc new decision` chỉ tạo `proposed`; `orc advance DEC` không còn; `orc advance ART-research --to accepted`
bị từ chối; `orc set` không sửa `summary/scope/supersedes` của DEC đã accepted; envelope chỉ tạo DEC proposed.
`orc approve` (mở rộng cho DEC/ART, nhiều ID một lần) là đường duy nhất tạo DEC accepted. `commands/auto.md`
chặng 1 và `commands/plan.md` chuyển sang `orc approval request` + Dung gõ `orc:approve` + `orc approve`.
Đường còn lại ngoài CLI: API Python nội bộ (`new_decision(status=...)`, `set_fields`) — guard Phase 3–4 không chặn được
`python -c` (FINDING-6), journal + approvals.yaml giúp phát hiện.

**F2.** `run()` bắt `OrcError` của lệnh ghi state (và `verify`), ghi `{event: rejected, task, operation, reason,
reason_hash, actor, ts}` vào journal rồi ném lại lỗi nguyên vẹn (mã thoát, thông báo không đổi). Lệnh đọc lỗi không
ghi. SAFE_MODE không ghi. Journal cũ giữ nguyên (chỉ nối thêm; test kiểm tiền tố).

**F3.** `orc_guard.match_path` dùng chung cho `_in_scope` (apply), verify (risk/guard/artifact) và guard. Mặc định
risk/guard/artifact viết lại theo `**/`. Khác gitignore có chủ đích: mẫu không có `/` vẫn neo ở gốc (an toàn hơn cho
write_scope). Phân biệt hoa/thường như git trên Linux.

**F4.** `orc_verify.classify`: `pass` / `TEST|LINT|BUILD|TYPECHECK_FAILURE` / `ENVIRONMENT_FAILURE`. Timeout và
"Cannot find module" **không** xếp vào môi trường (có thể là lỗi dự án). Phát lại 5 yêu cầu thật hôm nay
(`PHASE-4-verify-replay.md`): lint **pass** cả 5 — Application Control không còn chặn oxlint ⇒ 13 `LỆCH` ở Phase 2 là
lỗi môi trường, tự khai lint lúc đó đúng. Vì môi trường đã hết lỗi, ENVIRONMENT_FAILURE được chứng minh bằng test
(log Application Control thật, thiếu binding, exit 127), không bằng dữ liệu thật.

**F5.** `tools/rollback_v02_to_v01.py`: schema lấy từ code kit 0.1.0 (từ chối nếu đưa kit v0.2); chuyển trên bản
sao tạm + `validate()` của 0.1.0; `--apply` chỉ khi bản sao OK và `.orchestra/` trong git sạch; sao lưu `state/`
vào `.orchestra/rollback-v0.2-<ts>/`. Dry-run thật trên `D:\WMS` (dữ liệu vẫn là 0.1.0): OK, 0 thay đổi, git sạch.

**Agent/SubagentHandback.** Thuộc `PASS_TOOLS` (cùng Task, SendMessage, TodoWrite…): cho qua, lý do "tool không ghi
file". Tool lạ: cho qua, ghi "tool chưa phân loại: X" để shadow lộ ra.

Test Phase 3 sửa theo quyết định mới (không phải hồi quy): allowlist Bash (implement/research/safe) → hậu kiểm;
`TestGuardDecide.act` thêm `writable`; `test_advance_table` DEC không advance được; báo cáo shadow 2 → 1 lần chặn.

## Test

`python -m unittest discover -s tests`: **144 passed + 1 skipped (Ran 145)** — 122 cũ + 22 mới (`tests/test_phase4.py`).

## AC

AC-4.1 đạt (109 → 1, 1 còn lại do log cắt). AC-4.2 đạt. AC-4.3 đạt. AC-4.4 đạt. AC-4.5 đạt. AC-4.6 đạt bằng test;
dữ liệu thật hôm nay không còn lỗi môi trường (lint pass). AC-4.7 đạt. AC-4.8 đạt.

## Chưa làm (không thuộc phạm vi Dung duyệt)

Bật guard thật (enforce, fail-closed) và state machine K (mục O phase 4 của v0.2); ép xác nhận trước khi code
(ADJUSTMENTS #2) — cần state machine/level. Chờ Dung duyệt riêng.
