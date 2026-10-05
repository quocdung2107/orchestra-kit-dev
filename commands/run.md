---
description: Orchestra — giao một task ready cho subagent theo owner
argument-hint: [TASK-ID]
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Task chỉ định (có thể trống): $ARGUMENTS

Chỉ đọc metadata; không đọc code/plan (D3). Mọi ghi trạng thái qua `orc` (D4).

1. Nếu phiên chưa mở S-ID: mở bằng lệnh trong brief (`orc handoff open ...`), `--task` là task sắp chạy.
2. `orc next`. Không chỉ định task → lấy task ở dòng `NEXT:`. Task chỉ định phải ở trạng thái ready.
   Có dòng `HỎI DUNG` liên quan → dừng và hỏi Dung.
3. `orc show <TASK-ID> --meta` để biết owner.
   - owner `coder*` → subagent **coder**, prompt: `TASK: <TASK-ID>. Trả envelope YAML.`
   - owner `researcher` → `orc new artifact --type plan --task <TASK-ID> [--supersedes <ART plan cũ trong inputs>]`,
     rồi subagent **researcher**, prompt: `TASK: <TASK-ID>. Viết plan vào <ART-ID>. Trả envelope YAML.`
4. Trước khi gọi: `orc set <TASK-ID> status=dispatched`.
5. Nạp envelope: `orc apply - <<'YAML'` … `YAML`. Nếu orc từ chối (ví dụ file ngoài write_scope),
   báo Dung nguyên văn lỗi, không tự sửa state.
6. Theo dòng `ROUTE:` — `/review <TASK-ID>` là bước kế tiếp với code; plan mới thì đưa Dung duyệt như /plan bước 6–7.
