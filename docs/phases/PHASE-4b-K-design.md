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

## Dung chốt 2026-10-09: "đồng ý theo khuyên dùng" (A, Q2–Q5)

## Phạm vi thực hiện

1. **K là opt-in theo dự án** (`config.yaml: workflow: k`, Dung đặt — config nằm trong deny_always của guard).
   Yêu cầu mới tạo bằng `orc new request` (task gốc, owner orchestrator, `workflow: k`, trạng thái `NEW`).
   Ở dự án K, mọi task mới khác phải có `--parent <gốc>` (`orc new task --from PLAN` tự gán) — không còn đường
   "task mồ côi" lách cổng. Task cũ (không parent) giữ luật 0.1.0 cho tới khi xong ⇒ **không cần script chuyển**
   dữ liệu cũ (đơn giản hơn Q5; dữ liệu 0.1.0 không bị sửa). F5 thêm ánh xạ ngược K → 0.1.0.
2. **Task gốc** chỉ đổi trạng thái bằng `orc advance` theo bảng K (+ READY_FOR_IMPLEMENTATION của ADJ #2), orc
   kiểm điều kiện; level chưa phân mức ⇒ chỉ đi APPROVAL_REQUIRED (Q2). Vào APPROVAL_REQUIRED / READY_FOR_
   IMPLEMENTATION: orc tự tạo **một** yêu cầu duyệt gồm task gốc + ART research + DEC proposed của yêu cầu
   (ADJ #2 "hỏi một lần"). Binding task gốc: plan accepted của task con, hợp write_scope task coder, danh sách task
   coder, level, risk_flags. Vào IMPLEMENTING cần approval còn hiệu lực.
3. **Task con:** coder chỉ `dispatched` khi gốc ở IMPLEMENTING và approval của gốc còn hiệu lực (plan/scope/danh sách
   task đổi ⇒ phải duyệt lại). Reviewer đạt ⇒ orc đọc lần `orc verify` mới nhất: PASS ⇒ done; FAIL test/lint/build ⇒
   REPAIR (về coder, attempts+1; > 2 ⇒ ESCALATE); scope/bí mật ⇒ ROLLBACK (in lệnh cho Dung) + ESCALATE;
   INCOMPLETE môi trường ⇒ ESCALATE (Q3); chưa chạy verify / dự án chưa cấu hình `verify:` ⇒ từ chối envelope.
   Review không đạt: bảng I2 (Q4) — ESCALATE với level chưa phân mức cho SPEC_GAP; REGRESSION ⇒ ROLLBACK + ESCALATE.
   ESCALATE ở task con ⇒ task gốc BLOCKED.
4. **BLOCKED → trạng thái trước** chỉ bằng `orc resume GỐC` khi Dung đã gõ `orc:resume GỐC` sau lúc bị chặn;
   **ABORTED** bằng `orc abort GỐC` khi Dung gõ `orc:abort GỐC`. VERIFYING → DONE khi mọi task coder done.
5. `orc set` không đổi `parent, workflow, recovery_action`. Guard giữ shadow. `commands/auto.md` theo K.

## AC

- AC-4b.1: Bảng chuyển K: chuyển sai bị từ chối (+ journal `rejected`), đúng thì qua; level chưa phân mức không vào
  READY_FOR_IMPLEMENTATION.
- AC-4b.2: Không giao được task coder trước khi Dung duyệt; plan/scope/task con đổi sau duyệt ⇒ không giao được.
- AC-4b.3: Task coder không done khi verify chưa chạy/FAIL/INCOMPLETE; định tuyến REPAIR/ROLLBACK/ESCALATE đúng I2.
- AC-4b.4: resume/abort chỉ với lời Dung; ESCALATE con ⇒ gốc BLOCKED.
- AC-4b.5: Dự án K không tạo được task không parent; dự án/ task cũ chạy như trước (test cũ xanh).
- AC-4b.6: Vòng K đầy đủ qua CLI: request → … → DONE với token Dung giả lập qua hook prompt_log.
- AC-4b.7: F5 quay lui được dữ liệu có task K về 0.1.0 (validate 0.1.0 OK). Toàn bộ test xanh.

## Kết quả

Code: `cli/orc_k.py` (mới: bảng K, điều kiện, cổng giao/verify, I2, resume/abort, gợi ý `orc next`);
`cli/orc_core.py` (trường tuỳ chọn `parent, workflow, recovery_action`; trạng thái K hợp lệ chỉ cho task gốc;
failure_class I1; `orc new request`, `--parent`, `orc resume/abort`; `advance` gọi K; định tuyến review K trước khi ghi;
ESCALATE ⇒ gốc BLOCKED; dự án K bắt buộc parent; brief dòng `Workflow: K`; journal ts micro giây);
`cli/orc_approval.py` (binding task gốc K); `cli/orc_verify.py` (dòng journal `event: verify`);
`tools/rollback_v02_to_v01.py` (ánh xạ K → 0.1.0); `commands/auto.md` (viết lại theo K); `SCHEMA.md` §6c.

Khác đề xuất Q5 (đơn giản hơn, ghi rõ): K là opt-in và task cũ không parent giữ luật 0.1.0 ⇒ **không cần script
chuyển dữ liệu cũ sang K**; dữ liệu 0.1.0 không bị sửa. Lỗ "task mồ côi lách cổng" bị chặn bằng luật dự án K bắt buộc
`--parent` (kể cả `--from PLAN`). Nếu Dung vẫn muốn chuyển task cũ đang mở sang K: làm sau, khi có task cũ đang mở.

Tương thích: `orc` mới chạy `validate` (OK) và `brief` trên `D:\WMS` (chỉ đọc); git sạch.

Giới hạn còn lại:
- Level vẫn "chưa phân mức" tới Phase 5 (triage) ⇒ mọi yêu cầu đi APPROVAL_REQUIRED + V3; READY_FOR_IMPLEMENTATION
  chưa dùng được.
- DONE → INTEGRATED chỉ là ghi nhận (orc chưa kiểm commit đã lên main).
- Reviewer V3 "phiên mới / model khác ở L3" chưa ép (Phase 7).
- Đường Python nội bộ vẫn lách được (đã ghi ở Phase 4); guard vẫn shadow.

## Test

`python -m unittest discover -s tests`: **156 passed + 1 skipped (Ran 157)** — 145 cũ (không sửa test cũ nào) + 12 mới
(`tests/test_phase4b.py`: vòng K đầy đủ qua CLI tới INTEGRATED, cổng approval/plan đổi, bắt buộc parent, `orc set`
không đổi trường K, REPAIR/ESCALATE môi trường + resume cần lời Dung, ROLLBACK scope, I2 review, abort, bảng I2,
quay lui dữ liệu K về 0.1.0).

## AC

AC-4b.1 … AC-4b.7 đạt.

## Dung xác nhận sau khi xong (2026-10-09 13:16)

"1. A — 2. Đồng ý bỏ": giữ phương án A như đã làm; **bỏ** script chuyển dữ liệu 0.1.0 → K (Q5) — task cũ giữ luật
0.1.0, K chỉ áp cho yêu cầu mới ở dự án bật `workflow: k`.
