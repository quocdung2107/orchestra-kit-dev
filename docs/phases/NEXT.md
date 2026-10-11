# Việc tiếp theo — Orchestra v0.2 (chốt 2026-10-11)

## Trạng thái hiện tại

- Kit đang chạy: `C:\Users\quocd\orchestra-kit` checkout tag **rc-k-2** (detached). Code ở nhánh `v0.2` của worktree
  `C:\Users\quocd\orchestra-kit-v02`; tag `phase-0` … `phase-5`, `rc-k-1`, `rc-k-2`. Test: 166 passed + 1 skipped. Chưa push.
- WMS: `workflow: k` bật (commit `a8c658d`); `verify:` test/build/lint trong `app`; triage **shadow**; hook ghi lời Dung
  + guard **shadow** ở `D:\WMS\.claude\settings.local.json` (gitignore cục bộ). Koinonia: dùng kit mới, chưa bật K
  (`/auto` tự chạy `auto-legacy`).
- Đã xong: Phase 0–3, Phase 4 (FINDING-6, H7, F2–F5), Phase 4b (state machine K, phương án A), Phase 5 (triage shadow,
  hiệu chỉnh B + từ khoá, hồi cứu lệch 0/8).

## Việc ngay (Dung)

1. Dọn TASK-0051: phiên mới trong `D:\WMS` → gửi dòng riêng `orc:abort TASK-0051` → bảo Claude `orc abort TASK-0051`.
2. Dùng `/auto <mô tả>` cho yêu cầu mới; duyệt bằng dòng `orc:approve …` orc in ra (chép nguyên, dòng riêng).

## Việc tiếp theo (theo thứ tự)

| # | Việc | Ai | Cổng / điều kiện |
|---|---|---|---|
| 1 | Chạy ~10 yêu cầu K thật trên WMS | Dung | — |
| 2 | Bảng triage shadow sống vs mức Dung đánh giá (kiểm độc lập Phase 5) | Claude lập, Dung điền | lệch ≤ 1/10, không hạ thấp L3 ⇒ bật triage thật (ghi `task.level`, mở READY_FOR_IMPLEMENTATION cho L0/L1) |
| 3 | Báo cáo guard shadow trên luật mới (FINDING-6) qua 10 yêu cầu | Claude | 0 chặn sai ⇒ đề xuất bật guard thật (fail-closed, SAFE_MODE) — Dung duyệt riêng |
| 4 | Phase 6: research artifact v2 (claim FACT/INFERENCE + kiểm trích dẫn) + Context Compiler tất định; đo A/B graph ở Koinonia | Claude | cần Dung duyệt bắt đầu |
| 5 | Phase 7: gộp researcher/coder vào mode Main (L0–L1 trước), giữ reviewer độc lập, thêm researcher-external | Claude | chỉ số Phase 0 tốt hơn |
| 6 | Phase 8: dọn nguồn sự thật (rules → `.claude/rules`, KNOWLEDGE_MAP/HANDOFF/VIEC → archive/view, DEC có `topic`) | Claude | `orc docs check` sạch |
| 7 | Release chính thức: merge `v0.2` → `main`, sửa FINDING-1 (install.py), cài hook qua `install.py` | Dung duyệt | sau 2–3 |

## Rủi ro còn mở

- Bash / `python -c` vẫn ghi được ngoài phạm vi và gọi API nội bộ (chỉ phát hiện sau: `orc verify`, journal).
- `prompts.jsonl` chống sửa dòng cũ, không chống thêm dòng giả; nonce chỉ chống dùng lại.
- DONE → INTEGRATED chỉ ghi nhận; reviewer chưa ép phiên mới/model khác (Phase 7).
- Triage chỉ hiệu chỉnh trên 8 mẫu cũ — chưa kiểm độc lập.
- FINDING-1 (install.py nhận hook theo tên thư mục) còn mở.

Quay lui: `git -C C:\Users\quocd\orchestra-kit checkout main`; revert `a8c658d` ở WMS; xoá `D:\WMS\.claude\settings.local.json`;
dữ liệu có task K: `tools/rollback_v02_to_v01.py` (dry-run trước).
