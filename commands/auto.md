---
description: Orchestra — 2 chặng. (1) Hiểu yêu cầu & thiết kế, hỏi Dung chỗ chưa rõ. (2) Plan → code → review → báo cáo, tự chạy, chỉ dừng khi cần quyết
argument-hint: <mô tả yêu cầu>
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Yêu cầu: $ARGUMENTS

Quy tắc A: chỉ đọc metadata và kết quả lệnh `orc` (D3); mọi ghi state qua `orc` (D4); truyền ID cho subagent.
Không báo tiến độ từng bước; chỉ nói với Dung ở điểm dừng và ở báo cáo cuối.

## Chặng 1 — Hiểu yêu cầu & thiết kế (luôn dừng chờ Dung)
1. Phiên chưa mở S-ID → chạy lệnh `orc handoff open --key ...` có trong brief, `--request "$ARGUMENTS"`.
2. `orc new task --title "<tóm tắt ≤80 ký tự>" --owner researcher --summary "<≤200>"` → ROOT.
   `orc set <S-ID> task=<ROOT>`. `orc new artifact --type research --task <ROOT> --summary "Hiểu yêu cầu & thiết kế"` → UND.
3. `orc set <ROOT> status=dispatched`; subagent **researcher**:
   `TASK: <ROOT>. Viết hiểu yêu cầu & thiết kế vào <UND>. Trả envelope YAML.` → `orc apply - <<'YAML'` … `YAML`.
4. `orc ask <UND>` và gửi Dung **nguyên văn** kết quả, cuối thêm một dòng:
   "Trả lời các câu hỏi (hoặc ghi 'đồng ý theo khuyên dùng'), sửa chỗ tôi hiểu sai nếu có."
   `orc ask` báo lỗi (mục chưa điền) → gửi lỗi cho researcher sửa rồi chạy lại. **Dừng chờ Dung.**
5. Dung trả lời:
   - Mỗi ý Dung chốt → `orc new decision --status accepted --scope <UND> --summary "<≤200>"`.
   - Dung sửa cách hiểu nhiều hoặc thêm yêu cầu mới → `orc set <ROOT> status=dispatched`, gọi lại researcher
     với cùng ROOT/UND kèm ý của Dung (1–3 câu), `orc apply -`, rồi lặp lại bước 4.
   - Đủ rõ → `orc set <UND> status=accepted`, sang chặng 2.

## Chặng 2 — Plan → code → review → báo cáo (tự chạy)
1. `orc new task --title "Plan: <tóm tắt>" --owner researcher --inputs <UND> <các DEC vừa tạo>` → PT;
   `orc new artifact --type plan --task <PT> --depends-on <UND>` → PLAN.
   `orc next`, `orc set <PT> status=dispatched`; researcher: `TASK: <PT>. Viết plan vào <PLAN>. Trả envelope YAML.` → `orc apply -`.
2. `orc gate <PLAN>`: `PROCEED` → `orc set <PLAN> status=accepted`, `orc new task --from <PLAN>`.
   `ASK` → **điểm dừng** (báo các dòng sau `ASK`).
3. Lặp đến khi `orc next` không còn `READY:`/`REVIEW:` của yêu cầu này:
   - `HỎI DUNG` → **điểm dừng**.
   - `REVIEW: <T>` → `orc new artifact --type review_report --task <T>` → R; reviewer:
     `TASK: <T>. Báo cáo vào <R>. Dùng orc show <T> --pack. Trả envelope YAML.` → `orc apply -`.
   - `READY: <T>` → `orc set <T> status=dispatched`; owner coder → coder: `TASK: <T>. Trả envelope YAML.`;
     owner researcher (replan) → `orc new artifact --type plan --task <T> --supersedes <plan cũ>` rồi researcher → `orc apply -`.
   - `orc` từ chối envelope → gửi nguyên văn lỗi cho subagent đó sửa, tối đa 2 lần, rồi **điểm dừng**.
4. Kết thúc:
   - Code trong `app/` (repo riêng): nhánh `orchestra/<ROOT>`, commit; **không merge, không push**. Commit `.orchestra/` trong `D:\WMS`.
   - Điền `.orchestra/sessions/<S-ID>.md`, `orc handoff check --key ...`, `orc validate`.
   - Trả Dung **một lần**: `orc report <PT>` (giữ nguyên bảng) + tối đa 5 dòng: giả định đã tự chọn,
     việc Dung cần thử tay, nhánh cần merge.

## Điểm dừng ở chặng 2 (chỉ những trường hợp này)
`orc gate` = ASK · `HỎI DUNG` (DECISION_CONFLICT, attempts > 2, blocked, failed) · REGRESSION không tự sửa được
sau 1 vòng · lỗi môi trường không tự khắc phục. Khi dừng: handoff `result: blocked`, hỏi một câu trả lời được bằng
một từ, kèm phương án khuyên dùng.
