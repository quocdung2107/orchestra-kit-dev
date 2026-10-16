---
description: Orchestra — review một task in_review bằng subagent orchestra:reviewer, định tuyến theo failure_class
argument-hint: <TASK-ID>
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Task: $ARGUMENTS

1. `orc show <TASK-ID> --meta`: status phải là `in_review`.
2. `orc verify <TASK-ID>`: orc tự kiểm scope bằng git và chạy lệnh kiểm, tạo EVD `by: orc` (exit 6 = fail: vẫn review,
   báo Dung các dòng `LỆCH`/ngoài write_scope). Dự án chưa có mục `verify:` hoặc task chưa có checkpoint → bỏ qua.
   `orc new artifact --type review_report --task <TASK-ID>` → ART-ID.
3. Gọi subagent **orchestra:reviewer**, prompt chỉ gồm:
   `TASK: <TASK-ID>. Báo cáo vào <ART-ID>. Dùng orc show <TASK-ID> --pack. Trả envelope YAML.`
   Không chuyển cho orchestra:reviewer summary hay lập luận của coder.
4. `orc apply - <<'YAML'` … `YAML`. Định tuyến do orc làm, A chỉ làm theo dòng `ROUTE:`:
   - `→ done` : báo Dung xong, `orc next`.
   - `trả ... về coder` (IMPL_BUG): `/orchestra:run <TASK-ID>`.
   - `researcher replan` (SPEC_GAP): `/orchestra:run <TASK mới>` (plan mới supersedes plan cũ), rồi đưa Dung duyệt.
   - `CHẶN MERGE` (REGRESSION): không commit/merge thay đổi của task; `/orchestra:run <task sửa>`.
   - `HỎI DUNG` (DECISION_CONFLICT hoặc attempts > 2): dừng, hỏi Dung bằng summary + ID.
