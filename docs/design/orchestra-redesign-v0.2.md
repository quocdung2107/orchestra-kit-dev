# Orchestra Architecture Re-design — Safety-First

```
PROPOSED ARCHITECTURE
VERSION: 0.2
STATUS: REVIEW_REQUIRED
```

Ngày: 2026-10-07. Kit hiện tại: `orchestra-kit 0.1.0` (commit mới nhất ngày 2026-10-05).
Phạm vi: chỉ audit và thiết kế. **Không sửa code, không xoá file, không cài gì.**

**Căn cứ đã đọc:**
- `SCHEMA.md`, `cli/orc_core.py` (73 KB), `cli/graph_adapter.py`, `hooks/session_start`, `hooks/stop_check`, `templates/*`, `install.py` trong `C:\Users\quocd\orchestra-kit`.
- Thread "Dựng orchestra-kit đa agent".
- Tài liệu Claude Code về hooks, subagents, memory, permissions.

**Chưa đọc được:** `agents/*.md` và `commands/*.md`. Hai thư mục này là junction nên công cụ đọc file báo "protected". Mọi nhận định về prompt của agent/command trong tài liệu này đều suy ra từ SCHEMA và thread, chưa đối chiếu nguyên văn.

**Ký hiệu dùng xuyên suốt:**
- **[F]** sự thật đã kiểm, kèm vị trí trong code hoặc nguồn.
- **[I]** suy luận.
- **[P]** đề xuất.

---

## Tóm tắt điều hành

1. **[F] Vấn đề an toàn lớn nhất của 0.1.0 không nằm ở số lượng agent.** Nó nằm ở chỗ nhiều cơ chế "tất định" thực ra đang tin vào lời tự khai của LLM:
   - Bằng chứng test do LLM tự khai.
   - `write_scope` chỉ kiểm danh sách file mà LLM tự báo, không kiểm diff thật.
   - Cổng hỏi Dung (`orc gate`) chỉ dựa vào mục "Cần Dung quyết" do chính LLM viết.
   - `orc set` cho phép đổi trạng thái tuỳ ý.

   Vì vậy gộp hay tách agent đều **chưa** làm hệ an toàn hơn. Phải sửa lớp kiểm soát trước.
2. **[P] Nguyên tắc chính: tách trách nhiệm trước, tách phiên LLM sau.** Kiến trúc mới có ba mặt phẳng:
   - **Control plane** (`orc` + hooks, tất định, là người ghi duy nhất).
   - **Execution plane** (Main Claude chạy theo *mode*, tức logical agent có hợp đồng).
   - **Verification plane** (orc tự chạy test và kiểm diff; reviewer subagent độc lập khi cần).

   Quyền hạn được ép theo **trạng thái task** bằng hook PreToolUse, không ép theo việc tách phiên.
3. **[P] Được gộp:** Researcher (việc nội bộ), Architect/Planner và Coder vào Main session, cho Level 0–2.
4. **[P] Không gộp:**
   - Ghi state.
   - Chạy kiểm chứng.
   - Ghi nhận phê duyệt của người.
   - Reviewer độc lập (Level 2–3 và khi có cờ rủi ro).
   - Nghiên cứu trên nội dung ngoài, không tin cậy (web, tài liệu lạ). Việc này đặt trong subagent không có quyền ghi để chặn prompt injection.
5. **[P] Độ sâu workflow do `orc triage` quyết** từ tín hiệu tất định: đường dẫn rủi ro, số module, kích thước diff, loại thay đổi. Mức chỉ được **tăng** tự động, không tự giảm. Mức được tính lại ở ba điểm: lúc triage, sau plan (biết write_scope), và sau khi code (biết diff thật).

---

## A. Current Architecture Audit

### A1. Thành phần hiện có [F]

| Thành phần | Hiện thực | Vị trí |
|---|---|---|
| Orchestrator A | Phiên Claude chính + lệnh `/auto` `/plan` `/run` `/review` `/next` `/handoff` | SCHEMA §1, §6b |
| Researcher / Coder / Reviewer / Context Builder | 4 subagent ở `~/.claude/agents` (junction) | SCHEMA §1 |
| State | 5 registry YAML ở `.orchestra/state/`, nội dung ở `artifacts/ decisions/ contexts/ evidence/ sessions/` | SCHEMA §3–4 |
| Giao tiếp subagent → state | Envelope YAML → `orc apply` | `orc_core.py:827` |
| Định tuyến | Bảng tất định theo `status` + `failure_class` | `orc_core.py:888–945` |
| Cổng tự chạy | `orc gate ART-x` | `orc_core.py:1072` |
| Liền mạch phiên | Hook SessionStart → `orc brief`; hook Stop → kiểm handoff (chặn tối đa 3 lần) | `hooks/*`, `orc_core.py:715` |
| Graph | Graph Adapter + Graphify trong venv, cache gitignore, freshness bằng MD5 | `graph_adapter.py`, SCHEMA §10 |
| Tài liệu | `orc docs index/check` | `orc_core.py:1348, 1402` |
| Quyền | `~/.claude/settings.json` cho `Bash(orc *)`; `D:\WMS\.claude\settings.json` cho `npm run build/test/lint`, `git status/diff/log/add/commit/checkout -b` | thread, 2026-10-05 |

### A2. Những gì 0.1.0 làm tốt (giữ)

- **[F] Một nơi ghi registry, có validate:** ID trùng, tham chiếu gãy, enum sai, summary > 200 ký tự (`orc_core.py:612`).
- **[F] Kiểm envelope trước rồi mới ghi**, nên lỗi không để lại state ghi dở (`orc_core.py:839–865`).
- **[F] Reviewer chỉ nhận `--pack`** (acceptance + outputs + evidence), không nhận lập luận của coder.
- **[F] Accept một DEC có `supersedes` thì DEC cũ tự chuyển sang superseded** (`orc_core.py:458`).
- **[F] Graph có trạng thái `fresh|stale|degraded|locked|unavailable`, chỉ `fresh` là authoritative.** Có fallback và có lock riêng cho graph.
- **[F] Hook no-op khi không có `.orchestra/`.** Hook Stop có giới hạn để không chặn vô hạn.

### A3. Lỗ hổng trong code hiện tại [F]

| # | Lỗ hổng | Bằng chứng | Hệ quả |
|---|---|---|---|
| H1 | `orc set TASK status=done` được phép. Chỉ kiểm enum, không kiểm luật chuyển trạng thái | `set_fields` `orc_core.py:423–446` | LLM nhảy thẳng tới `done`, bỏ qua review. `Bash(orc *)` lại được cho phép không cần hỏi |
| H2 | Evidence là lời LLM khai: `{kind, result, summary}` → orc tạo EVD `result: pass` | `apply_envelope` `orc_core.py:850–857, 868–873` | "Test pass" có thể là bịa hoặc nhầm. orc không chạy lệnh nào |
| H3 | `write_scope` chỉ kiểm `outputs` mà coder tự khai | `_in_scope` dùng cho `env["outputs"]`, `orc_core.py:846–849` | Coder sửa file ngoài phạm vi mà không khai thì không bị phát hiện. Không có kiểm `git diff` |
| H4 | `orc gate` chỉ chặn khi mục "Cần Dung quyết" có nội dung, có DEC proposed, hoặc plan còn nguyên mẫu | `gate` `orc_core.py:1072–1104` | Việc có cần hỏi người hay không do LLM tự quyết. Không có tiêu chí rủi ro tất định (migration, auth, xoá dữ liệu…) |
| H5 | Ghi file không nguyên tử (`open(path, "w")`) và không có lock khi ghi state | `write_text` `orc_core.py:125–128` | Hai phiên chạy song song có thể ghi đè nhau. Process chết giữa lúc ghi thì registry bị cắt cụt |
| H6 | Hook bắt mọi lỗi rồi thoát 0, tức fail-open | `hooks/stop_check`, `hooks/session_start` | Với hook chặn, lỗi của kit đồng nghĩa với không chặn. Docs: lỗi thoát mã khác 2 hoặc timeout thì **tool call vẫn chạy** |
| H7 | Phê duyệt của Dung được ghi bằng lệnh mà chính LLM chạy (`orc set DEC status=accepted`) | SCHEMA §6b | Không phân biệt được Dung thật sự duyệt hay LLM tự ghi, hoặc bị nội dung độc hại dẫn tới ghi |
| H8 | `npm run test/build/lint` được cho phép không hỏi, trong khi `package.json` nằm trong phạm vi coder sửa được | `D:\WMS\.claude\settings.json` | Sửa `scripts.test` rồi chạy `npm run test` tức là chạy mã tuỳ ý không qua hỏi quyền |
| H9 | `ROUTE:` chỉ là dòng chữ gợi ý cho LLM. Việc LLM có làm theo hay không không được kiểm | `apply_envelope` trả chuỗi `ROUTE` | Hành động tiếp theo vẫn do LLM quyết |

