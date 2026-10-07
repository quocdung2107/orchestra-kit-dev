# FINDINGS — vấn đề phát hiện khi triển khai v0.2

Mỗi FINDING: vấn đề, bằng chứng, lựa chọn, đề xuất. Không tự mở rộng scope; chờ Dung quyết ở boundary.

## FINDING-1 — install.py nhận hook cũ theo tên thư mục kit (Phase 0)

- **Vấn đề:** `install.py` nhận hook cũ của kit bằng chuỗi `MARK = "orchestra-kit/hooks/"`. Cài từ thư mục
  có tên khác (worktree `orchestra-kit-v02`, hoặc kit đổi tên) thì hook cũ không được nhận ra, chạy lại sẽ
  ghi trùng hook SessionStart/Stop vào `~/.claude/settings.json`.
- **Bằng chứng:** `tests/test_install.py::test_install_is_idempotent_and_keeps_settings` fail trong worktree
  (`2 != 1`), pass trên `~/orchestra-kit` và trên bản sao tạm đặt tên `orchestra-kit`.
- **Lựa chọn:** (a) giữ nguyên, test bỏ qua đúng trường hợp tên thư mục khác; (b) nhận hook theo
  `KIT/hooks/<tên>` tuyệt đối + tên file hook; (c) đánh dấu hook bằng một khoá riêng trong settings.
- **Đề xuất:** (a) bây giờ (đã làm, `skipIf` chỉ khi `KIT.name != "orchestra-kit"`). Sửa theo (b) khi phase
  có thêm hook (3/4) phải đụng `install.py`, vì đó là bước release cần Dung duyệt.

## FINDING-2 — 0.1.0 không ghi thời điểm và không ghi lần từ chối (Phase 0)

- **Vấn đề:** Hai chỉ số của mục O không đo chính xác được từ dữ liệu 0.1.0:
  - *Thời gian*: registry không có timestamp; dấu phiên `runtime/sessions` mở muộn (S-0003 mở 23:22, đóng
    23:22 dù việc đã làm trước đó). Baseline chỉ có xấp xỉ bằng mtime file, lẫn việc khác (TASK-0001: 202 phút
    vì CTX-0001/0002 được tạo lúc thử graph).
  - *Envelope bị từ chối*: `orc apply` từ chối thì không ghi gì (đúng thiết kế "kiểm trước rồi mới ghi").
- **Bằng chứng:** `docs/phases/PHASE-0-baseline.md`, `cli/orc_core.py` `apply_envelope`.
- **Hệ quả:** cổng Phase 7 ("chỉ số phase 0 tốt hơn") sẽ so với baseline yếu ở 2 chỉ số này.
- **Lựa chọn:** (a) chấp nhận, chỉ so các chỉ số đo được (dừng, DEC, attempts, EVD, scope); (b) journal của
  Phase 1 ghi thêm sự kiện `rejected` (lệnh, lý do, hash lỗi) — cũng là dữ liệu cần cho bảng I2
  (RETRY khi "lỗi mới khác hash lỗi lần trước").
- **Đề xuất:** (b), chi phí nhỏ, nhưng là thêm vào phạm vi journal của Phase 1 nên **chờ Dung quyết**.
  Phase 1 hiện làm theo (a): journal chỉ ghi chuyển trạng thái như v0.2 K3.

## FINDING-3 — `*` trong write_scope khớp cả `/` (Phase 0)

- **Vấn đề:** `_in_scope` dùng `fnmatch`, nên `*` khớp qua nhiều cấp thư mục. Ví dụ `app/scripts/seed-carriers.*`
  khớp `app/scripts/seed-carriers.x/y/z.ts`; `supabase/migrations/2026*_carriers_*.sql` khớp file ở thư mục con.
  Write scope rộng hơn người đọc nghĩ.
