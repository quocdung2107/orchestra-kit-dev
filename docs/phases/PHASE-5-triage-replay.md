# Phase 5 — triage hồi cứu trên yêu cầu thật (shadow, chỉ đọc)

Lần 2 = write_scope các task coder; lần 3 = commit thật (bỏ `.orchestra/`). Không có form khai báo trong dữ
liệu cũ ⇒ chỉ tín hiệu máy (form thật có thể **nâng** thêm, không hạ). Cột cuối để Dung điền.

| Yêu cầu | Task coder | Lần 2: file scope → L | Lần 3: file / dòng / module → L | Kết quả (max) | Luật chính | Dung đánh giá |
|---|---|---|---|---|---|---|
| TASK-0001 B1 chống CSV injection khi xuất CSV | 1 | 3 → L3 | 3 / 66 / 2 → L3 | **L3** | từ khoá rủi ro: injection | L3 |
| TASK-0003 B2: chặn file Excel/CSV > 20 MB khi nạp | 2 | 4 → L2 | 4 / 45 / 4 → L2 | **L2** | kích thước: 4 file, 45 dòng, 4 module | L2 |
| TASK-0006 Thiết kế và lên ý tưởng Phase 3 | 8 | 15 → L3 | 15 / 1253 / 5 → L3 | **L3** | risk_path: supabase/migrations/20261007000000_carriers_base.sql, supabase/migrations/20261007000100_carriers_community.s | L3 |
| TASK-0016 Tra SKU: kiểm tồn (máy tính), Picking, … | 5 | 9 → L2 | 9 / 712 / 3 → L3 | **L3** | kích thước: 9 file, 712 dòng, 3 module | L3 |
| TASK-0023 PWA chạy độc lập, không cần run dev (de… | 3 | 3 → L3 | 3 / 101 / 2 → L3 | **L3** | risk_path: app/.github/workflows/deploy.yml | L3 |
| TASK-0028 Sửa email Supabase không gửi mã OTP 6 s… | 0 | 0 → L1 | 1 / 6 / 1 → L1 | **L1** | thiếu dữ kiện (không mặc định L0) | L1 |
| TASK-0029 Tạo đơn picking trong công cụ + chat Or… | 5 | 30 → L3 | 21 / 1460 / 7 → L3 | **L3** | risk_path: supabase/migrations/20261008000000_order_customer_shipment.sql, supabase/migrations/20261008000100_chat_image | L3 |
| TASK-0036 Audit repo theo Product Master Prompt (… | 8 | 23 → L3 | 21 / 1321 / 6 → L3 | **L3** | risk_path: supabase/functions/expire-chat-images/index.ts, supabase/migrations/20261009000000_chat_images_expiry.sql; kí | L3 |

**So với Dung: lệch 0/8** ; **hạ thấp L3: 0** . Cổng v0.2: lệch ≤ 1/10 và không hạ thấp L3.
