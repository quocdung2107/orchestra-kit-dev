# SCHEMA — orchestra-kit 0.1.0

Hệ đa-agent dạng blackboard: trạng thái sống trong file (.md/.yaml + git), agent
truyền nhau ID. Quyết định nền tảng D1–D8 do Dung chốt 2026-10-05.

## 1. Vai trò

| Vai trò | Hiện thực | Đọc | Ghi |
|---|---|---|---|
| A Orchestrator | Phiên Claude Code chính + lệnh /auto (trọn vòng) hoặc /plan /run /review /next /handoff | brief, `orc show --meta`, `orc next` (chỉ metadata — D3) | chỉ qua `orc` |
| B Researcher | subagent `researcher` | task, plan cũ, code, tài liệu | thân file ART được cấp |
| C Coder | subagent `coder` (owner `coder`, `coder-1`, …) | task + acceptance, context | file trong `write_scope` |
| D Reviewer | subagent `reviewer` | `orc show TASK --pack` (acceptance + outputs + evidence) | thân file ART review_report |
| Context Builder | subagent `context-builder` (bật từ DEC-0004) | task, plan, KNOWLEDGE_MAP, `orc graph ...` | thân file CTX được cấp |

Single writer (D4): chỉ `orc` ghi `.orchestra/state/`. Lệnh ghi giữ khoá `runtime/state.lock`, ghi file nguyên tử (tmp + rename); mọi đổi `status` ghi `state/journal.jsonl` (chuỗi hash, `orc validate` kiểm) — v0.2 phase 1. B/C/D trả **envelope YAML**; A nạp bằng `orc apply -`.

## 2. ID

`TASK-0001`, `ART-0001`, `DEC-0001`, `CTX-0001`, `EVD-0001`, `S-0001`. Đánh số tăng dần theo
từng dự án (lớn nhất hiện có + 1). `project_id` ở `.orchestra/config.yaml`.
Tiêu chí chấp nhận trỏ dạng `ART-0001#AC-2` tới dòng `- AC-2: ...` trong plan.

## 3. Cấu trúc

```
~/orchestra-kit/                     (git repo riêng)
  cli/orc, cli/orc.cmd, cli/orc_core.py
  agents/{researcher,coder,reviewer,context-builder}.md   → junction ~/.claude/agents
  commands/{plan,run,review,next,handoff}.md              → junction ~/.claude/commands
  hooks/{session_start,stop_check}
  templates/  tests/  install.py  SCHEMA.md  README.md  VERSION

<dự án>/
  CLAUDE.md
  .orchestra/
    config.yaml            project_id, kit_version, goal
    state/{tasks,artifacts,decisions,contexts,evidence}.yaml   (registry, chỉ orc ghi)
    artifacts/ART-x.md     frontmatter + nội dung
    decisions/DEC-x.md     nội dung chi tiết quyết định
    contexts/CTX-x.md  evidence/EVD-x.md  sessions/S-x.md
    knowledge/KNOWLEDGE_MAP.md
    runtime/               dấu phiên đang mở (gitignore)
```

## 4. Registry (`state/*.yaml`, mỗi file là danh sách)

**Task**: `id, title, status, owner, blocked_by[], context[], inputs[], outputs[], acceptance[], write_scope[], attempts, summary, failure_class, needs_user, resume_status`
- status: `pending|ready|dispatched|in_review|done|failed|blocked`
- owner: `orchestrator|researcher|reviewer|coder|coder-N`
- `needs_user`, `resume_status` (thêm ngoài đặc tả): cờ "hỏi Dung" và trạng thái quay về khi hết bị chặn.

**Artifact** (registry = frontmatter của file, phải khớp từng trường):
`id, type(plan|research|code_patch|review_report), task, version, supersedes, status(draft|accepted|rejected), summary, depends_on[], paths[]`

**Decision**: `id, status(proposed|accepted|superseded), scope, summary, supersedes`.
Accept một DEC có `supersedes` → orc tự chuyển DEC cũ sang `superseded`.

