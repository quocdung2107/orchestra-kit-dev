---
description: Orchestra — tự chạy trọn vòng ý tưởng → thiết kế → plan → code → review → báo cáo, chỉ dừng khi cần Dung quyết
argument-hint: <mô tả yêu cầu>
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Yêu cầu: $ARGUMENTS

Chạy liền một mạch, **không hỏi Dung** trừ khi gặp điểm dừng bên dưới. Không báo tiến độ từng bước;
chỉ trả lời Dung một lần ở cuối (báo cáo) hoặc khi phải dừng.
Quy tắc A: chỉ đọc metadata và kết quả lệnh `orc` (D3); mọi ghi state qua `orc` (D4); truyền ID cho subagent.

## 1. Mở phiên và lập plan
1. Phiên chưa mở S-ID → chạy lệnh `orc handoff open --key ...` có trong brief, `--request "$ARGUMENTS"`.
2. `orc new task --title "<tóm tắt ≤80 ký tự>" --owner researcher --summary "<≤200>"` → ROOT.
   `orc set <S-ID> task=<ROOT>`. `orc new artifact --type plan --task <ROOT>` → PLAN.
3. `orc set <ROOT> status=dispatched`; subagent **researcher**: `TASK: <ROOT>. Viết plan vào <PLAN>. Trả envelope YAML.`
4. `orc apply - <<'YAML'` … `YAML` (envelope nguyên văn).
5. `orc gate <PLAN>`:
   - `PROCEED` → `orc set <PLAN> status=accepted`, `orc new task --from <PLAN>`, sang bước 2.
   - `ASK` → **điểm dừng**: báo Dung các dòng sau `ASK` (kèm đường dẫn plan), dừng. Khi Dung trả lời:
     ghi quyết định bằng `orc new decision --status accepted --scope <PLAN> --summary "..."`,
     gọi lại researcher với cùng ROOT/PLAN để cập nhật plan, rồi `orc gate` lại.

## 2. Vòng code → review (lặp)
Lặp đến khi `orc next` không còn dòng `READY:` hay `REVIEW:` thuộc yêu cầu này:
- Có dòng `HỎI DUNG` → **điểm dừng**.
- `REVIEW: <T>` → `orc new artifact --type review_report --task <T>` → R; subagent **reviewer**:
  `TASK: <T>. Báo cáo vào <R>. Dùng orc show <T> --pack. Trả envelope YAML.` → `orc apply -`.
- `READY: <T>` → `orc set <T> status=dispatched`;
  owner coder → subagent **coder**: `TASK: <T>. Trả envelope YAML.`;
  owner researcher (replan) → `orc new artifact --type plan --task <T> --supersedes <plan cũ>` rồi researcher như bước 1.3;
  → `orc apply -`. `orc` từ chối envelope → gửi nguyên văn lỗi cho subagent đó sửa, tối đa 2 lần, rồi **điểm dừng**.
- Làm theo dòng `ROUTE:`; không tự đổi trạng thái ngoài `orc`.

## 3. Kết thúc
1. Code đã đổi trong `app/` (repo riêng): tạo nhánh `orchestra/<ROOT>` và commit ở đó; **không merge, không push**.
   Commit `.orchestra/` trong repo `D:\WMS`.
2. Điền `.orchestra/sessions/<S-ID>.md` (5 mục, `result`), `orc handoff check --key ...`, `orc validate`.
3. Trả lời Dung **một lần** bằng `orc report <ROOT>` (giữ nguyên bảng), thêm tối đa 5 dòng:
   giả định đã tự chọn (mục Thiết kế trong plan), việc Dung cần thử tay (AC thao tác tay), nhánh cần merge.

## Điểm dừng (chỉ những trường hợp này)
`orc gate` trả `ASK` · dòng `HỎI DUNG` (DECISION_CONFLICT, attempts > 2, blocked, failed) · REGRESSION không tự sửa được
sau 1 vòng · lỗi môi trường không tự khắc phục được. Khi dừng: viết handoff `result: blocked`, hỏi Dung một câu
trả lời được bằng một từ, kèm phương án khuyên dùng.