### A4. Cấu trúc thông tin hiện tại [F]

Khoảng 12 nơi cùng chứa "sự thật": CLAUDE.md, business-invariants, agents/commands prompt, tasks.yaml, VIEC_CON_TON_DONG, ROADMAP, sessions/S-x, HANDOFF.md, DEC, docs/decisions/danh-muc, KNOWLEDGE_MAP, INDEX, graph, CTX. Audit Koinonia đã cho thấy các nơi này lệch nhau trên thực tế: README, VIEC và header ghi sai so với code.

---

## B. Problems

| # | Vấn đề | Loại |
|---|---|---|
| P1 | Lớp "tất định" đang tin lời tự khai của LLM (H1–H4, H7, H9) | Correctness / Safety |
| P2 | Không có mô hình rủi ro nên mọi task đi cùng một độ sâu. Việc nhỏ thì chậm, việc nguy hiểm thì không được nâng mức | Correctness / Simplicity |
| P3 | Tách Researcher → Coder làm mất bối cảnh. Context Builder + CTX + fingerprint được dựng ra để bù | Context correctness / Performance |
| P4 | Nhiều nguồn sự thật chồng nhau | Context correctness |
| P5 | Không có mô hình rollback. Code nằm trên nhánh nhưng không có checkpoint, không có quy tắc khi nào được reset | Recovery |
| P6 | `failure_class` vừa là nhãn chẩn đoán vừa là nhánh xử lý (4 nhánh riêng) | Simplicity |
| P7 | Hook fail-open | Safety |
| P8 | Ghi state không nguyên tử, không khoá | Correctness |
| P9 | Không có ranh giới giữa nội dung tin cậy và không tin cậy: web, tài liệu ngoài và archive đều vào cùng một bối cảnh với quyền ghi code | Safety |

---

## C. Safety Risks (xếp theo mức độ)

| # | Rủi ro | Khả năng | Tác hại | Nguồn gốc |
|---|---|---|---|---|
| S1 | Đánh dấu xong khi test thật chưa chạy hoặc đang fail | Trung bình | Cao | H1, H2 |
| S2 | Sửa ngoài phạm vi (kể cả migration, auth) không bị phát hiện | Trung bình | Cao | H3, H8 |
| S3 | Thay đổi rủi ro cao (schema, RLS, xoá dữ liệu) tự chạy không hỏi | Thấp–Trung bình | Rất cao | H4 |
| S4 | Phê duyệt giả: LLM tự ghi accepted, hoặc do injection | Thấp | Cao | H7 |
| S5 | Prompt injection từ web hoặc tài liệu ngoài dẫn tới sửa code hoặc chạy lệnh | Thấp | Cao | P9 |
| S6 | Registry hỏng do ghi đồng thời hoặc process chết | Thấp | Trung bình | H5 |
| S7 | Hook lỗi nên cổng chặn mất tác dụng mà không ai biết | Thấp | Cao | H6 |
| S8 | Thao tác không đảo ngược: `supabase db push`, `git push --force`, xoá file | Thấp | Rất cao | Chưa có deny tường minh |
| S9 | Bối cảnh cũ: đọc DEC hoặc tài liệu đã superseded, CTX đã cũ | Trung bình | Trung bình | P4 |

**Mô hình mối đe doạ [P]:** máy cá nhân, một người dùng. Đối thủ chính là **lỗi và ảo giác của LLM**, cộng với **nội dung không tin cậy có lời dặn chèn vào**. Không phải người dùng ác ý.
- Các biện pháp dưới đây nhắm vào hai nguồn đó, không chống được người có quyền shell trên máy.
- Mọi biện pháp đều là **defense in depth**. Không có lớp nào kín tuyệt đối, vì Bash và script vẫn có thể ghi file gián tiếp.

---

## D. What Should Be Merged

### D0. Phân tích 13 chiều: tách phiên LLM với một phiên có ranh giới

"Có ranh giới" nghĩa là một Main session nhưng state, quyền, kiểm chứng và phê duyệt vẫn tách (thiết kế ở N).

| Chiều | Tách phiên (0.1.0) | Một phiên có ranh giới | Kết luận |
|---|---|---|---|
| Context isolation | Subagent bắt đầu trống [F docs]. Cô lập tốt, nhưng mất bối cảnh | Bối cảnh liên tục | Cô lập chỉ cần ở **review** và **nội dung không tin cậy** |
| Context contamination | Lập luận sai ở researcher vẫn đi qua plan sang coder, nên tách phiên không chặn được lỗi lan | Lập luận sai lan trong phiên | Ngang nhau. Chống lây nhiễm thật sự cần **artifact có kiểu** (FACT/INFERENCE) + kiểm trích dẫn, không cần tách phiên |
| Mất lịch sử lập luận | Mất ở mỗi lần chuyển giao | Giữ, trừ khi compaction | Một phiên tốt hơn. Compaction được xử lý bằng hook SessionStart `compact` nạp lại package [F docs] |
| Kiểm chứng độc lập | Reviewer subagent | Mất, nếu không giữ reviewer | **Phải giữ reviewer + orc tự chạy test** |
| Ranh giới quyền | Tool của subagent bị giới hạn bằng frontmatter `tools` | Một bộ quyền cho cả phiên | Giải bằng **PreToolUse hook theo trạng thái** (deny có hiệu lực cả ở auto mode [F docs]) |
| Ranh giới tool | Như trên | Như trên | Như trên |
| Lan truyền lỗi | Lỗi đi qua envelope, orc bắt được lỗi định dạng | Lỗi trong phiên không có điểm chặn | Cần **điểm chuyển trạng thái có điều kiện** do orc kiểm |
| Ranh giới phê duyệt | Hiện yếu ở cả hai (H7) | Như trên | Giải bằng **hook UserPromptSubmit ghi lời Dung** (có trường `prompt` [F docs]) |
| Audit trail | Envelope + registry | Registry | Ngang nhau nếu mọi chuyển trạng thái đi qua orc và ghi nhật ký |
| Recovery khi phiên chết | State trong file, phiên mới đọc lại | Như trên | Ngang nhau, nhờ state + package nằm trong file |
| Rollback | Chưa có | Chưa có | Cần **checkpoint git theo task** |
| Prompt injection | Subagent research có thể đọc web mà không có quyền ghi | Một phiên vừa đọc web vừa ghi code | **Tách phiên tốt hơn rõ rệt** cho nội dung ngoài |
| Tự xác nhận | Coder không tự review | Main tự làm rồi tự kiểm | **Không cho phép** ở mức quyết định "xong" (xem J) |

### D1. Gộp được an toàn [P]

| Gộp | Vào | Điều kiện |
|---|---|---|
| Researcher (nghiên cứu **nội bộ**: đọc code, tài liệu trong repo) | Main, mode RESEARCH | Đầu ra phải là Research Artifact có kiểu (F), orc validate |
| Architect / Planner | Main, mode PLAN | Plan phải qua `orc triage --stage plan` |
| Coder | Main, mode IMPLEMENT | Hook chỉ cho Edit/Write trong write_scope; orc kiểm diff thật |
| Context Builder (LLM) | `orc ctx compile` (tất định) + Main tự đọc thêm khi cần | Package dạng con trỏ + hash, không chép code |
| Orchestrator A | `orc` (luồng) + Main (giao tiếp với Dung) | Main không đổi trạng thái được, ngoài `orc advance` |

---

## E. What Must Remain Separated

| Trách nhiệm | Tách bằng | Vì sao không gộp được |
|---|---|---|
| Ghi state, chuyển trạng thái | `orc` (code) | Nguyên tắc 4: workflow tất định |
| Chạy kiểm chứng (test, lint, typecheck, build) | `orc verify` tự chạy, tự ghi exit code + log | S1: không tin lời tự khai |
| Kiểm phạm vi thay đổi | `orc verify` đọc `git diff` / `git status` thật | S2 |
| Ghi nhận phê duyệt | Hook UserPromptSubmit ghi lời Dung; `orc approve` chỉ nhận khi có lời đó | S4 |
| Ép quyền theo trạng thái | Hook PreToolUse (fail-closed) | Prompt không ép được gì. Hook thì ép được |
| Review độc lập (Level 2–3 + cờ rủi ro) | Subagent `reviewer`: bối cảnh mới, chỉ quyền đọc + lệnh test, có thể dùng model khác | Tránh tự xác nhận |
| Nghiên cứu nội dung ngoài (web, tài liệu bên thứ ba) | Subagent `researcher-external`: không Edit/Write, không Bash ghi; trả artifact có kiểu | S5: cô lập injection |
| Thao tác không đảo ngược | Luôn deny trong hook; chỉ Dung tự làm | S8 |

