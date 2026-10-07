# Baseline 0.1.0 — D:\WMS

Sinh bởi `tools/phase0_baseline.py` (chỉ đọc). Số liệu tất định với cùng dữ liệu.

Task thật: **28**, gom thành **6** yêu cầu.

## Theo yêu cầu

| Yêu cầu | Phiên | Task (coder) | Dừng chặng 1 | DEC Dung chốt | Gate ASK hiện tại | Hook Stop chặn | attempts | Review (lại / draft) | CTX (graph) | EVD pass/fail/info | Phút (mtime) | File đổi | Ngoài write_scope (code) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-0001 B1 chống CSV injection khi xuất CSV | S-0001:done | 2 (1) | 0 | 1 | 1 | 0 | 0 | 1 (0 / 0) | 2 (1) | 9/0/2 | 202 | 3 | 0 (0) |
| TASK-0003 B2: chặn file Excel/CSV > 20 MB khi nạp | S-0002:done | 3 (2) | 0 | 0 | 1 | 1 | 0 | 2 (0 / 2) | 0 (0) | 10/0/3 | 14 | 4 | 0 (0) |
| TASK-0006 Thiết kế và lên ý tưởng Phase 3 | S-0003:done | 10 (8) | 1 | 5 | 0 | 1 | 0 | 8 (0 / 8) | 8 (4) | 35/0/10 | 24 | 15 | 0 (0) |
| TASK-0016 Tra SKU: kiểm tồn (máy tính), Picking, … | S-0004:done | 7 (5) | 1 | 3 | 0 | 0 | 0 | 5 (0 / 5) | 5 (3) | 31/0/6 | 12 | 9 | 0 (0) |
| TASK-0023 PWA chạy độc lập, không cần run dev (de… | S-0005:done | 5 (3) | 1 | 2 | 0 | 1 | 1 | 4 (1 / 4) | 3 (0) | 14/1/3 | 8 | 3 | 0 (0) |
| TASK-0028 Sửa email Supabase không gửi mã OTP 6 s… | S-0006:blocked | 1 (0) | 1 | 0 | 0 | 1 | 0 | 0 (0 / 0) | 0 (0) | 0/0/1 | 1 | — (không ghép commit) | 0 (0) |

## Tổng

| Chỉ số (mục O) | Giá trị | Nguồn |
|---|---|---|
| Thời gian (phút, mtime đầu→cuối, tổng các yêu cầu) | 261 | mtime file ART/CTX/session — xấp xỉ, không gồm thời gian chờ trước file đầu tiên |
| Số lần dừng chờ Dung: chặng 1 | 4 | ART research |
| Số câu Dung chốt (DEC) | 11 | decisions.yaml theo scope |
| Phiên kết thúc `blocked` | 1 | sessions/S-x.md |
| Hook Stop chặn (handoff chưa hợp lệ) | 4 | runtime/sessions/*.yaml |
| Envelope bị từ chối | không đo được | 0.1.0 không ghi log khi `orc apply` từ chối |
| Review trả lại (attempts) | 1 | tasks.yaml |
| EVD tổng / do orc tự chạy | 125 / 0 | evidence.yaml; mọi EVD là tự khai qua envelope (H2) |
| EVD `fail` | 1 | evidence.yaml |
| EVD `info` (phần lớn là "chưa kiểm") | 25 | evidence.yaml |
| File commit ngoài write_scope (tổng / code) | 0 / 0 | git show so với write_scope của task coder |
| Review report còn `draft` | 19 / 20 | artifacts.yaml |

## File ngoài write_scope (để người đọc phân loại)

- (không có)

## Commit đã ghép

- TASK-0001: (gốc):21ff20b, app/:904d9db
- TASK-0003: (gốc):df0413f, app/:429ca0e
- TASK-0006: (gốc):a02657b, app/:a949af2
- TASK-0016: (gốc):b530516, app/:5f3f69f
- TASK-0023: (gốc):f82a576, app/:3056913
- TASK-0028: (không có)

## Kit

- 12 commit, 2026-10-05 → 2026-10-06
