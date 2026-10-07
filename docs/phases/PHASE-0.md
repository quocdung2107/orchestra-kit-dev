# PHASE 0 — Đo baseline trên 0.1.0

Nguồn: `docs/design/orchestra-redesign-v0.2.md` mục O (phase 0) + `ADJUSTMENTS-2026-10-07.md`.

## Phạm vi

- Đo baseline của kit 0.1.0 từ **dữ liệu thật đã có**: `D:\WMS\.orchestra` (registry, artifact, session,
  dấu phiên), lịch sử git của `D:\WMS`, `D:\WMS\app` và kit. Chỉ đọc, không ghi.
- Script đo chạy lại được: `tools/phase0_baseline.py`. Không bịa task; không chạy workflow mới.
- Đối chiếu `agents/*.md`, `commands/*.md` (đọc thật) với `SCHEMA.md` và với nhận định của v0.2.
- Không đổi hành vi `orc`.

## Acceptance criteria

- AC-0.1: Có bảng số cho các chỉ số trong mục O: thời gian, số lần dừng, số lần envelope bị từ chối,
  lỗi đọc nhầm. Chỉ số không đo được từ dữ liệu thì ghi rõ "không đo được" kèm lý do, không ước đoán.
- AC-0.2: Bảng số sinh ra bởi script chạy lại được, đầu ra tất định với cùng dữ liệu, script không ghi gì
  vào dự án được đo (test kiểm bằng hash cây thư mục trước/sau).
- AC-0.3: Số task thật ≥ 5; nếu < 5 thì ghi FINDING (không chặn Phase 1–2).
- AC-0.4: Ghi các chỗ lệch giữa agents/commands và SCHEMA / v0.2.
- AC-0.5: `python -m unittest discover -s tests` xanh toàn bộ (kể cả test cũ).

## Cách test

- `tests/test_phase0_baseline.py`: dựng dự án tạm bằng `orc` (init, task, artifact, envelope), chạy script,
  kiểm nhóm yêu cầu, đếm, và kiểm cây thư mục không đổi.
- Chạy script trên `D:\WMS` để sinh `docs/phases/PHASE-0-baseline.md`.

## Đọc agents/commands (bước 2 của brief)

Đọc được trực tiếp `agents/*.md` (4 file) và `commands/*.md` (6 file) trong worktree: đây là file thường
trong git, không phải junction. Giới hạn "protected" nêu trong v0.2 không còn; dòng cuối W8 đã kiểm.

Chỗ lệch so với `SCHEMA.md` và với nhận định của v0.2:

| # | Quan sát (file thật) | So với | Ý nghĩa |
|---|---|---|---|
| 1 | Có `commands/auto.md`; cây thư mục SCHEMA §3 chỉ liệt kê `plan,run,review,next,handoff` | SCHEMA §3 (§6b có nói /auto) | SCHEMA §3 lỗi thời |
| 2 | `reviewer` có tools `Read, Grep, Glob, Bash, Edit, Write` (cần Write để ghi report) | v0.2 J1: V3 chỉ Read/Grep/Glob + allowlist test | Khoảng cách cần xử lý ở Phase 7 |
| 3 | `researcher` có `WebFetch, WebSearch` **và** `Edit, Write, Bash` | v0.2 S5/P9 (suy luận) | Xác nhận: cùng một subagent vừa đọc web vừa ghi được |
| 4 | `coder` có `Bash`; quy tắc "chỉ sửa file khớp write_scope" chỉ nằm trong prompt | v0.2 H3 | Xác nhận |
| 5 | `auto.md` chặng 1 bước 5: Orchestrator tự chạy `orc new decision --status accepted` và `orc set <UND> status=accepted` | v0.2 H7 | Xác nhận: LLM ghi phê duyệt của Dung |
| 6 | `coder.md`/`reviewer.md`: evidence là mapping `{kind,result,summary}` tự điền | v0.2 H2 | Xác nhận |
| 7 | `auto.md` chặng 1 "luôn dừng chờ Dung" | ADJUSTMENTS #2 | Khớp điều chỉnh: giữ |
| 8 | `auto.md` bước 4 yêu cầu commit nhánh `orchestra/<ROOT>` nhưng `allowed-tools: Bash(orc *)` | chính nó | Commit dựa vào quyền ở settings dự án (A1 dòng Quyền), không do lệnh cấp |
| 9 | `reviewer.md`: chỉ dùng `orc show --pack`, không đọc summary của coder | v0.2 A2 | Khớp |