**C. Ranh giới phải giữ dù chỉ dùng một Claude session [P]:**
1. **State boundary:** Main chỉ chạm state qua `orc advance/propose/submit`. `orc set` không được đổi `status`, `attempts`, `level`, `approved_*`.
2. **Permission boundary theo trạng thái:**
   - RESEARCH/PLAN: không được sửa code.
   - IMPLEMENT: chỉ sửa trong write_scope.
   - Lúc nào cũng deny: push, merge, force, `db push`, sửa `.orchestra/state`, sửa `.claude/settings*`, xoá đệ quy.
3. **Evidence boundary:** EVD loại `test|lint|build|typecheck|scope` **chỉ do orc tạo**. LLM chỉ được nộp EVD loại `note`, và loại này không có giá trị chứng minh.
4. **Approval boundary:** chuyển vào IMPLEMENTING ở Level 2–3, và mọi thao tác trong danh sách "cần duyệt", đòi token phê duyệt có trong nhật ký lời Dung.
5. **Untrusted-content boundary:** trong IMPLEMENTING, deny `WebFetch/WebSearch`. Nội dung ngoài chỉ vào được qua artifact của `researcher-external`.
6. **Verification boundary:** Main không bao giờ là người duy nhất xác nhận "xong".

**D. Có cần logical agents không? [P] Có.** Mỗi logical agent là một **mode** với hợp đồng gồm 5 phần: đầu vào, quyền tool, đầu ra bắt buộc, điều kiện thoát, trạng thái được phép. Mode do trạng thái task quyết, không do LLM tự xưng. Hook đọc trạng thái hiện tại (`orc guard`) để biết đang ở mode nào.

| Logical agent | Chạy ở | Trạng thái | Quyền ghi | Đầu ra |
|---|---|---|---|---|
| Triage | `orc` (code) | NEW → TRIAGED | — | level, risk_flags |
| Researcher (nội bộ) | Main | RESEARCHING | chỉ file artifact của task | Research Artifact |
| Researcher (ngoài) | Subagent | RESEARCHING | không | Research Artifact (orc ghi) |
| Planner | Main | PLANNING | chỉ file plan | Plan |
| Implementer | Main | IMPLEMENTING | write_scope | diff + `orc submit` |
| Verifier | `orc verify` (code) | VERIFYING | `.orchestra/evidence` | EVD tất định |
| Reviewer | Subagent | VERIFYING | không (chỉ trả verdict) | Review verdict |

---

## F. Research Mode Design

### F1. Ba chế độ, chọn tất định [P]

| Mode | Khi nào (do `orc triage` tính) | Sản phẩm |
|---|---|---|
| `none` | Level 0 | Không có |
| `light` | Level 1; hoặc Level 2 không có cờ `external_dep`/`uncertain` | Mục `facts/assumptions/unknowns` **trong plan**, dùng cùng schema claim. Không có file riêng |
| `full` | Level 3; hoặc có bất kỳ cờ nào trong `external_dep`, `new_dependency`, `uncertain`, `architecture` | Research Artifact riêng; có web thì dùng `researcher-external` |

LLM không chọn mode. LLM chỉ khai **các trường dữ kiện** trong form triage (G4/H2), orc tính mode. Dung có thể nâng mức bất cứ lúc nào. Muốn hạ mức thì phải có token phê duyệt kèm lý do.

### F2. Research Artifact schema (tối thiểu) [P]

```yaml
id: ART-0012
type: research
task: TASK-0031
mode: full                      # light | full
question: "..."                 # 1 câu, đo được
scope: {in: [...], out: [...]}
base_commit: 9f3c2a1            # HEAD khi nghiên cứu
claims:                         # FACT / INFERENCE / ASSUMPTION / UNKNOWN đều nằm đây
  - id: C1
    kind: FACT
    statement: "change_status() chỉ cho chuyển tiến"
    evidence:
      - source: supabase/migrations/20261004_orders.sql
        source_type: CODE        # CODE|TEST|DOC|DEC|RULE|WEB|USER|GIT
        locator: "L120-L147"
        quote: "if new_status <= old_status then raise"   # ≤ 160 ký tự
        sha256: "…"              # hash file lúc trích
    confidence: HIGH
  - id: C2
    kind: INFERENCE
    statement: "UI không cần chặn lùi trạng thái"
    derived_from: [C1]
    confidence: MEDIUM
  - id: C3
    kind: ASSUMPTION
    statement: "Một đơn chỉ có một người xử lý cùng lúc"
    confidence: LOW
    needs_user: true
  - id: C4
    kind: UNKNOWN
    statement: "Có job nền nào ghi status không?"
    how_to_resolve: "grep 'status' trong supabase/functions"
constraints: [{ref: DEC-0007}, {ref: RULE:orders-lifecycle}]
options:
  - {id: O1, summary: "...", pros: [...], cons: [...], relies_on: [C1, C2]}
  - {id: O2, summary: "...", pros: [...], cons: [...], relies_on: [C3]}
rejected_options: [{id: O2, reason: "dựa vào ASSUMPTION C3 chưa được duyệt"}]
recommendation: {option: O1, kind: RECOMMENDATION, rationale_claims: [C1, C2]}
confidence: MEDIUM              # tổng thể = thấp nhất của các claim mà recommendation dựa vào
open_questions: [{id: Q1, text: "...", default_if_no_answer: "..."}]
```

### F3. Luật validate (orc, tất định) [P]

1. `FACT` phải có ≥ 1 evidence. Với `source_type` là CODE, TEST, DOC hoặc RULE:
   - file phải tồn tại;
   - `quote` phải xuất hiện **nguyên văn** trong file (bỏ qua khác biệt khoảng trắng), trong khoảng `locator` ± 20 dòng;
   - không đạt thì orc **hạ claim xuống INFERENCE** và báo lỗi. Researcher không thể tự biến suy luận thành sự thật.
2. `FACT` có `source_type: WEB` buộc phải có URL + quote. Loại này **không bao giờ** được confidence HIGH, vì orc không kiểm lại được nội dung web.
3. `FACT` có `source_type: GRAPH` bị cấm. Graph chỉ cho biết chỗ nào liên quan (M).
4. `INFERENCE` phải có `derived_from` trỏ tới claim có thật. `recommendation` phải trỏ tới option, và option phải trỏ tới claim.
5. Recommendation dựa vào `ASSUMPTION` có `needs_user: true` thì task tự chuyển sang APPROVAL_REQUIRED.
6. `UNKNOWN` không có `how_to_resolve` thì bị từ chối.
7. **Freshness:** artifact bị coi là stale khi bất kỳ file nào nó trích có sha256 khác với hiện tại. Artifact stale không được nạp vào Context Package (G).
8. Artifact chỉ có giá trị trong task của nó. Muốn dùng cho task khác thì phải "promote" thành DEC hoặc tài liệu `current` (L).

---

## G. Context Compiler Design

### G1. Vai trò [P]

Context Compiler **chỉ** retrieve, filter, rank, structure và compile. Nó **không** viết câu khẳng định mới.

Lõi là code (`orc ctx compile`). LLM chỉ được dùng ở một bước tuỳ chọn: xếp hạng các ứng viên ở Level ≥ 2. Ngay cả ở bước đó, LLM chỉ được chọn hoặc bỏ ứng viên, không được thêm nội dung.

### G2. Nguồn đầu vào và cách lấy (tất định)

| Nguồn | Cách chọn | Loại |
|---|---|---|
| Task, objective, acceptance | registry | TASK |
| Rules | `.claude/rules/*.md` có `paths:` khớp write_scope; luôn kèm rules không có `paths` | RULE |
| Decisions | DEC `accepted`, chưa superseded, có `scope`/`topic`/`paths` khớp task hoặc write_scope | DEC |
| Research | ART research của task, phải fresh | RESEARCH |
| Docs | `docs/**` có `status: current` và `feature` khớp; `read_when` dùng để xếp hạng | DOC |
| Code | write_scope + import trực tiếp (graph nếu fresh, nếu không thì grep import) | CODE |
| Tests | quy ước tên (`tests/**/<tên>.test.*`) + graph `affected` | TEST |
| Git | HEAD, nhánh, file bẩn ngoài scope | GIT |
| Graph | Chỉ để gợi ý ứng viên. Mọi ứng viên phải được xác minh lại trên file thật | GRAPH→CODE |

**Luôn loại trừ:** `docs/archive/**`, DEC superseded/proposed, artifact stale, tài liệu `status: superseded|archived`.

### G3. Context Package [P]

