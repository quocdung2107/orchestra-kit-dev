---
description: Orchestra — viết handoff cho phiên hiện tại trước khi kết thúc
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

1. Xác định S-ID của phiên (dòng "Phiên này đang mở S-x" trong brief, hoặc lệnh `orc handoff open` đã chạy).
   Phiên chưa mở S-ID và có làm việc đáng ghi lại → mở bằng lệnh trong brief rồi viết.
2. Sửa `.orchestra/sessions/<S-ID>.md`:
   - frontmatter `result`: `done` | `partial` | `blocked`; `task`: TASK-ID chính (nếu có).
   - Điền đủ 5 mục: Đã làm · File thay đổi · Quyết định phát sinh · Câu hỏi mở · Bước tiếp theo.
     Mục trống ghi "Không có". Dùng ID (TASK-, ART-, DEC-, EVD-) thay vì kể lại nội dung.
3. `orc handoff check --key <key trong brief>` (hoặc `--sid <S-ID>`) đến khi in "handoff hợp lệ".
4. `orc validate` phải in `OK`.
