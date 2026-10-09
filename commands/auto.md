---
description: Orchestra — yêu cầu đi state machine K. (1) Hiểu yêu cầu & thiết kế, hỏi Dung. (2) Plan → Dung duyệt một lần → code → verify → review → báo cáo
argument-hint: <mô tả yêu cầu>
allowed-tools: Bash(orc *)
disable-model-invocation: true
---

Bạn là **Orchestrator (A)**. Yêu cầu: $ARGUMENTS

Quy tắc A: chỉ đọc metadata và kết quả lệnh `orc` (D3); mọi ghi state qua `orc` (D4); truyền ID cho subagent.
Không báo tiến độ từng bước; chỉ nói với Dung ở điểm dừng và ở báo cáo cuối.
**Không bao giờ** tự gõ, chép hay "giúp" Dung dòng `orc:approve` / `orc:resume` / `orc:abort` — chỉ Dung gõ.

Điều kiện: brief có dòng `Workflow: K` và `verify: có`. Thiếu → **dừng**, báo Dung cần thêm `workflow: k` và mục
`verify:` vào `.orchestra/config.yaml` (Dung tự sửa; agent không sửa config).

## Chặng 1 — Hiểu yêu cầu & thiết kế (luôn dừng chờ Dung)
1. Phiên chưa mở S-ID → chạy lệnh `orc handoff open --key ...` có trong brief, `--request "$ARGUMENTS"`.
2. `orc new request --title "<tóm tắt ≤80 ký tự>" --summary "<≤200>"` → R. `orc set <S-ID> task=<R>`.
   `orc advance <R> --to TRIAGED`, `orc advance <R> --to RESEARCHING`.
3. `orc new task --title "Hiểu yêu cầu" --owner researcher --parent <R>` → UT;
   `orc new artifact --type research --task <UT> --summary "Hiểu yêu cầu & thiết kế"` → UND.
   `orc advance <UT> --to dispatched`; subagent **researcher**:
   `TASK: <UT>. Viết hiểu yêu cầu & thiết kế vào <UND>. Trả envelope YAML.` → `orc apply - <<'YAML'` … `YAML`.
4. `orc ask <UND>` và gửi Dung **nguyên văn** kết quả, cuối thêm một dòng:
   "Trả lời các câu hỏi (hoặc ghi 'đồng ý theo khuyên dùng'), sửa chỗ tôi hiểu sai nếu có."
   `orc ask` báo lỗi (mục chưa điền) → gửi lỗi cho researcher sửa rồi chạy lại. **Dừng chờ Dung.**