```yaml
id: CTX-0042
task: TASK-0031
level: 2
compiled_at: 2026-10-07T12:00:00Z
base_commit: 9f3c2a1
budget: {max_files: 12, used: 9, truncated: false}
objective: "..."                       # chép nguyên từ task
constraints: [...]
authoritative_rules:
  - {value: "Đơn chỉ chuyển trạng thái tiến", source: .claude/rules/orders.md, type: RULE,
     authority: 2, version: "sha256:…", confidence: HIGH}
relevant_decisions: [{id: DEC-0007, summary: "...", version: "sha256:…"}]
research: [{id: ART-0012, fresh: true}]
relevant_files:                        # CON TRỎ, không chép code
  - {path: app/src/orders/status.tsx, reason: "write_scope", sha256: "…", via: SCOPE}
  - {path: supabase/migrations/2026…sql, reason: "định nghĩa change_status", sha256: "…", via: GRAPH→VERIFIED}
relevant_tests: [{path: app/tests/status.test.ts, sha256: "…"}]
known_risks: ["RPC gọi bằng chuỗi: graph không phủ TS→SQL"]
assumptions: [{ref: ART-0012#C3, approved: false}]
forbidden_actions: ["sửa supabase/migrations/* cũ", "db push", "sửa ngoài write_scope"]
verification_requirements: [V1, V2, V3]   # theo J
conflicts: []                             # khác rỗng ⇒ không được vào IMPLEMENTING
not_exhaustive: true                      # Implementer được phép và được khuyến khích đọc thêm
```

### G4. Provenance [P]

Mọi mục có giá trị khẳng định (rule, decision, fact trích từ research) đều mang 5 trường:
- `value`
- `source`: đường dẫn hoặc ID
- `type`
- `authority`: bậc, xem bảng ở H5/L
- `version`: sha256 nội dung hoặc commit

`confidence` lấy nguyên từ nguồn; Compiler không tự gán. Compiler không có trường nào để ghi văn xuôi của riêng nó.

---

## H5. Context Safety (mục 5 của yêu cầu)

### Bậc nguồn và luật ưu tiên tất định [P]

| Bậc | Nguồn | Trả lời câu hỏi |
|---|---|---|
| 1 | Lời Dung trong phiên, có trong nhật ký prompt, đúng task | "Bây giờ muốn gì" |
| 2 | Rules (`.claude/rules`) + DEC accepted mới nhất | "Hệ thống **phải** thế nào" (chuẩn tắc) |
| 3 | Code + migrations tại HEAD | "Hệ thống **đang** thế nào" (mô tả) |
| 4 | Tests | Hành vi được khẳng định |
| 5 | Docs `status: current` | Giải thích, đặc tả chi tiết |
| 6 | Research artifact (fresh, cùng task) | Phân tích tạm thời |
| 7 | Graph | Chỉ để điều hướng, không bao giờ là bằng chứng |
| — | archive, superseded | Không được nạp |

**Luật ưu tiên chỉ áp dụng được ở các trường hợp sau.** Ngoài các trường hợp này là `CONFLICT DETECTED → dừng/hỏi`.

| Xung đột | Luật | Lý do được tự xử |
|---|---|---|
| Hai DEC accepted cùng `topic`, có liên kết `supersedes` | Lấy DEC mới | Liên kết tường minh do người duyệt |
| Doc (5) mô tả **hiện trạng** khác code (3) | Code thắng; doc bị đánh dấu `stale` để sửa sau | Câu hỏi mô tả: code là sự thật về cái đang có |
| Doc (5) khác DEC (2) | DEC thắng; doc bị đánh dấu `stale` | DEC là nguồn chuẩn tắc được duyệt |
| Research (6) khác bất kỳ nguồn bậc 1–5 nào | Nguồn bậc cao thắng; research bị đánh dấu stale | Research là tạm thời |
| Graph khác file thật | File thật thắng | Graph là cache |

**Luôn escalate, không tự chọn:**
- DEC/rule (chuẩn tắc) khác code (mô tả): có thể code bị lỗi, cũng có thể quyết định đã lỗi thời. Chỉ người mới biết.
- Rule khác DEC.
- Hai DEC accepted cùng `topic` mà không có `supersedes`.
- Lời Dung trong phiên trái một DEC accepted: hỏi xem có tạo DEC mới thay thế không.

### Phát hiện [P]

| Loại | Cách phát hiện | Tất định? |
|---|---|---|
| Superseded | Trạng thái trong registry hoặc frontmatter | Có |
| Stale | sha256 nguồn trích ≠ hiện tại; `base_commit` ≠ HEAD với file trong package | Có |
| Trùng lặp | Ràng buộc: tối đa 1 DEC accepted cho mỗi `topic` (trường bắt buộc mới); một đoạn văn trùng ≥ 90% ở 2 file `current` | Có |
| Mâu thuẫn cấu trúc | Doc `current` trỏ tới DEC đã superseded; package chứa 2 bản định nghĩa của cùng một symbol SQL | Có |
| Mâu thuẫn ngữ nghĩa ("A nói 5 trạng thái, B nói 6") | LLM phát hiện, ghi `conflict_candidate` | **Không**. LLM chỉ được **báo**, không được **chọn** |

Package có `conflicts` khác rỗng thì `orc advance → IMPLEMENTING` bị từ chối, trừ khi mỗi xung đột đã có `resolution` trỏ tới một luật trong bảng trên, hoặc tới token phê duyệt của Dung.

---

## M. Graphify Boundary

```
Source of Truth (code, migrations, tests @ HEAD)
        │  build (orc graph update, chỉ khi hash code/SQL đổi)
        ▼
Graph Index (cache, .orchestra/cache/graph, gitignore)
        │  query → ỨNG VIÊN (path, symbol, quan hệ)
        ▼
Context Compiler ── verify mỗi ứng viên:
        │   file tồn tại? sha256 khớp manifest? symbol có thật (grep)?
        │   có ⇒ đưa vào relevant_files với via: GRAPH→VERIFIED
        │   không ⇒ bỏ + ghi known_risks
        ▼
Context Package
```

**Luật [P]:**
1. Kết quả graph có kiểu `NAVIGATION_HINT`. Không được thành FACT và không được thành bằng chứng "không phụ thuộc".
2. Graph khác `fresh` ⇒ Compiler bỏ qua graph và dùng fallback (grep import, quy ước tên). Package ghi `graph_state`.
3. Graph chết thì workflow vẫn chạy được. Phải có test bảo đảm điều này (đã có trong 0.1.0, giữ nguyên).
4. **[F]** Các rủi ro F1–F7 đã xử lý trong 0.1.0 được giữ nguyên.
5. **[P]** Graph mặc định tắt ở repo dưới ~150 file (WMS), bật ở Koinonia. Chỉ giữ graph nếu đo thấy lợi (O, phase 5).

---

## H. Workflow Depth Design

### H1. Bốn mức, một state machine

Bốn mức **không** phải bốn workflow. Chúng dùng chung state machine K; mức chỉ quyết định **trạng thái nào bắt buộc** và **kiểm chứng nào bắt buộc**.

| | L0 Quick | L1 Normal | L2 Complex | L3 High-risk |
|---|---|---|---|---|
| Research | none | light (trong plan) | light/full | full + alternatives |
| Plan | không (task = plan) | có, ngắn | có + design | có + DEC |
| Hiện "tôi hiểu yêu cầu là" | không | có | có | có |
| Dừng chờ Dung trước khi code | chỉ khi có câu hỏi mở | chỉ khi có câu hỏi mở | **luôn** | **luôn** + DEC accepted |
| V1 test, V2 static + scope | ✓ | ✓ | ✓ | ✓ |
| V3 reviewer độc lập | — | khi có cờ | ✓ | ✓ (khuyên dùng model khác) |
| Merge | Dung | Dung | Dung | Dung, sau kiểm tích hợp |

**Lưu ý: mục này thay đổi một quyết định đã chốt.** Ngày 2026-10-05 Dung chốt "chặng hiểu & thiết kế luôn dừng". Thiết kế này đề xuất ở L0/L1 chỉ **hiện** phần hiểu, và chỉ **dừng** khi có câu hỏi mở. Cần Dung duyệt riêng (câu hỏi Q2 ở cuối).

### H2. Tiêu chí tất định [P]

`orc triage` tính mức từ hai nguồn tín hiệu.
- **(a) Tín hiệu máy đo được:** đường dẫn, số file, số dòng diff, module.
- **(b) Form khai báo**, mỗi trường là có/không, LLM điền, Dung xem được.

Mức cuối cùng = **max** của các luật khớp.