- **Bằng chứng:** `cli/orc_core.py` `_in_scope`; scope thật trong `D:\WMS\.orchestra\state\tasks.yaml` (TASK-0008, 0010).
- **Lựa chọn:** (a) giữ ngữ nghĩa cũ ở mọi nơi (tương thích task cũ); (b) Phase 2 scope check dùng ngữ nghĩa
  `*` không qua `/`, `**` qua nhiều cấp (giống `.gitignore`), task cũ phải viết lại scope.
- **Đề xuất:** Phase 2 giữ (a) để không đổi hành vi 0.1.0 (cổng Phase 1–2 là "0.1.0 vẫn chạy"); ghi rõ
  giới hạn. Đổi sang (b) cùng lúc với state machine ở Phase 4, cần Dung duyệt.

## FINDING-4 — `orc verify` không phân biệt lỗi môi trường với lỗi thật; lint đang không chạy được trên máy (Phase 2)

- **Vấn đề:** Phát lại 5 yêu cầu thật: `npm run lint` fail ở cả 5 vì Windows Application Control chặn file native
  `@oxlint/binding-win32-x64-msvc/oxlint.win32-x64-msvc.node` ("An Application Control policy has blocked this
  file"). Chặn cả bản gốc ở `D:\WMS\app\node_modules` (thử `require` trực tiếp), không chỉ bản chép ở Temp.
  `orc verify` ghi `lint: fail` và so với tự khai thành 13 dòng `LỆCH` — đúng là không cho lọt, nhưng **không
  phải** bằng chứng tự khai sai: lúc 2026-10-05/06 lint có thể đã chạy được.
- **Bằng chứng:** `docs/phases/PHASE-2-replay.md`; log `.orchestra/runtime/verify/TASK-*/lint.log` trong bản replay.
- **Hệ quả:** (1) với Dung: `npm run lint` hiện có thể không chạy trên máy này (nên tự thử); (2) với thiết kế:
  verdict nhị phân pass/fail làm báo động giả, dễ dẫn tới "mệt mỏi phê duyệt" (W2.2).
- **Lựa chọn:** (a) giữ nhị phân, người đọc log; (b) thêm `failure_class: ENV` cho kết quả lệnh khi khớp chữ ký
  lỗi môi trường đã biết (không tìm thấy lệnh, bị chính sách chặn, timeout) — đúng nhãn I1 của v0.2, dùng ở bảng I2
  (ENV → RETRY ≤ 2 rồi ESCALATE).
- **Đề xuất:** (b) làm cùng bảng I2 ở Phase 4, không làm trong Phase 2. Dung kiểm `npm run lint` trên máy.

## FINDING-5 — Quay lui về 0.1.0 sau khi chạy thử v0.2 bị `orc validate` cũ từ chối (Phase 3)

- **Vấn đề:** v0.2 thêm trường tuỳ chọn vào registry: task `level, risk_flags` (Phase 3, cho binding approval),
  evidence `by` (Phase 2), và file mới (`state/journal.jsonl`, `state/approvals.yaml`, `state/checkpoints/`).
  `orc validate` của 0.1.0 báo "trường lạ" với mọi task/EVD tạo bằng v0.2 ⇒ hook Stop của 0.1.0 chặn kết thúc phiên
  (tối đa 3 lần) và validate không còn `OK`.
- **Bằng chứng:** `cli/orc_core.py` 0.1.0 `entry_errors`: `unknown = [f for f in e if f not in FIELDS[kind]]`.
- **Hệ quả:** nguyên tắc mục O "rollback từng phase: dự án đặt kit_version cũ" không tự đúng khi dữ liệu đã ghi bằng v0.2.
- **Lựa chọn:** (a) script quay lui bỏ các trường/file mới (giữ bản sao); (b) chạy thử v0.2 trên **bản sao** dự án;
  (c) chấp nhận: đã thử v0.2 thì không quay lui dữ liệu, chỉ quay lui kit.
- **Đề xuất:** (a), gộp vào script chuyển registry của Phase 4 (v0.2 đã định giữ `state.v0.1/`). Trước khi Dung
  chạy thử Phase 3 trên `D:\WMS`: commit `.orchestra/` để quay lui bằng git được.
