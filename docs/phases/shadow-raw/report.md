# Shadow guard — tóm tắt

Tool call đã thấy: 511; lẽ ra chặn: 110; phiên: 1; agent_type: ['None', 'coder', 'context-builder', 'researcher', 'reviewer']

Thời gian quyết định trong guard: median 0.5 ms, max 125.1 ms (không gồm khởi động Python — xem tools/phase3_latency.py).

## Lẽ ra chặn theo mode và lý do

| Mode | Lý do | Số lần | Ví dụ |
|---|---|---|---|
| verify | verify: lệnh ngoài allowlist | 38 | `cd /d/WMS/app && (npm run build 2>&1 \| tail -8; npm run test 2>&1 \| tail -15; ` |
| implement | implement: lệnh ngoài allowlist | 25 | `cd /d/WMS/app && cat src/shared/inventory/uom.ts \| head -40; cat tsconfig.app.j` |
| implement | implement: ghi file bằng chuyển hướng shell | 17 | `mkdir -p /d/WMS/app/src/features/pick-orders && cd /d/WMS/app/src/features/pick-` |
| research | research: lệnh ngoài allowlist | 13 | `cat .orchestra/knowledge/KNOWLEDGE_MAP.md \| head -80; ls app/src/features/* sup` |
| verify | verify: ghi file bằng chuyển hướng shell | 12 | `cat >> .orchestra/artifacts/ART-0033.md <<'EOF'

## Kết luận
PASS (migration chư` |
| research | research: ghi file bằng chuyển hướng shell | 3 | `python - <<'EOF'
p='.orchestra/artifacts/ART-0030.md'
s=open(p,encoding='utf-8')` |
| implement | deny_always: supabase db push | 1 | `mkdir -p supabase/functions/expire-chat-images && cat > supabase/migrations/2026` |
| implement | implement: ghi ngoài dự án | 1 | `C:\Users\quocd\AppData\Local\Temp\claude\d--WMS\a7876150-44bd-4aaf-9fba-a92bd869` |

## Approval (shadow)

Giao task coder khi chưa có approval hợp lệ: 0 lần

## Lỗi hook

0 lỗi
Lời Dung đã ghi (prompts.jsonl): 52; phiên bị loại khỏi thống kê: ['883fcd3d-e75a-4804-8432-b3215e4b5a8c', 'smoke-test']

Dung đánh dấu từng dòng: chặn đúng / chặn sai. Chặn sai > 0 ⇒ sửa bảng guard trước Phase 4.
