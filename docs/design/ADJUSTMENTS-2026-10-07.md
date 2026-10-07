# ĐIỀU CHỈNH CỦA DUNG (2026-10-07) — thắng v0.2 ở các điểm này

Khi mâu thuẫn với `orchestra-redesign-v0.2.md` thì file này thắng.

1. Giữ nguyên tắc "tách trách nhiệm trước, tách phiên LLM sau" và mô hình 3 plane.
2. Giữ quyết định "chặng hiểu & thiết kế luôn dừng".
   - L0/L1: sau plan, task vào trạng thái `READY_FOR_IMPLEMENTATION`, hỏi Dung xác nhận một lần rồi mới code.
   - L2/L3: giữ `APPROVAL_REQUIRED` + risk approval như v0.2.
   - Không biến mọi task thành quy trình nặng.
3. Fail-closed, nhưng KHÔNG có `ORC_GUARD=off` bypass toàn bộ. Thay bằng `MAINTENANCE/SAFE_MODE`: chỉ cho sửa lỗi Orchestra (kit, cấu hình orchestra); không cho mutation workflow (chuyển trạng thái, approve) và mutation project (code app, migrations).
4. Giữ `orc:approve`, nhưng approval bind với `TASK + PLAN_HASH + WRITE_SCOPE_HASH + LEVEL + RISK_FLAGS + NONCE`. Nonce do orc sinh, dùng một lần. Plan, scope, level hoặc risk thay đổi thì approval cũ hết hiệu lực.
5. Context Compiler giữ thiết kế v0.2, phân biệt rõ `USER_INTENT` / `NORMATIVE_AUTHORITY` / `SYSTEM_REALITY`. Không biến lời người dùng thành rule/DEC.
6. Level tăng đơn điệu. Kích thước chỉ dùng để nâng level; task nhỏ không mặc định an toàn.
7. Giữ V1/V2/V3. `orc verify` phải kiểm soát môi trường thực thi ở mức phù hợp, ví dụ: env tối thiểu (loại biến chứa token/secret/key), cwd cố định, timeout, lệnh đọc từ config tại checkpoint. Không coi "lệnh cố định" là "lệnh an toàn". Ghi rõ giới hạn còn lại.
8. Write scope là mutation boundary + detection, KHÔNG gọi là sandbox. Giữ kiểm post-hoc bằng `git diff` / `git status`.

Mục tiêu: v0.2 + các điều chỉnh trên, không thêm complexity ngoài mức cần thiết.