## Kết quả

Bảng số: `docs/phases/PHASE-0-baseline.md`, sinh bằng

```
python tools/phase0_baseline.py --project D:/WMS --app-repo app --map TASK-0006=a949af2
```

(`--map` vì commit app `a949af2` "Phase 3: danh bạ vận tải" không nhắc ID; ghép theo thời điểm commit
23:57:25 trùng commit gốc `a02657b` "TASK-0006..0015" 23:57:41.)

Tóm tắt baseline (28 task thật, 6 yêu cầu, 6 phiên):

| Chỉ số | Giá trị |
|---|---|
| Dừng chờ Dung ở chặng 1 | 4 (4 yêu cầu từ khi có chặng 1); 11 câu Dung chốt (DEC) |
| Phiên kết thúc blocked | 1 (S-0006) |
| Hook Stop chặn vì handoff chưa hợp lệ | 4 lần / 5 phiên có dấu |
| Envelope bị từ chối | **không đo được** (FINDING-2) |
| Thời gian | chỉ xấp xỉ bằng mtime: 1–24 phút/yêu cầu (TASK-0001 202 phút lẫn việc khác) (FINDING-2) |
| Review trả lại (attempts) | 1 (TASK-0025, IMPL_BUG đã xoá sau khi đạt) |
| EVD: tổng / do orc tự chạy | 125 / **0** — mọi bằng chứng là tự khai (H2) |
| EVD fail / info | 1 / 25 (phần lớn info là "chưa kiểm tay") |
| File commit ngoài write_scope | 0 / 34 file đổi (so theo yêu cầu; không tách được theo task vì commit gộp) |
| Review report còn `draft` | 19 / 20 (registry không phản ánh kết quả review) |

"Lỗi đọc nhầm": không có trường dữ liệu trực tiếp. Proxy đo được: attempts = 1, EVD fail = 1
(TASK-0025: `vite preview` dùng base `/`), 0 file ngoài scope. Ghi là proxy, không phải số đo.

Số task thật = 28 ≥ 5: không cần FINDING về số lượng.

FINDING mới: FINDING-1 (install.py theo tên thư mục), FINDING-2 (thiếu timestamp/log từ chối),
FINDING-3 (`*` khớp `/` trong write_scope). Chi tiết: `docs/phases/FINDINGS.md`.

## Test

`python -m unittest discover -s tests` trong worktree: **76 passed + 1 skipped (Ran 77)**.
- 74 test cũ + 3 test mới (`tests/test_phase0_baseline.py`).
- 1 skip: `test_install_is_idempotent_and_keeps_settings`, chỉ khi thư mục kit không tên `orchestra-kit`
  (FINDING-1). Chọn cách này vì không đổi `install.py` (bước release) và không đổi cách chạy test.
  Kiểm chứng: chép worktree sang thư mục tạm tên `orchestra-kit`, `python -m unittest tests.test_install`
  → 2/2 OK.
- Script chạy 2 lần trên `D:\WMS` cho đầu ra giống hệt; `git status` của `D:\WMS` và `D:\WMS\app` không đổi
  so với lúc bắt đầu phiên.

## AC

- AC-0.1 đạt (chỉ số không đo được ghi rõ). AC-0.2 đạt. AC-0.3 đạt (28). AC-0.4 đạt. AC-0.5 đạt.