**Context**: `id, task, summary, paths[]` · **Evidence**: `id, task, kind(test|lint|build|manual|other|typecheck|scope), result(pass|fail|info), summary, paths[], by(agent|orc)` — `typecheck|scope` và `by: orc` chỉ do `orc verify` tạo; mục cũ thiếu `by` = agent

`summary` ≤ 200 ký tự ở mọi nơi.

## 5. Envelope (subagent → A)

Chỉ YAML (cho phép bọc trong ```` ```yaml ````), không khoá lạ:

```yaml
msg: result
task_id: TASK-0003
status: done            # done | partial | blocked | failed
outputs: []             # ID, hoặc đường dẫn tương đối gốc dự án
evidence: []            # EVD-ID, hoặc {kind, result, summary, paths} → orc tạo EVD
proposed_decisions: []  # chuỗi, hoặc {summary, scope, supersedes} → orc tạo DEC proposed
summary: "≤200"
failure_class: null     # chỉ reviewer
```

## 6. Định tuyến tất định (`orc apply`)

| Lúc nhận | Kết quả | Task thành |
|---|---|---|
| dispatched, owner coder | done | `in_review` → /review |
| dispatched, owner khác | done | `done` |
| dispatched | partial | `ready` |
| dispatched | blocked / failed | `blocked` / `failed` + needs_user |
| in_review | done, không failure_class | `done` |
| in_review | IMPL_BUG | attempts+1 → `ready` (về coder); attempts > 2 → `blocked` + needs_user |
| in_review | SPEC_GAP | tạo task researcher "Lập lại plan" (plan mới `--supersedes`); task gốc `blocked`, resume `ready` |
| in_review | DECISION_CONFLICT | `blocked` + needs_user |
| in_review | REGRESSION | chặn merge; tạo task coder sửa; task gốc `blocked`, resume `in_review` |

Coder trả file ngoài `write_scope` → orc từ chối cả envelope, không ghi gì.
`orc next`: `pending` có blocked_by đều `done` → `ready`; `blocked` (không needs_user) hết chặn → `resume_status`.

## 6b. Chế độ tự chạy `/auto` (Dung yêu cầu 2026-10-05)

Hai chặng (Dung chốt lại 2026-10-05):

1. **Hiểu yêu cầu & thiết kế — luôn dừng.** Researcher viết ART `research` 4 mục: Tôi hiểu yêu cầu là ·
   Thiết kế sơ bộ · Chưa rõ / thiếu thông tin · Câu hỏi cho Dung. A gửi Dung nguyên văn `orc ask ART-x`.
   Câu trả lời của Dung → DEC **proposed** (scope = ART research); A chạy `orc approval request <ART> <DEC...>`,
   Dung gõ dòng `orc:approve ...`, `orc approve` đưa ART research + DEC sang accepted (H7, v0.2 phase 4).
2. **Plan → code → review → báo cáo — tự chạy.** Task plan có inputs = ART research + DEC; `orc gate` →
   tự accept plan → vòng coder/reviewer theo `orc next` + `ROUTE:` → commit nhánh `orchestra/<ROOT>`
   (không merge/push) → handoff → trả `orc report <task plan>`. Chỉ dừng khi: `orc gate` = ASK, `HỎI DUNG`,
   envelope bị từ chối 2 lần, lỗi môi trường.

`orc ask ART-x` từ chối nếu ART không phải research hoặc còn mục chưa điền.

## 7. Phiên và handoff (D5)

- Hook **SessionStart** nạp `orc brief` (≤ 6000 ký tự ≈ 1.5k token) kèm khoá phiên Claude (`session_id`).
- Khi phiên nhận yêu cầu có tạo/làm task: `orc handoff open --key <session_id> --role ... --task ... --request "..."`
  → tạo `sessions/S-x.md` (result `pending`) + dấu ở `runtime/`.
- Hook **Stop** chỉ chặn khi phiên đã mở S-ID (Dung chốt Q4) và handoff chưa hợp lệ. Chặn tối đa 3 lần
  rồi cho dừng (chống vòng lặp vô hạn theo khuyến cáo trong tài liệu hooks).
- Handoff hợp lệ: frontmatter `id, task, role, result(done|partial|blocked)` + đủ 5 mục
  `## Đã làm`, `## File thay đổi`, `## Quyết định phát sinh`, `## Câu hỏi mở`, `## Bước tiếp theo`
  (mục trống ghi "Không có").
- Cả hai hook no-op khi không tìm thấy `.orchestra/config.yaml` ở cwd hay thư mục cha, và không bao giờ
  làm hỏng phiên khi kit lỗi (thoát 0).

## 8. Lệnh `orc`

| Lệnh | Việc |
|---|---|
| `orc init --project-id X --goal "..."` | tạo `.orchestra/`; tạo CLAUDE.md chỉ khi chưa có |
| `orc brief [--key K]` | brief ≤ ~1.5k token |
| `orc new task|artifact|decision|context|evidence ...` | tạo mục, in ID; `orc new task --from ART-x` tạo task từ khối ```` ```yaml orc-tasks ```` của plan đã accepted |
| `orc set ID k=v ...` | sửa trường (giá trị đọc như YAML: `[a,b]`, `true`); **không** đổi `status, level, attempts, failure_class, needs_user, resume_status, approved_*` (v0.2 phase 1, H1) |
| `orc advance ID --to X` | đổi trạng thái theo bảng chuyển: TASK `pending/ready→dispatched` (blocked_by xong), `dispatched→ready`, `blocked(needs_user)/failed→ready`, researcher `done→dispatched`; ART `draft→accepted/rejected` (trừ ART research: chỉ qua `orc approve`); DEC: không có — chỉ `orc approve` (H7) |
| `orc new decision` | chỉ tạo DEC `proposed`; `--status accepted/superseded` bị từ chối (H7). `orc set` không sửa `summary/scope/supersedes` của DEC đã accepted |
| `orc show ID [--meta] [--pack]` | `--meta` cho A; `--pack` cho reviewer |
| `orc approval request ID...` | (v0.2 phase 3–4) binding từng ID — TASK: `plan_hash + write_scope_hash + level + risk_flags`; DEC: nội dung; ART: thân — sinh nonce dùng một lần, in dòng Dung phải gõ `orc:approve ID1,ID2 NONCE` (một lần duyệt nhiều ID) |
| `orc approve ID...` | chỉ khi hook UserPromptSubmit đã ghi đúng dòng đó của Dung sau lúc yêu cầu, nonce chưa dùng, mọi binding không đổi: DEC `proposed→accepted` (DEC cũ superseded), ART `draft→accepted`, TASK ghi approval; `state/approvals.yaml` + journal. **Đường duy nhất tạo DEC accepted** |
| `orc approval check TASK` | approval còn hiệu lực? plan/scope/level/risk đổi ⇒ hết (exit 3) |
| `orc verify TASK` | V1/V2 tất định (v0.2 phase 2): so file đổi kể từ checkpoint (tạo khi `advance → dispatched` task coder, chụp cả mục `verify:` của config) với write_scope, quét risk_paths/bí mật, chạy `test/typecheck/lint/build` từ bản chụp (env bỏ biến kiểu secret, cwd trong dự án, timeout); tạo EVD `by: orc`, in `LỆCH` so với EVD tự khai. Mỗi lệnh: pass / `TEST|LINT|BUILD|TYPECHECK_FAILURE` / `ENVIRONMENT_FAILURE` (Application Control chặn, thiếu native binding, không tìm thấy lệnh, exit 126/127 — EVD `info`, không tính LỆCH). Exit 0 PASS, 6 FAIL, 7 INCOMPLETE (chỉ lỗi môi trường). Không đổi trạng thái task |
| `orc next` | thăng hạng task, in READY/REVIEW/HỎI DUNG/NEXT |
| `orc apply FILE|-` | nạp envelope, định tuyến, in `ROUTE:` (thêm ngoài đặc tả: cần để giữ D4) |
| `orc handoff open|check` | mở/kiểm handoff phiên |
| `orc gate ART-x` | plan tự chạy tiếp được không: `PROCEED`, hoặc `ASK` + lý do (thoát mã 3): mục `## Cần Dung quyết` có câu hỏi, quyết định proposed của task/plan, thiếu AC hoặc orc-tasks, plan còn nguyên mẫu |
| `orc report TASK-x` | báo cáo tất định cho một yêu cầu: plan, bảng task, bằng chứng, review, quyết định, kết luận |
| `orc validate [--handoff] [--key K]` | từ chối: frontmatter sai, ID trùng, summary > 200, tham chiếu ID không tồn tại, enum sai, file mồ côi |

## 8b. Guard, phê duyệt, SAFE_MODE (v0.2 phase 3 — shadow)

- Hook **UserPromptSubmit** `hooks/prompt_log` → `runtime/prompts.jsonl`: ts, session, sha256 lời Dung, nguyên văn chỉ
  các dòng `orc:...`; chuỗi hash. Hook **PreToolUse** `hooks/guard` → `runtime/guard-shadow.jsonl` (shadow: luôn cho
  qua). Guard đọc `runtime/active.json` (orc ghi mỗi lần lưu registry), không nạp YAML.
- `orc advance <task coder> --to dispatched` thiếu approval hợp lệ ⇒ ghi `runtime/shadow.jsonl` (chưa chặn).
- `ORC_SAFE_MODE=1` (Dung đặt trước khi mở VS Code): guard chỉ cho Edit/Write vào kit + `.orchestra/config.yaml`; `orc`
  từ chối lệnh đổi workflow; brief cảnh báo. Không có biến tắt guard.
- **Phase 4 (FINDING-6, Dung chốt): Bash không phải semantic sandbox.** Guard Bash chỉ deny luật tin cậy cao (git
  push/merge/rebase/reset --hard/clean -f/branch -D, `supabase db push|reset`, deploy/publish, xoá đệ quy, psql ngoài
  localhost, ghi vào vùng deny_always, chạm file bí mật) trên lệnh đã bỏ thân heredoc và câu trong ngoặc. Không suy
  write_scope từ Bash; `orc verify` hậu kiểm. Edit/Write: deny_always (`.orchestra/` trừ `writable` của active.json,
  `.claude/`, `~/.claude/`, `.git/`, file bí mật, `guard.protected_paths`) + write_scope khi có task coder chạy.
- Khớp đường dẫn (write_scope, risk/guard/artifact paths): kiểu gitignore, neo ở gốc dự án — `*` không qua `/`,
  `**` nhiều cấp, đuôi `/` là thư mục (`orc_guard.match_path`, FINDING-3).
- Journal: lệnh `orc` ghi state bị từ chối ⇒ dòng `{event: rejected, task, operation, reason, reason_hash, actor, ts}` (F2).
- Quay lui dữ liệu về 0.1.0: `tools/rollback_v02_to_v01.py` (dry-run mặc định; F5).

## 9. Cú pháp Claude Code đã kiểm (2026-10-05)

Nguồn: code.claude.com/docs/en/hooks, /sub-agents, /slash-commands; Claude Code 2.1.289.
- Hook trong `settings.json`: `hooks.<Event>[].hooks[] = {type: "command", command, timeout}`; stdin là JSON có `session_id`, `cwd`.
- SessionStart: JSON `hookSpecificOutput.additionalContext` được đưa vào ngữ cảnh; không chặn được phiên.
- Stop: chặn bằng JSON `{"decision": "block", "reason": "..."}` (thoát 0).
- Windows: hook chạy bằng Git Bash mặc định.
- Subagent: `~/.claude/agents/*.md`, frontmatter `name, description, tools, model…`; chỉ câu trả lời cuối của subagent về phiên chính.
- Lệnh: `~/.claude/commands/*.md` vẫn dùng được (đã gộp vào skills); frontmatter `description, argument-hint, allowed-tools, disable-model-invocation`; `$ARGUMENTS`.

## 10. Graph & Context Builder (DEC-0003..0005, sửa D7 ngày 2026-10-05)

**Graph là accelerator tuỳ chọn.** Chưa cấu hình / chưa cài / chưa dựng / lỗi ⇒ Orchestra chạy như cũ (fallback).

- **Graph Adapter** `cli/graph_adapter.py` (stdlib): `is_available, status, update, query, affected, explain, path`.
  Engine hiện tại: Graphify, gọi `<venv>\python -m graphify extract <root> --code-only --out <cache>`; không
  `graphify install`, không hook, không `graphify update` (ghi vào thư mục nguồn). Đọc graph do adapter tự làm trên
  `graph.json` ⇒ đổi engine chỉ thay phần build/load.
- **Cài**: `python install.py --with-graphify` ⇒ venv `%LOCALAPPDATA%\orchestra-kit\graphify-venv`, `graphifyy[sql]==0.9.76`.
- **Bật cho dự án** — `config.yaml`:
  ```yaml
  graph:
    engine: graphify
    max_files: 12        # budget CTX
    max_results: 40
    hub_degree: 25       # symbol có > 25 cạnh phụ thuộc không được mở rộng
    roots:               # dựng riêng từng root, tránh .gitignore loại thư mục (F1)
      - {path: app, include: [src, tests]}
      - {path: supabase/migrations}
  ```
- **Cache** `.orchestra/cache/graph/` (gitignore; không commit raw graph; không có GRAPH_REPORT ở phase 1).
- **Trạng thái** `none|fresh|stale|degraded|locked|unavailable`; chỉ `fresh` là `authoritative`.
  Freshness = MD5 từng file trong include so với manifest (không mtime, không git). Sửa docs/.orchestra không làm stale.
  `degraded` khi: engine bỏ sót file (F1), có .sql mà không có node SQL (F2), khác phiên bản ghim.
- **An toàn đọc**: hàm SQL định nghĩa lại ⇒ chỉ bản ở migration mới nhất, bản cũ có `superseded_by` (F3);
  graph không phủ RPC bằng chuỗi TS → SQL ⇒ "không có đường đi" ≠ "không phụ thuộc" (F4); lock file khi update,
  đọc khi đang khoá ⇒ `locked` ⇒ fallback (F6); không lưu ID community (F7).
- **CTX** (`contexts.yaml`): thêm `source (manual|graph|fallback)`, `graph_state`, `fingerprint {graph, files: {path: md5}}`,
  `truncated`. Context Builder viết thân CTX (khối ```` ```yaml orc-context ```` + Graph evidence + Vùng rủi ro +
  Giới hạn context); A chạy `orc ctx seal` (orc ghi registry, D4). `source: graph` bị từ chối nếu graph không fresh.
  Coder chạy `orc ctx check CTX-x` trước khi dùng (F5: file đổi sau khi dựng context).

| Lệnh | Việc |
|---|---|
| `orc graph status` | trạng thái + file đổi + vấn đề (A chỉ đọc lệnh này, D3) |
| `orc graph update [--force]` | dựng lại khi code/SQL đổi; fresh thì không chạy engine; lỗi ⇒ mã 4 |
| `orc graph query T...` / `affected X` / `explain X` / `path A B` | kết quả kèm `state`, `authoritative`, `truncated` |
| `orc docs index` / `orc docs check` | sinh lại phần tự động của `docs/INDEX.md` từ frontmatter / kiểm frontmatter, INDEX, đường dẫn `docs/…` gãy trong md và chú thích code (chạy được cả khi chưa có `.orchestra/`) |
| `orc ctx seal CTX-x` / `orc ctx check CTX-x` | đăng ký CTX / báo file đã đổi (mã 5) |

## 11. Giai đoạn sau (D7 còn lại)

Nhiều Coder song song bằng git worktree (frontmatter subagent có `isolation: worktree`, chưa dùng) ·
docs/PDF vào graph (cần LLM) · GRAPH_REPORT như Orchestra artifact.
