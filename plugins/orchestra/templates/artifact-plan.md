
# Plan {{id}} (task {{task}})

## Mục tiêu
<!-- 1–3 câu: tính năng này giải quyết việc gì cho ai -->

## Ý tưởng
<!-- 2–3 phương án ngắn gọn, phương án chọn và lý do (đơn giản nhất đủ dùng) -->

## Phạm vi
<!-- Làm / không làm -->

## Tiêu chí chấp nhận
<!-- Mỗi dòng một tiêu chí, có ID để task trỏ tới dạng {{id}}#AC-n.
     Tiêu chí phải kiểm được bằng test hoặc thao tác cụ thể. -->
- AC-1: ...

## Thiết kế
<!-- File sẽ sửa, luồng dữ liệu, rủi ro. Giả định tự chọn ghi rõ "Giả định: ..." -->

## Cần Dung quyết
<!-- Chỉ ghi điều KHÔNG thể tự quyết: đổi quy tắc nghiệp vụ, data model, kiến trúc,
     phạm vi mơ hồ đến mức không chọn được mặc định hợp lý, hoặc việc không đảo ngược được.
     Mỗi dòng một câu hỏi kèm phương án khuyên dùng. Không có thì ghi đúng: Không có -->
Không có

## Task
<!-- orc tạo task từ khối dưới khi plan được accepted: `orc new task --from {{id}}`.
     key: tên cục bộ để blocked_by trỏ tới; acceptance: AC-n của plan này. -->
```yaml orc-tasks
- key: t1
  title: ...
  owner: coder
  acceptance: [AC-1]
  write_scope: ["app/src/..."]
  blocked_by: []
```