| Tín hiệu | Nguồn | → Mức tối thiểu |
|---|---|---|
| Đường dẫn khớp `risk_paths.L3` (mặc định: `**/migrations/**`, `supabase/**`, `**/auth/**`, `**/*rls*`, `.github/**`, `.claude/**`, `.orchestra/**`, `package.json`, lockfile, `**/*.env*`) | máy | L3 |
| Khai: đổi schema/data model, xoá hoặc di trú dữ liệu, bảo mật/quyền, thao tác không đảo ngược | form | L3 |
| Số file thay đổi > 15 **hoặc** diff > 400 dòng **hoặc** module > 3 | máy | L3 |
| Khai: đổi API/contract công khai, thêm dependency, phụ thuộc dịch vụ ngoài | form | L2 |
| Đổi hành vi người dùng thấy được (UI flow, định dạng file xuất) | form | L2 |
| Module chạm > 1 **hoặc** file > 5 **hoặc** diff > 120 dòng | máy | L2 |
| `unknowns` không rỗng sau plan **hoặc** cờ `uncertain` | form/artifact | L2 |
| File ≤ 5, 1 module, không có cờ nào ở trên | máy | L1 |
| File ≤ 2, diff ≤ 40 dòng, không đổi hành vi, không có cờ | máy + form | L0 |

"Module" = thư mục cấp 2 dưới các `roots` trong config. Mọi ngưỡng nằm trong `config.yaml` để chỉnh theo từng dự án.

### H3. Thời điểm tính và tính đơn điệu

1. **Triage lần 1** (NEW → TRIAGED): dựa trên yêu cầu + form + đường dẫn dự kiến.
2. **Triage lần 2** (PLANNED): dựa trên write_scope thật của plan.
3. **Triage lần 3** (VERIFYING): dựa trên `git diff` thật.

Mức chỉ **tăng**.
- Tăng ở lần 2 ⇒ task quay lại bước còn thiếu (ví dụ L1 → L3 thì phải research full + DEC).
- Tăng ở lần 3 ⇒ task **bị chặn**. Phải qua đủ kiểm chứng của mức mới, và nếu thiếu phê duyệt thì ROLLBACK (I).

Hạ mức chỉ được khi Dung gõ `orc:downgrade TASK-x L1 <lý do>`. Lời này được ghi trong nhật ký prompt.

---

## I. Failure / Recovery Model

### I1. Tách nhãn và hành động [P]

**`failure_class` (chỉ để chẩn đoán, đo lường, báo cáo):**
- `ENV`: mạng, tool, quyền OS.
- `VALIDATION`: artifact hoặc envelope sai schema.
- `TEST_FAIL`
- `STATIC_FAIL`: type, lint, build.
- `SCOPE_VIOLATION`
- `SPEC_GAP`
- `CONTEXT_CONFLICT`
- `DECISION_CONFLICT`
- `REGRESSION`
- `APPROVAL_MISSING`
- `REVIEW_REJECT`
- `INTERNAL`: lỗi của orc hoặc hook.

**`recovery_action`** chỉ có 5 giá trị: `RETRY | REPAIR | ROLLBACK | ESCALATE | ABORT`.

### I2. Bảng ánh xạ (tất định, orc tính)

| failure_class | Điều kiện | → action |
|---|---|---|
| ENV, VALIDATION | lần thứ ≤ 2 **và** lỗi mới khác hash lỗi lần trước | RETRY |
| ENV, VALIDATION | lặp cùng hash lỗi, hoặc lần thứ > 2 | ESCALATE |
| TEST_FAIL, STATIC_FAIL | L0–L2, attempts ≤ 2, test fail nằm trong write_scope/tests liên quan | REPAIR |
| TEST_FAIL, STATIC_FAIL | L3, hoặc attempts > 2 | ESCALATE |
| REGRESSION (test **ngoài** liên quan fail) | bất kỳ | ROLLBACK → ESCALATE |
| SCOPE_VIOLATION | bất kỳ | ROLLBACK phần ngoài scope → ESCALATE |
| SPEC_GAP | L0–L1 | REPAIR (sửa plan, triage lại) |
| SPEC_GAP | L2–L3 | ESCALATE |
| CONTEXT_CONFLICT, DECISION_CONFLICT, APPROVAL_MISSING | bất kỳ | ESCALATE |
| REVIEW_REJECT | L2, lần 1 | REPAIR, rồi review lại bằng **phiên reviewer mới** |
| REVIEW_REJECT | L3, hoặc lần 2 | ESCALATE |
| INTERNAL | bất kỳ | ABORT task hiện tại (state giữ nguyên), báo Dung |
| (Dung huỷ) | — | ABORT |

### I3. Trả lời các câu hỏi bắt buộc

- **Khi nào retry?** Chỉ khi thao tác **idempotent, không có tác dụng phụ ngoài repo**, và lỗi là ENV hoặc VALIDATION. Tối đa 2 lần. Lỗi lặp lại y hệt thì dừng.
- **Khi nào retry là nguy hiểm?**
  - Lệnh chạm DB hoặc dịch vụ thật.
  - Lệnh đã ghi một phần (migration, script chuyển dữ liệu).
  - Lệnh có tham số ngẫu nhiên hoặc phụ thuộc thời gian.
  - "Retry" thực chất là sửa test cho pass.

  Các trường hợp này đều bị cấm retry và chuyển thẳng ESCALATE.
- **Khi nào rollback?** SCOPE_VIOLATION, REGRESSION, mức bị nâng ở triage lần 3 mà thiếu phê duyệt, hoặc Dung yêu cầu. Cơ chế:
  - Mỗi task chạy trên nhánh `orchestra/TASK-x`, có **checkpoint commit** lúc vào IMPLEMENTING.
  - Rollback = `git reset --hard <checkpoint>` **chỉ trên nhánh task**.
  - Từ chối rollback nếu đang ở `main`, hoặc nếu có file bẩn ngoài write_scope (có thể là việc Dung đang làm dở).
  - Không có rollback cho tác dụng phụ ngoài git. Vì vậy L3 cấm áp migration lên DB thật trong task (xem J, N).
- **Khi nào bắt buộc hỏi Dung?**
  - Mọi ESCALATE.
  - Vào IMPLEMENTING ở L2–L3.
  - ASSUMPTION có `needs_user`.
  - Mọi CONFLICT không có luật.
  - Hạ mức.
  - Merge và push.
  - Mọi thao tác trong `deny_always`: Dung tự làm.
- **Khi nào Main không được tự sửa?**
  - SCOPE_VIOLATION.
  - Mọi CONFLICT.
  - Test fail mà muốn sửa **chính test đó**. Chỉ được sửa khi file test nằm trong write_scope **và** plan đã nêu rõ việc đổi test.
  - REVIEW_REJECT ở L3.
  - Phát hiện vấn đề bảo mật.
  - Thay đổi rules, DEC hoặc `.claude/`.
- **Khi nào cần reviewer độc lập?** Xem J.

---

## J. Verification Model

### J1. Bốn mức

| Mức | Ai làm | Bằng chứng | Có giá trị chứng minh "xong"? |
|---|---|---|---|
| V0 Self-check | Main | Checklist AC tự đánh giá | **Không** (chỉ là ghi chú) |
| V1 Deterministic tests | `orc verify` tự chạy lệnh trong `config.verify.test` | exit code, thời gian, sha256 log, số test | Có |
| V2 Static + scope | `orc verify`: typecheck, lint, build; `git diff --name-only` + `git status --porcelain --ignored` so với write_scope; quét risk_paths; quét bí mật đơn giản | như trên | Có |
| V3 Independent review | Subagent `reviewer` (bối cảnh mới, chỉ Read/Grep/Glob + allowlist lệnh test; tuỳ chọn model khác) | verdict theo từng AC, mỗi verdict có `file:line`; orc kiểm các trích dẫn có tồn tại | Có (cho các tiêu chí test không phủ) |

### J2. Trả lời trực tiếp

**Main Claude có được vừa implement vừa tự verify không?**
- Được tự **V0** để tự sửa sớm.
- **Không bao giờ** được là bên duy nhất quyết định "xong". DONE luôn đòi V1 + V2 do orc tạo.
- V3 bắt buộc khi:

| Trường hợp | V3 bắt buộc |
|---|---|
| Level 2, Level 3 | ✓ |
| Cờ: architecture, schema, migration, security/auth/RLS, destructive, dependency mới | ✓ (ở mọi mức, mà các cờ này vốn đã đẩy task lên L2/L3) |
| Refactor lớn (> 15 file hoặc > 400 dòng) | ✓ |
| Chạm > 1 module | ✓ |
| AC không có test tự động tương ứng | ✓ cho riêng AC đó, hoặc ghi "kiểm tay" vào báo cáo cho Dung |
| L0, L1 không có cờ | — |

**Chống "tự xác nhận trá hình" (cùng model review chính mình) [P]:**
- Reviewer **không** nhận lập luận, plan nội bộ hay hội thoại của Implementer. Chỉ nhận: AC, diff, EVD do orc tạo, rules/DEC trong package.
- Reviewer phải đưa phản bác tối thiểu ("tìm ít nhất 1 cách AC này có thể chưa đạt").
- Ở L3, reviewer chạy model khác (frontmatter subagent có trường `model` [F docs]).
- REVIEW_REJECT được sửa xong thì review lại bằng **phiên reviewer mới**, không dùng lại phiên cũ.

