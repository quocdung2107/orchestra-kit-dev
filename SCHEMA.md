# SCHEMA — orchestra-kit 0.1.0

Hệ đa-agent dạng blackboard: trạng thái sống trong file (.md/.yaml + git), agent
truyền nhau ID. Quyết định nền tảng D1–D8 do Dung chốt 2026-10-05.

## 1. Vai trò

| Vai trò | Hiện thực | Đọc | Ghi |
|---|---|---|---|
| A Orchestrator | Phiên Claude Code chính + lệnh /plan /run /review /next /handoff | brief, `orc show --meta`, `orc next` (chỉ metadata — D3) | chỉ qua `orc` |
| B Researcher | subagent `researcher` | task, plan cũ, code, tài liệu | thân file ART được cấp |
| C Coder | subagent `coder` (owner `coder`, `coder-1`, …) | task + acceptance, context | file trong `write_scope` |
| D Reviewer | subagent `reviewer` | `orc show TASK --pack` (acceptance + outputs + evidence) | thân file ART review_report |
| Context Builder | subagent `context-builder` — **placeholder (D7)** | — | — |

Single writer (D4): chỉ `orc` ghi `.orchestra/state/`. B/C/D trả **envelope YAML**; A nạp bằng `orc apply -`.

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

**Context**: `id, task, summary, paths[]` · **Evidence**: `id, task, kind(test|lint|build|manual|other), result(pass|fail|info), summary, paths[]`

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
| `orc set ID k=v ...` | sửa trường (giá trị đọc như YAML: `[a,b]`, `true`) |
| `orc show ID [--meta] [--pack]` | `--meta` cho A; `--pack` cho reviewer |
| `orc next` | thăng hạng task, in READY/REVIEW/HỎI DUNG/NEXT |
| `orc apply FILE|-` | nạp envelope, định tuyến, in `ROUTE:` (thêm ngoài đặc tả: cần để giữ D4) |
| `orc handoff open|check` | mở/kiểm handoff phiên |
| `orc validate [--handoff] [--key K]` | từ chối: frontmatter sai, ID trùng, summary > 200, tham chiếu ID không tồn tại, enum sai, file mồ côi |

## 9. Cú pháp Claude Code đã kiểm (2026-10-05)

Nguồn: code.claude.com/docs/en/hooks, /sub-agents, /slash-commands; Claude Code 2.1.289.
- Hook trong `settings.json`: `hooks.<Event>[].hooks[] = {type: "command", command, timeout}`; stdin là JSON có `session_id`, `cwd`.
- SessionStart: JSON `hookSpecificOutput.additionalContext` được đưa vào ngữ cảnh; không chặn được phiên.
- Stop: chặn bằng JSON `{"decision": "block", "reason": "..."}` (thoát 0).
- Windows: hook chạy bằng Git Bash mặc định.
- Subagent: `~/.claude/agents/*.md`, frontmatter `name, description, tools, model…`; chỉ câu trả lời cuối của subagent về phiên chính.
- Lệnh: `~/.claude/commands/*.md` vẫn dùng được (đã gộp vào skills); frontmatter `description, argument-hint, allowed-tools, disable-model-invocation`; `$ARGUMENTS`.

## 10. Giai đoạn sau (D7, chỉ khung)

Context Builder tự động · Graphify dựng KNOWLEDGE_MAP · nhiều Coder song song bằng git worktree
(frontmatter subagent có `isolation: worktree`, chưa dùng).
