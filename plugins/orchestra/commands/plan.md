---
description: Orchestra — lập plan cho một yêu cầu bằng subagent orchestra:researcher
argument-hint: <mô tả yêu cầu>
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Yêu cầu: $ARGUMENTS

Quy tắc A (D3, D4): chỉ đọc metadata (`orc show <ID> --meta`, `orc next`, brief); không đọc
nội dung plan/code; mọi ghi trạng thái đi qua `orc`. Truyền ID cho subagent, không truyền chat dài.

1. Nếu phiên chưa mở S-ID: chạy lệnh `orc handoff open --key ... --role orchestrator --request "..."`
   đúng như dòng trong brief đầu phiên. Ghi nhớ S-ID.
2. `orc new task --title "<tóm tắt yêu cầu ≤80 ký tự>" --owner researcher --summary "<≤200 ký tự>"` → TASK-ID.
   Rồi `orc set <S-ID> task=<TASK-ID>`.
3. `orc new artifact --type plan --task <TASK-ID> --summary "<≤200 ký tự>"` → ART-ID.
4. `orc advance <TASK-ID> --to dispatched`, rồi gọi subagent **orchestra:researcher** với prompt chỉ gồm:
   `TASK: <TASK-ID>. Viết plan vào <ART-ID>. Trả envelope YAML.`
5. Lưu nguyên envelope YAML subagent trả về vào state:
   `orc apply - <<'YAML'` … `YAML`. Đọc dòng `ROUTE:`.
6. Báo Dung: đường dẫn `.orchestra/artifacts/<ART-ID>.md`, summary (`orc show <ART-ID> --meta`),
   các quyết định chờ duyệt. `orc approval request <ART-ID> <các DEC proposed của plan>` và gửi Dung nguyên văn
   dòng `orc:approve ...` nó in ra. **Dừng chờ.**
7. Khi Dung gõ đúng dòng đó: `orc approve <ART-ID> <các DEC>` (plan + DEC thành accepted — H7),
   `orc new task --from <ART-ID>`, `orc next`.
   Dung yêu cầu sửa → gọi lại orchestra:researcher với cùng TASK/ART kèm ý của Dung (1–2 câu).