5. Dung trả lời:
   - Mỗi ý Dung chốt → `orc new decision --scope <UND> --summary "<≤200>"` (chỉ **đề xuất** — H7). DEC và UND sẽ
     được Dung duyệt **một lần** cùng plan ở bước 3 chặng 2 (ADJUSTMENTS #2).
   - Dung sửa cách hiểu nhiều hoặc thêm yêu cầu mới → `orc advance <UT> --to dispatched`, gọi lại researcher
     với cùng UT/UND kèm ý của Dung (1–3 câu), `orc apply -`, rồi lặp lại bước 4.
   - Đủ rõ → chặng 2.

## Chặng 2 — Plan → Dung duyệt một lần → code → verify → review → báo cáo
1. `orc new task --title "Plan: <tóm tắt>" --owner researcher --parent <R> --inputs <UND> <các DEC vừa tạo>` → PT;
   `orc new artifact --type plan --task <PT> --depends-on <UND>` → PLAN.
   `orc next`, `orc advance <PT> --to dispatched`; researcher: `TASK: <PT>. Viết plan vào <PLAN>. Trả envelope YAML.` → `orc apply -`.
2. `orc gate <PLAN>`: `PROCEED` → `orc advance <PLAN> --to accepted`, `orc new task --from <PLAN>` (task con tự thuộc R),
   `orc advance <R> --to PLANNED`. `ASK` → **điểm dừng** (báo các dòng sau `ASK`).
3. `orc advance <R> --to APPROVAL_REQUIRED` — orc in dòng `orc:approve <R>,<UND>,<DEC...> <NONCE>`. Gửi Dung
   **nguyên văn** dòng đó + tóm tắt plan (`orc report <PT>` phần plan/task, ≤ 10 dòng). **Dừng chờ Dung.**
   Dung gõ dòng đó → `orc approve <các ID đúng như dòng>` → `orc advance <R> --to IMPLEMENTING`.
   (Level chưa phân mức ⇒ chỉ APPROVAL_REQUIRED; READY_FOR_IMPLEMENTATION dành cho L0/L1 sau khi có triage.)
4. Lặp đến khi `orc next` không còn `READY:`/`REVIEW:` của R:
   - `HỎI DUNG` hoặc dòng `K: <R> [BLOCKED]` → **điểm dừng**: báo lý do (`orc show <R> --meta`, route cuối);
     khi Dung quyết xong, Dung gõ `orc:resume <R>` → `orc resume <R>`.
   - `READY: <T>` owner coder → **context trước**:
     1. `orc graph update` — tuỳ chọn; lỗi/không cấu hình (mã 4) thì bỏ qua, **không bao giờ dừng vì graph**.
     2. `orc new context --task <T> --summary "Context cho <T>"` → CTX; subagent **context-builder**:
        `TASK: <T>. Viết context vào <CTX>. Trả envelope YAML.`
     3. `orc ctx seal <CTX>`; lỗi → gửi nguyên văn cho context-builder sửa (tối đa 2 lần); vẫn lỗi thì bỏ CTX, chạy tiếp.
     4. Seal được → `orc set <T> context=[<CTX>]`.
     Rồi `orc advance <T> --to dispatched` (orc từ chối nếu R chưa IMPLEMENTING hoặc plan/scope đổi sau khi Dung duyệt
     → **điểm dừng**, xin duyệt lại bằng `orc approval request …`); coder: `TASK: <T>. Trả envelope YAML.` → `orc apply -`.
   - `REVIEW: <T>` → **`orc verify <T>` bắt buộc** (exit 0 PASS, 6 FAIL, 7 INCOMPLETE do môi trường — vẫn chuyển
     reviewer; orc tự định tuyến khi nạp kết quả review) → `orc graph update` (bỏ qua nếu lỗi) →
     `orc new artifact --type review_report --task <T>` → RR;
     reviewer: `TASK: <T>. Báo cáo vào <RR>. Dùng orc show <T> --pack. Trả envelope YAML.` → `orc apply -`.
     orc đọc lần verify sau lần nộp: PASS ⇒ done; FAIL ⇒ REPAIR (về coder); scope ⇒ ROLLBACK + BLOCKED (orc in lệnh
     cho **Dung** tự chạy; A không chạy `git reset/checkout` để bỏ thay đổi); môi trường ⇒ BLOCKED.
   - `READY: <T>` owner researcher (replan) → `orc advance <T> --to dispatched`,
     `orc new artifact --type plan --task <T> --supersedes <plan cũ>` rồi researcher → `orc apply -`.
   - `orc` từ chối envelope → gửi nguyên văn lỗi cho subagent đó sửa, tối đa 2 lần, rồi **điểm dừng**.
5. Mọi task coder đã nộp → `orc advance <R> --to VERIFYING`; mọi task coder done → `orc advance <R> --to DONE`.
6. Kết thúc:
   - Code trong `app/` (repo riêng): nhánh `orchestra/<R>`, commit; **không merge, không push**. Commit `.orchestra/` trong `D:\WMS`.
   - Điền `.orchestra/sessions/<S-ID>.md`, `orc handoff check --key ...`, `orc validate`.
   - Trả Dung **một lần**: `orc report <PT>` (giữ nguyên bảng) + tối đa 5 dòng: giả định đã tự chọn,
     việc Dung cần thử tay, nhánh cần merge. Dung merge xong → `orc advance <R> --to INTEGRATED`.

## Điểm dừng (chỉ những trường hợp này)
Chặng 1 bước 4 · duyệt plan (chặng 2 bước 3) · `orc gate` = ASK · `HỎI DUNG` / R BLOCKED · dispatch bị từ chối vì
approval · envelope bị từ chối 2 lần · lỗi môi trường không tự khắc phục. Khi dừng: handoff `result: blocked`, hỏi một
câu trả lời được bằng một từ, kèm phương án khuyên dùng. Dung muốn huỷ yêu cầu: Dung gõ `orc:abort <R>` → `orc abort <R>`.
