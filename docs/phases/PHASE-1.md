# PHASE 1 — Vá lỗ hổng không đổi kiến trúc (H5, H1, journal)

Nguồn: v0.2 mục O (phase 1), K3, A3 H1/H5; ADJUSTMENTS (không điểm nào đổi phạm vi phase này).

## Phạm vi

1. **Ghi nguyên tử (H5):** mọi `write_text` ghi file tạm cùng thư mục rồi `os.replace`.
2. **Lock state (H5):** lệnh `orc` có ghi (`new`, `set`, `advance`, `apply`, `next`, `handoff`, `ctx seal`,
   `docs index`… — mọi lệnh trừ lệnh chỉ đọc) giữ khoá `.orchestra/runtime/state.lock` suốt lệnh.
   Khoá có pid + thời điểm; chờ tối đa 10 s; khoá cũ hơn 120 s được coi là bỏ rơi và gỡ.
3. **`orc set` cấm trường trạng thái (H1, K3):** `status, level, attempts, failure_class, approved_*`,
   và hai trường trạng thái của 0.1.0 `needs_user, resume_status` (v0.2 N5 xếp chúng vào state machine).
4. **`orc advance ID --to X`:** đường duy nhất để đổi trạng thái bằng tay, theo bảng chuyển **của 0.1.0**
   (state machine K là Phase 4):
   - TASK: `pending|ready → dispatched` (mọi blocked_by đã done); `dispatched → ready` (giao lại);
     `blocked|failed → ready` (xoá needs_user — tạm thời, Phase 3 đòi token `orc:resume`).
     `in_review`, `done` chỉ đến qua `orc apply`.
   - ART: `draft → accepted|rejected`. DEC: `proposed → accepted` (DEC cũ tự superseded).
5. **Journal** `.orchestra/state/journal.jsonl`: mọi thay đổi `status` (tạo mới, advance, apply, next,
   supersede) ghi 1 dòng `{ts, id, from, to, actor, evidence, prev}`; `prev` = sha256 dòng trước (chuỗi hash).
   `orc validate` báo lỗi khi chuỗi gãy hoặc dòng không phải JSON.
6. Cập nhật `commands/*.md`, `SCHEMA.md` từ `orc set X status=…` sang `orc advance X --to …` để 0.1.0
   vẫn chạy được với `orc` mới (chỉ có hiệu lực khi release).

Ngoài phạm vi: ghi sự kiện "envelope bị từ chối" (FINDING-2, chờ Dung); `orc new decision --status accepted`
vẫn cho phép (đường phê duyệt của 0.1.0, thay ở Phase 3).

## Acceptance criteria

- AC-1.1: Ghi file nguyên tử: lỗi giữa chừng không để lại file đích hỏng; không còn file tạm.
- AC-1.2: Hai process `orc new task` chạy đồng thời không mất mục, không trùng ID.
- AC-1.3: `orc set TASK status=done` (và các trường cấm) bị từ chối, registry không đổi.
- AC-1.4: `orc advance` chỉ cho các chuyển ở mục 4; chuyển khác bị từ chối.
- AC-1.5: Mỗi chuyển trạng thái có đúng 1 dòng journal; sửa tay 1 dòng làm `orc validate` báo lỗi.
- AC-1.6: 0.1.0 vẫn chạy: vòng plan → task → dispatched → apply → review → done chạy qua CLI.
- AC-1.7: Toàn bộ test xanh.

## Cách test

`tests/test_phase1.py`: ghi nguyên tử (giả lỗi khi ghi), 2 process song song, `orc set` bị cấm, bảng
`advance`, journal + validate phát hiện sửa tay, vòng 0.1.0 đầy đủ qua CLI.

## Kết quả

Code (`cli/orc_core.py`):
- `write_text`: file tạm `.<tên>.<pid>.tmp` + `fsync` + `os.replace` (thử lại 50×20 ms khi Windows báo
  PermissionError vì file đích đang mở); file tạm luôn bị dọn.
- `state_lock`: `O_CREAT|O_EXCL` trên `runtime/state.lock` (gitignore sẵn), giữ suốt lệnh CLI có ghi
  (`MUTATING = new, set, advance, apply, next, handoff, ctx`). Hook không lấy khoá (chỉ ghi dấu phiên riêng).
- `guarded_set` cho `orc set`; `advance` + lệnh `orc advance ID --to X`; `set_fields` giữ làm hàm nội bộ.
- Journal ghi ở **một chỗ**: `save_registry` so status cũ/mới của task/artifact/decision, nên mọi đường
  (new, advance, apply, next, supersede) đều được ghi, kể cả đường quên. `apply` gắn EVD vào dòng journal.
  `orc validate` kiểm JSON + chuỗi `prev`.
- `commands/{auto,plan,run}.md`: `orc set X status=Y` → `orc advance X --to Y` (9 chỗ). `SCHEMA.md` §1, §8.

Test sửa: `test_orc.TestSetShow.test_set_artifact_syncs_frontmatter` đổi từ `orc set ART status=accepted`
sang `orc advance` + `orc set summary=` — đổi hành vi có chủ đích của phase này (K3).

Tương thích dữ liệu thật: `orc` mới chạy `validate` (OK), `brief`, `report` trên `D:\WMS` (lệnh chỉ đọc);
`git status` của `D:\WMS` không đổi. Dự án cũ không có `journal.jsonl` vẫn hợp lệ; journal bắt đầu từ lần ghi đầu.

Giới hạn còn lại (ghi rõ, không sửa ở phase này):
- Đường Python trực tiếp (`python -c "import orc_core; orc_core.set_fields(...)"`) vẫn đổi được status:
  chặn ở Phase 3–4 bằng guard; journal giúp **phát hiện**, không **ngăn**.
- `orc new decision --status accepted` vẫn được (đường phê duyệt của 0.1.0, thay ở Phase 3).
- `advance blocked|failed → ready` chưa đòi token `orc:resume` của Dung (Phase 3).
- Journal ghi lại toàn file mỗi lần (O(n)); đủ cho quy mô hiện tại (WMS: 28 task).

## Test

`python -m unittest discover -s tests`: **Ran 85 tests, OK (skipped=1)** — 77 cũ (1 test cũ sửa như trên)
+ 8 mới trong `tests/test_phase1.py`. Skip vẫn là FINDING-1.

## AC

AC-1.1 đạt (`TestAtomicWrite`). AC-1.2 đạt (6 process song song → TASK-0001..0006, không mất).
AC-1.3 đạt. AC-1.4 đạt. AC-1.5 đạt (journal 3 dòng / 3 chuyển; sửa tay → validate lỗi). AC-1.6 đạt
(`TestV01StillRuns` qua CLI: plan → gate → from → next → dispatched → apply → review → done → report).
AC-1.7 đạt.
