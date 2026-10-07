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
