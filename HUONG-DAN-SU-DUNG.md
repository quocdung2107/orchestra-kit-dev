# Hướng dẫn dùng orchestra-kit hằng ngày

Áp dụng cho dự án kho `D:\WMS`. Kit đã cài; không cần chạy lại `install.py`.

## Lần đầu sau khi cài (làm 1 lần)

1. **Đóng hẳn VS Code rồi mở lại** (để Claude Code nhận PATH, hook, agent, lệnh mới).
2. Mở thư mục `D:\WMS` trong VS Code (File → Open Folder). Mở thư mục gốc `D:\WMS`,
   không mở `D:\WMS\app`, để `CLAUDE.md` và `.orchestra/` được dùng đúng.
3. Mở terminal trong VS Code, gõ `orc next`. Thấy chữ `NEXT:` là PATH đã đúng.

## Cách nhanh: một lệnh `/auto` (khuyên dùng)

1. Bấm **New session** trong Claude Code.
2. Gõ: `/auto <mô tả yêu cầu>`, ví dụ `/auto B2: chặn nạp file Excel/CSV lớn hơn 20 MB, báo lỗi dễ hiểu`.
3. Claude tự làm hết: ý tưởng → thiết kế → plan → code → review → commit vào nhánh `orchestra/TASK-x`
   trong `app/` (không merge, không push) → trả **một báo cáo** (bảng task, bằng chứng, giả định đã tự chọn,
   việc anh/chị cần thử tay).
4. Claude chỉ dừng hỏi khi plan đụng quy tắc nghiệp vụ / data model / kiến trúc, yêu cầu quá mơ hồ,
   reviewer báo xung đột quyết định, hoặc sửa quá 2 lần chưa đạt. Trả lời một từ là Claude chạy tiếp.
5. Đọc báo cáo, thử tay, rồi bảo Claude "merge và push".

## Cách từng bước (khi muốn kiểm soát từng khâu)

## Mỗi yêu cầu = 1 phiên mới (D5)

1. Trong khung Claude Code bấm **New session** (phiên mới).
2. Kiểm brief: hỏi *"Brief đầu phiên nói mục tiêu, quyết định và bước tiếp theo là gì?"*.
   Claude phải trả lời được ngay mà không đọc file.
3. Gõ `/next` để xem việc đang chờ.
4. Giao việc mới bằng `/plan <mô tả yêu cầu>`, ví dụ:
   `/plan B2: chặn nạp file Excel/CSV lớn hơn 20 MB, báo lỗi dễ hiểu`
   - Claude tự mở phiên S-x, tạo TASK, gọi agent **researcher** viết plan.
   - Claude dừng lại, báo đường dẫn `.orchestra/artifacts/ART-x.md`.
   - **Anh/chị mở file đó đọc plan**, rồi trả lời `duyệt` hoặc ghi điều cần sửa.
5. Sau khi duyệt: gõ `/run`. Agent **coder** làm task ready đầu tiên.
6. Khi Claude báo `ROUTE: ... /review TASK-x`: gõ `/review TASK-x`. Agent **reviewer** tự chạy
   build/test và kết luận. Claude làm theo dòng `ROUTE:` (đạt → done; lỗi → trả coder,
   lập lại plan, hoặc hỏi anh/chị).
7. Kết thúc: gõ `/handoff`. Nếu quên, hook Stop sẽ chặn và nhắc điền handoff (tối đa 3 lần).
8. Nhờ Claude commit: *"commit .orchestra trong D:\WMS; code trong app/ commit trên nhánh mới"*.
   Anh/chị tự thử tay rồi bảo Claude merge/push như lần B1.

Yêu cầu tiếp theo: **bấm New session lần nữa**, không làm tiếp trong phiên cũ.

## Gợi ý vài lần test

| Lần | Gõ | Kiểm điều gì |
|---|---|---|
| 1 | `/auto B2: chặn file > 20 MB` | Chạy trọn không dừng, nhận 1 báo cáo |
| 1b | `/auto đổi trạng thái đơn hàng thành 4 bước` | Phải dừng hỏi (đụng quy tắc nghiệp vụ) |
| 2 | Giữa chừng (sau `/run`) đóng VS Code, mở phiên mới, hỏi *"đang làm dở gì?"* | Liền mạch nhờ brief + handoff |
| 3 | `/plan B3: nút xoá toàn bộ dữ liệu trên máy` | Plan có nhiều task, `blocked_by` |
| 4 | Trong phiên đã `/plan`, cố kết thúc mà không `/handoff` | Hook Stop chặn |
| 5 | Phiên chỉ hỏi một câu, không `/plan` | Hook Stop **không** chặn |

## Lệnh `orc` hay dùng (gõ trong terminal ở `D:\WMS`)

- `orc next` — task kế tiếp, việc cần anh/chị quyết.
- `orc brief` — xem brief mà Claude nhận đầu phiên.
- `orc show TASK-0002 --meta` — trạng thái một mục.
- `orc validate` — kiểm toàn bộ `.orchestra/`, phải in `OK`.

## Khi có trục trặc

- `orc` không chạy → chưa mở lại VS Code; hoặc dùng `python C:\Users\quocd\orchestra-kit\cli\orc ...`.
- Đầu phiên không có brief → kiểm `~/.claude/settings.json` có mục `hooks` chứa `orchestra-kit/hooks/`.
- Không thấy agent `researcher/coder/reviewer` → gõ `/agents`; nếu thiếu, kiểm `~/.claude/agents` còn trỏ tới kit.
- Hook Stop chặn mãi → mở `.orchestra/sessions/S-x.md`, điền đủ 5 mục, `result: done|partial|blocked`.
