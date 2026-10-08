# PHASE 3 — Kết quả shadow trên D:\WMS (2026-10-07 → 2026-10-08)

Cấu hình: kit đang chạy giữ `main` (0.1.0); chỉ 2 hook (UserPromptSubmit, PreToolUse) từ worktree tag
`phase-3-shadow`, khai ở `D:\WMS\.claude\settings.local.json`. Không chặn tool call nào, không đổi workflow.
Dữ liệu: 17 task thật (TASK-0029..0045; 12 coder, 5 researcher), 1 phiên làm việc (`a7876150…`), 511 tool call.
Loại khỏi thống kê: phiên triển khai kit (`883fcd3d…`) và lần chạy thử `smoke-test`.
Dữ liệu thô: `docs/phases/shadow-raw/` (guard-shadow.jsonl, prompts.jsonl, report.md).

## would_block: 110 / 511

| Nhóm | Số | Đánh giá |
|---|---|---|
| Tách lệnh sai trong chuỗi/heredoc/regex `\|`, subshell `( )` | 68 | false positive (lỗi parser) |
| Ghi file bằng Bash (heredoc, `python - <<EOF`, `sed -i`), đích trong write_scope/artifact của task | 38 | đúng chính sách N1, không có hại; sẽ phá workflow nếu enforce |
| Lệnh chỉ đọc thiếu trong allowlist (`cut`, `git check-ignore`) | 2 | false positive |
| `deny_always: supabase db push` khớp chữ trong nội dung migration | 1 | false positive |
| Write vào scratchpad tạm của Claude (ngoài dự án) | 1 | false positive (thực tế vô hại) |

Chặn đúng một thao tác nguy hiểm/ngoài phạm vi: **0**. Edit/Write qua tool (38 lần): 0 lần sai.
Đối chiếu tự động 47 đích ghi qua Bash: mọi đích trong mode implement/verify/research đều thuộc write_scope hoặc
artifact của task; 16 dòng "ngoài" là CTX do context-builder ghi khi chưa có task chạy (mode normal) hoặc đường
dẫn script đối chiếu phân tích sai (`cd` lồng nhau).

## Quan sát khác

- W8 "hook chạy trong subagent, có agent_type": **xác nhận** — gặp `coder, context-builder, researcher, reviewer`.
- Tool lạ chưa có trong bảng: `SubagentHandback` (45), `Agent` (44), `SendMessage` (1) — guard cho qua (không ghi).
- H7 thấy thật: `orc new decision --status accepted` do LLM chạy (guard cho qua vì là `orc`).
- Approval shadow: 0 sự kiện (orc 0.1.0 không gọi kiểm approval). prompts.jsonl: 52 lời, 0 dòng `orc:`.

## Độ trễ

- Phần quyết định trong guard (511 lần): median 0.5 ms, p90 79.7 ms, max 125.1 ms. 60 lần > 50 ms đều là lúc
  guard tự dựng `active.json` từ YAML (chỉ có ở shadow trên orc 0.1.0).
- Tổng mỗi tool call ước tính: khởi động hook qua Git Bash median 76 ms (đo tổng hợp, `tools/phase3_latency.py`)
  + phần trên ⇒ thường ~77 ms, xấu nhất ~200 ms. Không đo được tổng thật từ bên trong Claude Code.

## Lỗi hook

0 (không có `hook-errors.jsonl`; không có dòng `mode: error`).

## Khôi phục

Đã xoá `D:\WMS\.claude\settings.local.json`, gỡ dòng trong `.git/info/exclude`, xoá `runtime/active.json`,
`guard-shadow.jsonl`, `prompts.jsonl` (đã chép bản sao). `git status` của `D:\WMS` và `D:\WMS\app` sạch;
`~/.claude` không đổi trong suốt shadow. Commit của Dung trong thời gian shadow giữ nguyên.

FINDING mới: FINDING-6 (Bash allowlist).
