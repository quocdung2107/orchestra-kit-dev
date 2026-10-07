# PHASE 3 — Hook UserPromptSubmit + `orc approve` (H7); PreToolUse guard ở shadow

Nguồn: v0.2 mục O (phase 3), N1, N2, K3, W1.6, W2.3, W2.4, W3; ADJUSTMENTS #3 (SAFE_MODE thay
`ORC_GUARD=off`), #4 (approval bind TASK + PLAN_HASH + WRITE_SCOPE_HASH + LEVEL + RISK_FLAGS + NONCE).

## Phạm vi

1. **Hook `prompt_log` (UserPromptSubmit):** ghi `.orchestra/runtime/prompts.jsonl` một dòng mỗi lời Dung:
   `ts, session_id, sha256(prompt)`, chỉ giữ nguyên văn các dòng `orc:<lệnh> ...` (W2.4), chuỗi hash `prev`.
   Không chặn, không làm hỏng phiên (thoát 0).
2. **Phê duyệt (ADJUSTMENTS #4):**
   - `orc approval request TASK`: tính binding `{task, plan_hash, write_scope_hash, level, risk_flags}`, sinh
     nonce dùng một lần, in đúng một dòng Dung phải gõ: `orc:approve TASK-x <NONCE>` + tóm tắt 1 dòng (W2.3).
   - `orc approve TASK`: chỉ thành công khi `prompts.jsonl` có dòng `orc:approve TASK-x <NONCE>` của Dung,
     ghi **sau** lúc tạo yêu cầu, nonce chưa dùng, và binding tính lại **khớp** binding lúc yêu cầu.
     Ghi approval vào `state/approvals.yaml` + journal.
   - `orc approval check TASK`: approval còn hiệu lực không; plan, write_scope, level hoặc risk_flags đổi ⇒ hết hiệu lực.
   - Phase 3 **chưa** bắt buộc approval: `orc advance <task coder> --to dispatched` ghi vào shadow log
     "lẽ ra cần approval" khi thiếu/hết hiệu lực (bật thật ở Phase 4 với state machine).
3. **Guard PreToolUse ở shadow** (`hooks/guard`): đọc `runtime/active.json` (orc ghi mỗi lần lưu registry; JSON,
   không YAML — W3), quyết định theo bảng N1 ánh xạ trạng thái 0.1.0 (coder dispatched ≈ IMPLEMENTING, researcher
   dispatched ≈ RESEARCH/PLAN, in_review ≈ VERIFYING, không task đang chạy = bình thường) + `deny_always`.
   Shadow: **luôn cho qua**, ghi `runtime/guard-shadow.jsonl` (tool, đích, quyết định, lý do, agent_type, độ trễ).
   Lỗi trong guard: shadow ghi "lẽ ra chặn (lỗi)"; chế độ thật (Phase 4) sẽ exit 2 (fail-closed).
4. **SAFE_MODE (ADJUSTMENTS #3):** biến môi trường `ORC_SAFE_MODE=1` do Dung đặt trước khi mở VS Code
   (LLM không đổi được env của tiến trình Claude Code). Khi bật:
   - guard chỉ cho Edit/Write vào thư mục kit và `.orchestra/config.yaml`; Bash chỉ lệnh đọc, `orc` chỉ đọc, và
     lệnh chạy trong thư mục kit; đường quyết định này không đọc state (chạy được cả khi orc/state hỏng);
   - `orc` từ chối mọi lệnh đổi workflow (`new, set, advance, apply, next, approve, approval request, verify,
     handoff open, ctx seal`); lệnh đọc vẫn chạy;
   - brief ghi cảnh báo SAFE_MODE mỗi phiên.
   Không có `ORC_GUARD=off`.
5. Đo độ trễ hook guard và prompt_log trên máy này (W3, cổng phase 3: < 300 ms/tool call).

Ngoài phạm vi: bật chặn thật; approval cho DEC/ART; cài hook vào `~/.claude` (bước release).

## Acceptance criteria

- AC-3.1: prompt_log ghi đúng: không lưu nguyên văn dòng thường, giữ dòng `orc:`; chuỗi hash; không có `.orchestra` → no-op.
- AC-3.2: `orc approve` thất bại khi: không có lời Dung; nonce sai; nonce đã dùng; lời Dung trước lúc yêu cầu;
  plan/scope/level/risk đổi sau yêu cầu. Thành công khi đủ điều kiện; `approval check` hết hiệu lực khi binding đổi.
- AC-3.3: Guard shadow quyết định đúng các ca của N1 + deny_always, luôn exit 0 không chặn, ghi log.
- AC-3.4: SAFE_MODE: guard chỉ cho kit + config; `orc` từ chối lệnh đổi workflow, lệnh đọc vẫn chạy.
- AC-3.5: Độ trễ guard đo trên Windows (python trực tiếp và qua Git Bash), có số.
- AC-3.6: Toàn bộ test xanh; 0.1.0 vẫn chạy.
- AC v0.2 cần dữ liệu thật — **boundary, dừng**: "số lần guard lẽ ra chặn trong 10 task được Dung xem".

## Cách test

`tests/test_phase3.py` (hook qua subprocess với JSON stdin như Claude Code), `tools/phase3_latency.py`.

## Kết quả

Code mới: `cli/orc_guard.py` (guard + nhật ký lời Dung, chỉ stdlib), `cli/orc_approval.py`, `hooks/guard`,
`hooks/prompt_log`, `tools/phase3_latency.py`, `tools/phase3_shadow_report.py`. `cli/orc_core.py`: `active.json`,
`orc approve`, `orc approval request|check`, SAFE_MODE, shadow approval khi giao task coder, trường tuỳ chọn
`level, risk_flags` của task (cần cho binding #4; `orc set` không đổi được; triage điền ở Phase 5). `SCHEMA.md` §8, §8b.

Độ trễ (máy này, 30 lần/dòng, `tools/phase3_latency.py`):

| Cách gọi | median | p90 | max |
|---|---|---|---|
| `python -c pass` (mốc) | 27 | 27 | 31 |
| guard: python trực tiếp | 49 | 50 | 54 |
| prompt_log: python trực tiếp | 57 | 58 | 61 |
| guard: qua Git Bash (cách Claude Code chạy hook trên Windows) | 76 | 78 | 99 |

Quyết định bên trong guard: ~0.4 ms. Cổng < 300 ms/tool call: **đạt** (đo tổng hợp; số thật khi chạy trong
Claude Code ghi ở cột `ms` của shadow log, chỉ phần trong guard).

Chọn thiết kế theo ADJUSTMENTS:
- #3: không có `ORC_GUARD=off`. SAFE_MODE là biến môi trường của tiến trình Claude Code (LLM không đặt được cho hook);
  đường quyết định SAFE_MODE không đọc state nên vẫn chạy khi `active.json`/registry hỏng (có test).
- #4: binding gồm đủ 6 phần; nonce `secrets.token_hex(3)`; yêu cầu mới làm yêu cầu cũ `expired`; approval dùng
  rồi hết hiệu lực khi binding đổi (`approval check`).
- #8: guard là ranh giới + phát hiện; Bash allowlist chỉ nhìn chuỗi lệnh (`python -c`, script npm vẫn ghi được);
  V2 (`orc verify`) bắt sau.

Giới hạn còn lại:
- `prompts.jsonl` nằm ở `runtime/` cùng user: chuỗi hash phát hiện sửa/xoá dòng cũ, **không ngăn** thêm dòng giả mới.
  Phase 4 guard chặn tool ghi vào `runtime/`; script Python vẫn lách được (v0.2 N2).
- Nonce do orc in ra nên LLM cũng thấy: nonce chống dùng lại/nhầm task, không chống giả mạo.
- Bash allowlist chỉ là xấp xỉ (tách theo `&& || ; |`, chặn chuyển hướng `>`), có thể chặn sai lệnh lạ —
  đó là thứ shadow cần đo.
- Ánh xạ trạng thái 0.1.0 → mode là tạm (state machine K ở Phase 4).

## Test

`python -m unittest discover -s tests`: **120 passed + 1 skipped (Ran 121)** — 101 cũ + 20 mới (`tests/test_phase3.py`).

## AC

- AC-3.1 đạt. AC-3.2 đạt (không lời Dung, nonce sai, "ok" chung chung, nonce đã dùng, lời trước yêu cầu, plan/
  scope/level/risk đổi, nhật ký bị sửa). AC-3.3 đạt. AC-3.4 đạt. AC-3.5 đạt (bảng trên). AC-3.6 đạt.
- **Cổng v0.2 cần dữ liệu thật — DỪNG ở boundary:** "số lần guard lẽ ra chặn trong 10 task được Dung xem".
  Chưa sang Phase 4.

## Cách Dung bật thử (bước release, cần Dung duyệt — tôi không tự làm)

Khuyên: thử trên `D:\WMS` thật để có 10 task thật, sau khi commit `.orchestra/` (để quay lui — FINDING-5).

1. Commit `D:\WMS\.orchestra` hiện tại; sao lưu `~/.claude/settings.json`.
2. Cho kit đang chạy dùng bản phase-3 (junction agents/commands, PATH `orc`, hook cũ đều trỏ `C:\Users\quocd\orchestra-kit`):
   `git -C C:\Users\quocd\orchestra-kit checkout phase-3` (detached; nhánh `v0.2` đang mở ở worktree nên dùng tag).
3. Thêm 2 hook vào `D:\WMS\.claude\settings.local.json` (chỉ dự án WMS), giữ nguyên hook cũ ở `~/.claude`:
   ```json
   {"hooks": {
     "UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 10,
       "command": "\"C:/Users/quocd/AppData/Local/Python/pythoncore-3.14-64/python.exe\" \"C:/Users/quocd/orchestra-kit/hooks/prompt_log\""}]}],
     "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "timeout": 10,
       "command": "\"C:/Users/quocd/AppData/Local/Python/pythoncore-3.14-64/python.exe\" \"C:/Users/quocd/orchestra-kit/hooks/guard\""}]}]
   }}
   ```
4. (Tuỳ chọn, để có số liệu Phase 2) thêm vào `D:\WMS\.orchestra\config.yaml`:
   ```yaml
   verify:
     repos: [".", "app"]
     commands:
       test: {run: "npm run test", cwd: app}
       build: {run: "npm run build", cwd: app}
       lint: {run: "npm run lint", cwd: app}   # hiện bị Application Control chặn (FINDING-4)
   ```
5. Làm 10 task như thường (/auto). Khi muốn duyệt: `orc approval request TASK-x` → gõ dòng `orc:approve ...` nó in ra.
6. Xem kết quả: `python C:\Users\quocd\orchestra-kit\tools\phase3_shadow_report.py --project D:\WMS`,
   đánh dấu từng dòng "chặn đúng/chặn sai".

Quay lui: `git -C C:\Users\quocd\orchestra-kit checkout main`; xoá 2 hook ở bước 3; dữ liệu `.orchestra` về commit
ở bước 1 (FINDING-5).

## Shadow trên D:\WMS (Dung duyệt 2026-10-07)

Đổi so với "Cách Dung bật thử" ở trên: **không** checkout `phase-3` ở kit đang chạy (sẽ đổi workflow thật:
`orc set` → `orc advance`, trường registry mới — FINDING-5). Kit đang chạy giữ `main` (0.1.0); chỉ 2 hook
(UserPromptSubmit, PreToolUse) trỏ tới worktree tag `phase-3-shadow`, khai ở `D:\WMS\.claude\settings.local.json`
(thêm vào `.git/info/exclude` để không lẫn vào commit). Guard tự dựng `runtime/active.json` từ registry khi registry
đổi (orc 0.1.0 không ghi file này). Lỗi hook ghi `runtime/hook-errors.jsonl`. Báo cáo loại phiên triển khai kit
(`--exclude-session`). Test: **122 passed + 1 skipped** (thêm 2 test: dựng active.json trên dự án 0.1.0, ghi lỗi hook).
