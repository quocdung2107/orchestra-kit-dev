# Context {{id}} (task {{task}})

<!-- Context Builder điền. Đây là GỢI Ý để coder/reviewer bắt đầu đúng chỗ, không phải sự thật cuối cùng:
     trước khi dùng phải chạy `orc ctx check {{id}}`; file báo đổi thì đọc lại từ đĩa. -->

## File chọn
<!-- Khối dưới do `orc ctx seal` đọc. source: graph (graph fresh) | fallback (không graph / stale / lỗi).
     Tối đa max_files file (mặc định 12); cắt bớt thì truncated: true. Đường dẫn tương đối gốc dự án. -->
```yaml orc-context
source: fallback
truncated: false
files:
  - path: app/src/...
    reason: "..."
```

## Graph evidence
<!-- Kết quả `orc graph query/affected/explain` đã dùng (symbol, file:dòng, quan hệ). Fallback: lệnh tìm kiếm đã chạy. -->

## Vùng rủi ro
<!-- Nơi có thể bị ảnh hưởng nhưng không chọn vào context (hub UI, SQL/RLS qua RPC chuỗi, test liên quan). -->

## Giới hạn context
<!-- Trạng thái graph lúc dựng; graph không phủ RPC bằng chuỗi (TS → SQL); hàm SQL định nghĩa lại
     ở migration mới hơn; những gì đã cắt vì budget. -->
