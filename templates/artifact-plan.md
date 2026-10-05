
# Plan {{id}} (task {{task}})

## Mục tiêu
<!-- 1–3 câu: tính năng này giải quyết việc gì cho ai -->

## Phạm vi
<!-- Làm / không làm -->

## Tiêu chí chấp nhận
<!-- Mỗi dòng một tiêu chí, có ID để task trỏ tới dạng {{id}}#AC-n.
     Tiêu chí phải kiểm được bằng test hoặc thao tác cụ thể. -->
- AC-1: ...

## Thiết kế
<!-- File sẽ sửa, luồng dữ liệu, rủi ro -->

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