**AC không đo được bằng máy** ⇒ trạng thái DONE vẫn đạt, nhưng báo cáo ghi rõ "AC-n: chưa kiểm, cần Dung thử tay". Task chỉ sang `INTEGRATED` khi Dung xác nhận (K).

---

## K. State Machine

### K1. Trạng thái (9 + 3 phụ)

```
NEW → TRIAGED → [RESEARCHING] → PLANNED → [APPROVAL_REQUIRED] → IMPLEMENTING → VERIFYING → DONE → [INTEGRATED]
                                                   phụ: BLOCKED · FAILED · ABORTED
```
`[ ]` = chỉ có ở một số mức.
- RESEARCHING: L2 có `full`, L3.
- APPROVAL_REQUIRED: L2–L3, hoặc có câu hỏi mở.
- INTEGRATED: sau khi Dung merge.

So với 0.1.0, `dispatched/in_review/ready/pending` bị bỏ. `ready/pending` trở thành điều kiện tính toán (`blocked_by`), không còn là trạng thái.

### K2. Bảng chuyển

| Chuyển | Điều kiện trước | Actor | Hành động được phép trong trạng thái nguồn | Bằng chứng bắt buộc | Điều kiện sau | Khi thất bại |
|---|---|---|---|---|---|---|
| NEW→TRIAGED | form triage hợp lệ | orc (`orc triage`) | đọc | form + tín hiệu máy | `level`, `risk_flags`, `research_mode` được ghi | VALIDATION → RETRY ≤ 2 |
| TRIAGED→RESEARCHING | mode ≠ none | orc | đọc | — | ART research mở | — |
| RESEARCHING→PLANNED | ART validate đạt (F3), không có claim UNKNOWN chặn | orc | đọc; ghi **chỉ** ART của task; web chỉ qua subagent | ART hợp lệ | ART `accepted` | VALIDATION → RETRY; UNKNOWN chặn → ESCALATE |
| TRIAGED→PLANNED | mode = none hoặc light | orc | đọc | plan có AC + write_scope | triage lần 2 chạy | mức tăng → quay lại bước thiếu |
| PLANNED→APPROVAL_REQUIRED | L2–L3, hoặc câu hỏi mở, hoặc ASSUMPTION needs_user | orc | — | — | tin nhắn hỏi Dung được sinh từ `orc ask` | — |
| APPROVAL_REQUIRED→IMPLEMENTING | token `orc:approve TASK-x` có trong nhật ký prompt **sau** thời điểm plan; L3 cần thêm DEC accepted; package không có conflict | orc (`orc advance`) | — | approval record (prompt hash, thời gian) | checkpoint commit trên nhánh task | thiếu → APPROVAL_MISSING → ESCALATE |
| PLANNED→IMPLEMENTING | L0–L1, không có câu hỏi mở, package không có conflict | orc | — | CTX compiled | checkpoint commit | conflict → ESCALATE |
| IMPLEMENTING→VERIFYING | `orc submit` | Main gọi, orc kiểm | Edit/Write trong write_scope; Bash allowlist; **không** web | — | triage lần 3 chạy; `orc verify` tự chạy | mức tăng mà thiếu phê duyệt → ROLLBACK + ESCALATE |
| VERIFYING→DONE | đủ EVD V1+V2 = pass; V3 = pass nếu bắt buộc; package fingerprint còn khớp | orc | không sửa code | EVD do orc tạo; verdict reviewer có trích dẫn hợp lệ | báo cáo `orc report` | theo bảng I2 (REPAIR → IMPLEMENTING, attempts+1) |
| VERIFYING→IMPLEMENTING | action = REPAIR | orc | — | failure record | attempts+1 | attempts > 2 → ESCALATE |
| DONE→INTEGRATED | Dung merge (kiểm commit có trên main) | orc phát hiện | — | commit hash trên main | — | — |
| *→BLOCKED | ESCALATE | orc | — | lý do | `needs_user` | — |
| BLOCKED→(trạng thái trước) | token `orc:resume TASK-x` của Dung | orc | — | approval record | — | — |
| *→ABORTED | Dung huỷ, hoặc INTERNAL | orc | — | — | nhánh task giữ nguyên | — |

### K3. Ép buộc

- Lệnh duy nhất đổi trạng thái là `orc advance TASK --to X`. orc tự kiểm điều kiện.
- `orc set` bị cấm sửa `status, level, attempts, approved_*, failure_class`.
- PreToolUse hook deny mọi Edit/Write vào `.orchestra/state/**`, `.orchestra/runtime/**`, `.orchestra/evidence/**`, và deny mọi lệnh Bash nhắc tới các đường dẫn đó, trừ `orc`.
- Mỗi lần chuyển trạng thái được ghi vào `.orchestra/state/journal.jsonl`: thời gian, task, from, to, actor, evidence ids, hash dòng trước (chuỗi hash để phát hiện sửa tay).

---

## L. Source-of-Truth Map

| Loại thông tin | SOURCE OF TRUTH (duy nhất) | GENERATED VIEW | CACHE / INDEX | TEMPORARY | HISTORY |
|---|---|---|---|---|---|
| Chỉ dẫn làm việc mọi phiên | `CLAUDE.md` (< 200 dòng, không chứa sự thật nghiệp vụ) | — | — | — | — |
| Quy tắc nghiệp vụ, bất biến | `.claude/rules/*.md` (có `paths:`) | mục rules trong `docs/INDEX.md` | — | — | — |
| Quyết định | `.orchestra/decisions/DEC-x.md` + registry (bắt buộc có `topic`) | `docs/decisions/` (danh mục tự sinh) | — | — | DEC superseded |
| Trạng thái task | `.orchestra/state/tasks.yaml` + `journal.jsonl` | `orc brief`, `orc report`; nếu cần giữ thì VIEC/ROADMAP do orc sinh | — | — | — |
| Hành vi hệ thống | Code + migrations + tests @ git HEAD | — | Graphify | — | git log |
| Đặc tả tính năng | `docs/features/**` `status: current`, không được chép lại nội dung của DEC mà phải trỏ tới DEC | — | — | — | `docs/archive/**` |
| Định tuyến tài liệu | Phần viết tay của `docs/INDEX.md` (chỉ định tuyến, không khẳng định) | phần tự sinh của INDEX | — | — | — |
| Bản đồ domain → code | gộp vào INDEX (mục "domain → thư mục") | — | graph | — | `KNOWLEDGE_MAP.md` (đóng băng) |
| Nghiên cứu | — | — | — | ART research (giá trị trong task) | sau khi task DONE |
| Context | — | — | — | Context Package (sinh lại được; chỉ commit manifest hash) | — |
| Bằng chứng kiểm chứng | `.orchestra/evidence/EVD-x` **do orc tạo** | `orc report` | — | log đầy đủ (gitignore) | — |
| Phê duyệt | `.orchestra/runtime/prompts.jsonl` (hook ghi) → `approvals` trong journal | — | — | — | — |
| Lịch sử phiên | — | `orc brief` | — | — | `sessions/S-x.md` |
| Nhật ký cũ | — | — | — | — | `HANDOFF.md`, `VIEC_CON_TON_DONG.md` cũ (archive) |
| Auto memory của Claude Code | **Không phải nguồn sự thật**; khuyên tắt hoặc chỉ dùng cho sở thích cá nhân (cách tắt cần kiểm trong docs) | — | — | — | — |

**Luật [P]:** `orc docs check` từ chối khi có hai file `current` cùng khẳng định một `topic`, hoặc khi một doc chép nguyên văn một DEC.

---

## N. Proposed Architecture

```
                         ┌──────────────── Dung ────────────────┐
                         │ gõ yêu cầu / orc:approve / orc:resume│
                         └───────────────┬──────────────────────┘
                     UserPromptSubmit hook → prompts.jsonl (bằng chứng phê duyệt)
                                         │
┌───────────────────────── CONTROL PLANE (tất định) ─────────────────────────┐
│ orc: triage · state machine (advance) · journal · ctx compile · conflict    │
│      detect · verify runner · scope check · approve · report · docs check   │
│ hooks: SessionStart(startup|resume|compact → brief+package)                 │
│        PreToolUse(guard theo trạng thái, FAIL-CLOSED: lỗi ⇒ exit 2)         │
│        Stop(handoff)  SubagentStop(envelope hợp lệ)                         │
│ ghi nguyên tử (tmp+rename) + lock file cho state                            │
└───────┬──────────────────────────┬──────────────────────────┬──────────────┘
        │ mode (theo trạng thái)   │ chạy lệnh thật           │ dữ liệu
┌───────▼────────── EXECUTION ─────┐ ┌──────── VERIFICATION ───▼──┐ ┌─ KNOWLEDGE ─┐
│ Main Claude (một phiên)          │ │ orc verify (V1, V2)        │ │ SoT (L)     │
│  mode RESEARCH (nội bộ)          │ │ reviewer subagent (V3):    │ │ views       │
│  mode PLAN                       │ │  bối cảnh mới, chỉ đọc,    │ │ graph cache │
│  mode IMPLEMENT (write_scope)    │ │  model khác ở L3           │ └─────────────┘
│ researcher-external subagent:    │ └────────────────────────────┘
│  web/tài liệu ngoài, không ghi   │
└──────────────────────────────────┘
```

