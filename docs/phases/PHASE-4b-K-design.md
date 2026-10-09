# PHASE 4b — State machine K: đề xuất ánh xạ, chờ Dung chốt (2026-10-09)

Dung yêu cầu: "Làm state machine K, giữ guard ở shadow". Guard giữ shadow — không đổi.

## Vì sao phải hỏi trước khi code

v0.2 mục K mô tả K cho **một task đi trọn** từ triage → research → plan → implement → verify, do Main chạy theo
mode (đó là Phase 7 "gộp agent"). Kit hiện tại (0.1.0 + Phase 1–4) vẫn tách mỗi yêu cầu thành nhiều task: task gốc
(researcher, chặng 1) → task plan (researcher) → các task coder → review. Áp K lên mô hình nhiều task này là quyết định
kiến trúc **thiết kế chưa nói** (FINDING-7). Ngoài ra triage (level) là Phase 5, chưa có.

## Đề xuất

**A (khuyên dùng) — K chạy ở task gốc của yêu cầu; task con giữ vòng ngắn có điều kiện.**

```
Task gốc (yêu cầu):
NEW → TRIAGED → [RESEARCHING] → PLANNED → READY_FOR_IMPLEMENTATION | APPROVAL_REQUIRED → IMPLEMENTING → VERIFYING → DONE → [INTEGRATED]
                                          (L0/L1, ADJ #2)            (L2/L3 / chưa có level)
phụ: BLOCKED · FAILED · ABORTED
Task con (plan, coder, review): pending → ready → dispatched → in_review → done (như hiện nay), nhưng:
  - task coder chỉ được giao khi task gốc ở IMPLEMENTING (đã có approval của Dung, binding plan + write_scope);
  - task coder chỉ done khi có EVD `orc verify` PASS (by: orc) + reviewer đạt — không còn done nhờ tự khai;
  - task gốc VERIFYING → DONE khi mọi task coder done.
```
Ưu: giữ nguyên máy chạy subagent đang ổn định (Phase 3 shadow: 17 task chạy trơn), thêm đúng các cổng K cần:
phê duyệt trước khi code, kiểm chứng tất định trước DONE, journal + `orc advance` là đường duy nhất đổi trạng thái gốc.
Khi Phase 7 gộp agent, task gốc chính là task K của v0.2 — không phải làm lại.

**B — đổi mọi task sang K** (plan/coder/review đều đi đủ trạng thái K). Đúng chữ v0.2 hơn nhưng phải viết lại
`apply`/`next`/định tuyến failure_class và mọi prompt agent ngay bây giờ, rồi Phase 7 lại đổi tiếp. Không khuyên.

## Câu hỏi cho Dung (trả lời một từ được)

- **Q1**: Áp K theo A (task gốc chạy K, task con vòng ngắn có điều kiện)? — Khuyên: **A**.
- **Q2**: Khi chưa có triage (Phase 5), level = "chưa phân mức" ⇒ đi đường **APPROVAL_REQUIRED** (Dung gõ
  `orc:approve` một lần trước khi code; reviewer độc lập bắt buộc). ADJ #6: nhỏ không mặc định an toàn. — Khuyên: **đồng ý**.
- **Q3**: VERIFYING → DONE bắt buộc `orc verify` PASS; INCOMPLETE (lỗi môi trường) ⇒ BLOCKED hỏi Dung; dự án
  chưa có mục `verify:` ⇒ không DONE được (phải cấu hình). — Khuyên: **đồng ý** (WMS thêm `verify:` khi bật v0.2).
- **Q4**: Thất bại theo bảng I2 (RETRY/REPAIR/ROLLBACK/ESCALATE/ABORT) làm cùng K; ROLLBACK **chỉ đánh dấu + in
  lệnh** cho Dung, orc không tự `git reset --hard` (đã là deny_always). — Khuyên: **đồng ý**.
- **Q5**: Dữ liệu 0.1.0 (D:\WMS): script chuyển trạng thái cũ → K (giữ `state.v0.1/`), dry-run mặc định, không tự
  chạy trên WMS; F5 rollback mở rộng ánh xạ ngược K → 0.1.0. — Khuyên: **đồng ý**.

Không làm ở 4b: bật guard thật, triage (Phase 5), gộp agent (Phase 7).