### N1. Guard (PreToolUse) theo trạng thái

| Trạng thái của task đang mở | Edit/Write | Bash | WebFetch/Search |
|---|---|---|---|
| không có task (hỏi đáp) | hỏi như bình thường (permission mode của Dung) | như bình thường | như bình thường |
| TRIAGED, RESEARCHING, PLANNED, APPROVAL_REQUIRED | chỉ file artifact/plan của task | chỉ allowlist đọc + `orc` | RESEARCHING: chỉ qua subagent external |
| IMPLEMENTING | chỉ trong write_scope | allowlist (test/lint/build/git đọc/commit trên nhánh task) | **deny** |
| VERIFYING | deny | allowlist test/đọc | deny |
| Mọi trạng thái (`deny_always`) | `.orchestra/state|runtime|evidence/**`, `.claude/**` | `git push`, `merge`, `rebase`, `reset --hard` (trừ khi `orc rollback` gọi), `--force`, `rm -r`, `supabase db push`, `psql` tới host ngoài localhost, `npm publish` | — |

**Ghi chú:**
- **[F docs]** Deny của PreToolUse có hiệu lực ở mọi permission mode. Hook lỗi với mã khác 2, hoặc timeout, thì tool call **vẫn chạy**.
- **[P]** Vì vậy guard phải bắt mọi exception rồi **exit 2** (fail-closed), có timeout nội bộ ngắn hơn timeout của hook. Riêng brief và stop vẫn fail-open, vì chúng không phải cổng an toàn.
- **[P]** Lối thoát khẩn cấp: biến môi trường `ORC_GUARD=off`. Chỉ có tác dụng khi Dung đặt trước lúc mở VS Code. Guard ghi cảnh báo vào brief mỗi phiên.

### N2. Phê duyệt không giả được bởi LLM

- Hook UserPromptSubmit ghi `{ts, session_id, sha256(prompt), prompt}` vào `prompts.jsonl`. Hook tự giữ chuỗi hash: mỗi dòng chứa hash của dòng trước.
- `orc approve TASK-x` chỉ thành công khi tìm thấy, trong nhật ký, một prompt chứa đúng `orc:approve TASK-x` và có thời điểm sau khi plan được tạo.
- Không có kênh nào khác để duyệt. Trả lời "ok" chung chung thì không đủ. Đây là đánh đổi có chủ đích về sự tiện lợi: Q5.
- **Giới hạn:** guard deny việc ghi file nhật ký, nhưng script Python vẫn có thể ghi gián tiếp. Chuỗi hash giúp **phát hiện** sửa, không **ngăn** được.

### N3. `orc verify`

- Đọc `config.verify`: `test`, `typecheck`, `lint`, `build` (lệnh cố định do Dung cấu hình).
- Tự chạy từng lệnh. Lưu exit code, thời gian, sha256 log, số test pass/fail (nếu parse được) thành EVD.
- `git diff --name-only <checkpoint>..HEAD` + `git status --porcelain --ignored` → so với write_scope và risk_paths → EVD `scope`.
- **Lệnh verify đọc từ config tại checkpoint commit, không đọc từ working tree.** Nhờ vậy sửa `package.json` không đổi được lệnh kiểm (vá H8). `package.json` vốn đã nằm trong risk_paths L3.

### N4. Hợp đồng mode (logical agents)

| Mode | Đầu vào | Đầu ra | Thoát bằng |
|---|---|---|---|
| RESEARCH | task + package | ART research (F2) | `orc advance --to PLANNED` (orc validate) |
| PLAN | task + package + ART | plan: AC, write_scope, orc-tasks, claims (nếu light) | `orc advance` (orc triage lần 2) |
| IMPLEMENT | package (con trỏ), plan | commit trên nhánh task | `orc submit` |
| REVIEW (subagent) | `orc show --pack` mới: AC + diff + EVD + rules | verdict YAML theo AC | SubagentStop hook kiểm định dạng; orc ghi |

### N5. Đơn giản hoá so với 0.1.0

| Bỏ / gộp | Thay bằng |
|---|---|
| Subagent researcher (nội bộ), coder, context-builder | Mode trong Main + `orc ctx compile` |
| Envelope cho researcher/coder | `orc advance` / `orc submit` (orc tự đọc diff và chạy test) |
| 7 trạng thái cũ + `resume_status` + `needs_user` | State machine K |
| 4 nhánh failure_class | 5 recovery_action |
| `orc gate` dựa vào mục LLM tự viết | `orc triage` 3 lần + điều kiện chuyển trạng thái |
| CTX viết tay bởi LLM | Context Package do code sinh |

**Giữ:** registry, validate, docs check, graph adapter, brief, handoff, reviewer.

---

## O. Migration Strategy

**Nguyên tắc:**
- Mỗi phase đảo ngược được (kit có git tag, dự án ghim `kit_version`).
- Có cổng kiểm: test kit + chỉ số không tệ hơn + Dung duyệt.
- Thành phần cưỡng chế chạy ở **shadow mode** (chỉ ghi log, không chặn) trước khi bật.

| Phase | Nội dung | Rủi ro | Cổng sang phase sau |
|---|---|---|---|
| 0 | **Đo baseline** trên 0.1.0 với 5 task thật: thời gian, số lần dừng, số lần envelope bị từ chối, lỗi đọc nhầm | không có | có bảng số |
| 1 | Vá lỗ hổng không đổi kiến trúc: ghi nguyên tử + lock (H5); `orc set` cấm trường trạng thái (H1); journal | thấp | 0.1.0 vẫn chạy, test xanh |
| 2 | `orc verify` + scope check bằng git (H2, H3, H8). EVD tất định chạy song song với EVD tự khai, so sánh độ lệch | thấp | 5 task: không có EVD tự khai nào sai mà không bị phát hiện |
| 3 | Hook UserPromptSubmit + `orc approve` (H7). PreToolUse guard ở **shadow** | trung bình (độ trễ hook) | đo độ trễ < 300 ms/tool call trên Windows; số lần guard *lẽ ra* chặn trong 10 task được Dung xem |
| 4 | Bật guard fail-closed. State machine K thay trạng thái cũ (có script chuyển registry, giữ bản cũ) | trung bình | không còn chặn sai sau 5 task |
| 5 | `orc triage` ở shadow (so với đánh giá của Dung trên 10 task) → bật | trung bình | lệch mức với Dung ≤ 1/10, không lần nào hạ thấp L3 |
| 6 | Research artifact v2 + kiểm trích dẫn. Context Compiler tất định; tắt context-builder. Đo A/B graph ở Koinonia | trung bình | tỷ lệ claim bị hạ cấp có xu hướng giảm; không mất file liên quan trong 5 task |
| 7 | Gộp researcher/coder vào mode của Main: L0–L1 trước, rồi L2. Giữ reviewer, thêm researcher-external | trung bình | chỉ số phase 0 tốt hơn, không tăng lỗi lọt review |
| 8 | Dọn nguồn sự thật (L): rules sang `.claude/rules`, KNOWLEDGE_MAP/HANDOFF/VIEC vào archive hoặc thành view, DEC có `topic` | thấp | `orc docs check` sạch |

**Rollback từng phase:** kit `git checkout <tag phase trước>`; dự án đặt `kit_version` cũ. Script chuyển registry ở phase 4 giữ bản `state.v0.1/` để quay lui.

---

## Why This Design Could Be Wrong

### W1. Failure scenarios

1. **Triage đánh giá thấp:** form khai thiếu, đường dẫn dự kiến sai. Lần 3 mới phát hiện L3 thì công đã làm phí, phải rollback.
   → *Sửa:* guard deny Edit vào risk_paths khi `level < 3`. Lỗi lộ ra **ngay lần sửa đầu tiên**, không phải đợi tới cuối.
2. **Lách guard qua Bash:** `python -c`, `sed -i`, script npm ghi file. Guard chỉ thấy chuỗi lệnh.
   → V2 (git diff + `--ignored`) bắt được sau đó. File bị gitignore nằm ngoài risk_paths thì vẫn lọt; đây là rủi ro còn lại được chấp nhận.
3. **Test xanh nhưng sai:** test không phủ AC. L0/L1 không có V3 nên lọt.
   → *Sửa:* AC không ánh xạ được tới test thì **bắt buộc** hoặc V3 cho AC đó, hoặc dòng "kiểm tay" trong báo cáo. Không được im lặng.
4. **Package cũ:** phiên song song sửa code (đã xảy ra ngày 2026-10-05). Implementer làm trên bối cảnh cũ.
   → Fingerprint được kiểm ở `orc submit` và trước V3. Lệch thì compile lại, và REPAIR nếu file trong scope đã đổi.
5. **Compaction giữa IMPLEMENTING làm mất ràng buộc.**
   → Hook SessionStart `compact` nạp lại brief + package [F docs: có matcher `compact`]. Ràng buộc sống trong file, không sống trong trí nhớ phiên.
6. **Guard fail-closed + Claude Code đổi schema hook** ⇒ chặn **mọi thứ**, Dung không làm việc được.
   → `ORC_GUARD=off`, kèm test hợp đồng hook trong kit để phát hiện sớm khi nâng Claude Code.

### W2. Safety risks của chính thiết kế

1. **Reviewer cùng model có điểm mù tương quan** nên độc lập chỉ là một phần. *Sửa:* model khác ở L3; bắt reviewer đưa phản bác tối thiểu.
2. **Mệt mỏi phê duyệt:** hỏi nhiều thì Dung duyệt máy móc, và an toàn thực tế giảm. *Sửa:* gom câu hỏi mỗi task thành **một** lần duyệt; đo số lần hỏi/task; cảnh báo khi > 2.
3. **`orc:approve` gõ bằng tay vẫn có thể bị Dung dán nhầm task.** *Sửa:* `orc ask` in sẵn câu lệnh duyệt kèm tóm tắt 1 dòng.
4. **`prompts.jsonl` chứa toàn văn lời Dung, có thể có thông tin nhạy cảm.** *Sửa:* gitignore; chỉ lưu dòng khớp `orc:` cùng hash của các dòng khác.
5. **Allowlist lệnh = chạy mã tuỳ ý** nếu cấu hình test bị thay đổi. *Đã sửa ở N3* (đọc config từ checkpoint). Nhưng mã test cũng là mã: test do Implementer viết có thể làm bất cứ gì khi chạy. Đây là rủi ro còn lại, giảm bằng V3 xem diff test.
6. **Rollback `reset --hard` xoá việc dở của Dung.** *Sửa:* điều kiện ở I3 + tạo stash/tag trước khi reset.

### W3. Complexity risks

1. `orc` từ 73 KB lên có thể gấp 2–3 lần: một người phải bảo trì một workflow engine.
2. Bề mặt cấu hình lớn: risk_paths, ngưỡng, lệnh verify cho từng dự án.
3. Hook PreToolUse chạy ở **mọi** tool call. Khởi động Python trên Windows có thể mất 100–300 ms, cộng dồn thành chậm (Dung đã than chậm).
4. Phụ thuộc vào ngữ nghĩa hook của Claude Code, vốn đang đổi nhanh.
5. Kiểm trích dẫn nguyên văn có thể gây nhiều lần từ chối (Stage 3 đã thấy LLM ghi sai định dạng evidence).
6. Thời gian chuyển tiếp có hai hệ (agents cũ + mode mới) nên dễ nhầm.

*Sửa:*
- Guard viết thành một module nhỏ, độc lập, khởi động nhanh, chỉ đọc một file `runtime/active.json` (không nạp YAML). Đo độ trễ ở phase 3, quá ngưỡng thì dừng.
- Ngưỡng có mặc định hợp lý; dự án chỉ ghi phần khác.
- Mỗi phase xoá luôn phần cũ mà nó thay.

### W4. Khi tách nhiều agent thực sự tốt hơn

1. **Nghiên cứu nội dung ngoài/không tin cậy:** cô lập injection (đã giữ: researcher-external).
2. **Review độc lập:** bối cảnh mới, không thấy lập luận của người làm (đã giữ).
3. **Khám phá lớn sinh nhiều output** (quét 400 file Koinonia): subagent giữ cho bối cảnh chính sạch.
   → *Sửa:* thêm mode `EXPLORE` tuỳ chọn chạy bằng subagent chỉ đọc, trả về danh sách con trỏ.
4. **Task độc lập chạy song song** trong worktree: để giai đoạn sau, như D7.

### W5. Khi Context Compiler làm tệ hơn

1. **Lọc mất file quan trọng** (RPC chuỗi TS→SQL) mà Implementer coi package là đủ.
   → *Sửa:* `not_exhaustive: true`; Implementer được đọc thêm. File đọc thêm nằm trong risk_paths thì triage lại.
2. **Chép đoạn code vào package** nên code bị cũ. *Sửa:* chỉ con trỏ + hash.
3. **Chi phí lớn hơn lợi ích ở L0.** *Sửa:* package L0 chỉ gồm rules khớp đường dẫn + write_scope + forbidden_actions.
4. **Luật ưu tiên mã hoá sai thứ bậc** nên chọn sai một cách âm thầm và có hệ thống. *Sửa:* luật ưu tiên chỉ dùng cho xung đột **mô tả/staleness**. Xung đột chuẩn tắc luôn hỏi.

### W6. Khi Research Mode thừa

1. Đường dẫn rủi ro khớp nhưng thay đổi tầm thường (sửa chú thích trong migration) vẫn bị bắt research full.
   → *Sửa:* `orc:downgrade` có lý do; thống kê số lần downgrade để chỉnh risk_paths.
2. Đã có artifact fresh cùng `topic` mà vẫn nghiên cứu lại. *Sửa:* tái dùng khi fresh (hash khớp).
3. Ở L2 nội bộ, đọc code chính là nghiên cứu nên artifact riêng trùng với plan. *Sửa:* L2 mặc định `light` (claims nằm trong plan); chỉ có cờ mới lên `full`.
4. Kiểm trích dẫn tốn công cho câu hỏi đơn giản. *Sửa:* với `light` chỉ kiểm claim FACT mà recommendation dựa vào.

### W7. Điều chỉnh thiết kế sau phản biện (đã đưa vào các mục trên)

- Guard deny sửa risk_paths khi `level < 3` (W1.1).
- AC không có test thì phải có V3 hoặc dòng "kiểm tay" tường minh (W1.3).
- Guard fail-closed, có lối thoát `ORC_GUARD=off` và test hợp đồng hook (W1.6).
- Config verify đọc từ checkpoint (W2.5).
- Thêm mode `EXPLORE` bằng subagent chỉ đọc (W4.3).
- Package dạng con trỏ, có `not_exhaustive` (W5.1–2).
- L2 mặc định research `light` (W6.3).
- Gom phê duyệt mỗi task thành một lần (W2.2).

### W8. Giả định chưa kiểm (sẽ làm sai thiết kế nếu sai)

| Giả định | Cách kiểm |
|---|---|
| Hook PreToolUse đủ nhanh trên Windows + Git Bash | Đo ở phase 3 |
| Hook fire bên trong subagent, có `agent_type` | [F docs], nhưng cần chạy thử trên máy |
| Cách tắt auto memory | Đọc docs memory, mục cấu hình |
| `git status --ignored` đủ để bắt ghi file bị gitignore | Thử ở phase 2 |
| LLM điền được form triage và claim schema với tỷ lệ từ chối chấp nhận được | Đo ở phase 5–6 |
| Nội dung `agents/*.md`, `commands/*.md` khớp với SCHEMA | Đọc trực tiếp (bị chặn lần này) |

---

## Câu hỏi cần Dung quyết trước khi lập implementation plan

| # | Câu hỏi | Khuyên |
|---|---|---|
| Q1 | Duyệt nguyên tắc "tách trách nhiệm trước, tách phiên sau" và mô hình 3 mặt phẳng (N)? | **Duyệt** |
| Q2 | L0/L1 chỉ dừng khi có câu hỏi mở, thay vì luôn dừng ở chặng hiểu & thiết kế (đổi quyết định 2026-10-05)? | **Đồng ý** |
| Q3 | Guard PreToolUse **fail-closed** (kit lỗi thì chặn), có lối thoát `ORC_GUARD=off`? | **Đồng ý** |
| Q4 | `package.json`, lockfile, `.claude/**`, migrations là risk_paths L3 mặc định? | **Đồng ý** |
| Q5 | Phê duyệt chỉ bằng câu lệnh `orc:approve TASK-x` (không nhận "ok")? | **Đồng ý** (an toàn > tiện) |
| Q6 | Reviewer ở L3 chạy model khác model chính? | **Đồng ý** |
| Q7 | Làm theo thứ tự phase 0 → 8, mỗi phase một lần duyệt? | **Đồng ý**; phase 0–2 làm trước vì vá được lỗ hổng mà không đổi kiến trúc |

```
PROPOSED ARCHITECTURE
VERSION: 0.2
STATUS: REVIEW_REQUIRED
```
