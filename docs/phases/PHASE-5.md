# PHASE 5 — `orc triage` ở shadow (Dung duyệt 2026-10-09: "triage chạy shadow, chưa release K lên WMS")

Nguồn: v0.2 H1–H3 (bảng tiêu chí, 3 lần tính, đơn điệu, hạ mức chỉ bằng `orc:downgrade`), F1 (research mode),
mục O phase 5; ADJUSTMENTS #2 (chặng hiểu luôn dừng), #6 (level tăng đơn điệu; kích thước chỉ để nâng; nhỏ không mặc
định an toàn).

## Phạm vi

1. `cli/orc_triage.py` — tính level tất định từ:
   - tín hiệu máy: đường dẫn khớp `risk_paths` L3, số file, số dòng diff, số module ("module" = tối đa 2 cấp thư mục
     dưới `module_roots` của config; mặc định 2 cấp thư mục đầu);
   - form khai báo (có/không): L3 `schema_change, data_migration, security, irreversible`;
     L2 `public_api, new_dependency, external_service, user_visible, uncertain`.
   - Mức = max các luật khớp. Không đủ dữ kiện ⇒ tối thiểu L1 (không bao giờ mặc định L0). L0 chỉ khi file ≤ 2,
     1 module, mọi cờ form **được khai rõ là không**, và (ở lần 3) diff ≤ 40 dòng.
   - Ngưỡng mặc định theo bảng H2, chỉnh được ở `config.triage`.
2. Ba lần tính: lần 1 khi task gốc K vào TRIAGED (form + đường dẫn dự kiến nếu có), lần 2 khi vào PLANNED
   (write_scope các task coder, đếm file thật bằng `git ls-files`), lần 3 khi vào VERIFYING (file đổi + số dòng diff
   kể từ checkpoint). Mỗi lần: `level = max(level lần trước, level tính)` — chỉ tăng.
3. **Shadow:** kết quả ghi journal `event: triage` (+ `runtime/shadow.jsonl`), in cho A; **không** ghi `task.level`,
   không đổi luồng K (mọi yêu cầu vẫn APPROVAL_REQUIRED). `orc triage run|show ID`.
4. Hạ mức: `orc triage downgrade ID --to L` chỉ khi Dung gõ `orc:downgrade ID L<n> <lý do>`; ở shadow chỉ ghi nhận.
5. `tools/phase5_triage_replay.py`: tính triage hồi cứu (lần 2 + lần 3) cho các yêu cầu thật đã có trong `D:\WMS`
   (chỉ đọc), ra bảng để Dung điền mức tự đánh giá.

Ngoài phạm vi: bật triage thật (ghi `task.level`, mở READY_FOR_IMPLEMENTATION), research mode `full` /
researcher-external (Phase 6–7), release K lên WMS.

## AC

- AC-5.1: Bảng luật H2 đúng (test từng luật, max, ngưỡng từ config).
- AC-5.2: Đơn điệu: lần sau không thấp hơn lần trước; hạ mức chỉ với lời Dung.
- AC-5.3: Shadow: `task.level` không đổi, luồng K không đổi; journal có 3 dòng triage cho một vòng K.
- AC-5.4: Không bao giờ mặc định L0 khi thiếu dữ kiện.
- AC-5.5: Bảng hồi cứu trên dữ liệu thật của WMS (chỉ đọc, git sạch).
- AC-5.6: Toàn bộ test xanh.
- **Cổng v0.2 cần dữ liệu thật — boundary:** "lệch mức với Dung ≤ 1/10, không lần nào hạ thấp L3" trên 10 task.

## Kết quả

Code: `cli/orc_triage.py` (mới), `cli/orc_k.py` (tự chạy triage lần 1/2/3 khi gốc vào TRIAGED/PLANNED/VERIFYING —
shadow, lỗi triage không chặn K), `cli/orc_core.py` (`orc triage run|show|downgrade`), `tools/phase5_triage_replay.py`.

Triage hồi cứu trên 8 yêu cầu thật của D:\WMS (`PHASE-5-triage-replay.md`; `--module-roots app/src`; chỉ đọc, git
sạch): L1 ×1 (TASK-0028, không có code), L2 ×1 (TASK-0001), L3 ×6. Quan sát để hiệu chỉnh (không tự đổi ngưỡng H2):
- "module" = 2 cấp thư mục dưới root ⇒ `app/tests` luôn là 1 module riêng; việc nhỏ chạm 1 tính năng + test đã thành
  2 module ⇒ L2 (TASK-0001: 3 file, 66 dòng).
- Ngưỡng "> 3 module ⇒ L3" đẩy TASK-0003 (4 file, 45 dòng, chặn file > 20 MB) lên L3 vì chạm 4 thư mục.
- 4/6 yêu cầu L3 có lý do tin cậy (migration, workflow GitHub, > 400 dòng).
Form khai báo không có trong dữ liệu cũ ⇒ hồi cứu chỉ có tín hiệu máy (form thật chỉ nâng thêm).

Giới hạn: triage chỉ tự chạy trong vòng K, mà K chưa release lên WMS ⇒ chưa có triage shadow "sống" trên task thật;
số dòng lần 3 tính cả file test/tài liệu; bảng hồi cứu đếm file theo cây hiện tại (không theo thời điểm commit).

## Test

`python -m unittest discover -s tests`: **163 passed + 1 skipped (Ran 164)** — 157 cũ + 7 mới (`tests/test_phase5.py`).

## AC

AC-5.1 … AC-5.6 đạt. **Cổng v0.2 (lệch ≤ 1/10 so với Dung, không hạ thấp L3) — boundary:** cần Dung điền mức tự đánh
giá cho các yêu cầu (bảng hồi cứu: 8 yêu cầu) và/hoặc chạy shadow sống sau khi release K.

## Hiệu chỉnh theo Dung (2026-10-09 13:39: "Tổ hợp: B, Từ khoá: có")

Mức Dung tự đánh giá 8 yêu cầu: L3, L2, L3, L3, L3, L1, L3, L3. Luật ban đầu lệch 2/8, hạ thấp L3 1 lần (TASK-0001
chống CSV injection: việc bảo mật không có dấu hiệu máy đo được).
- **B:** "> 3 module ⇒ L3" chỉ khi diff > 120 dòng (`l3.modules_min_lines: 120`); test vẫn tính module riêng.
- **Từ khoá rủi ro ⇒ L3** (`risk_keywords_l3`, chỉ nâng) trên tiêu đề + tóm tắt yêu cầu: bảo mật, security, injection,
  xss, csrf, auth, đăng nhập, phân quyền, quyền truy cập, rls, mật khẩu, password, secret, api key, xoá/xóa dữ liệu,
  migration. Từ ASCII khớp nguyên từ. **Bỏ "token"** khỏi danh sách gợi ý: tóm tắt TASK-0028 có `{{ .Token }}` (biến
  template) ⇒ báo nhầm L3.
- Bảng hồi cứu chỉ khớp từ khoá trên **tiêu đề** (tóm tắt trong dữ liệu cũ viết sau khi làm xong).

Kết quả hồi cứu sau hiệu chỉnh (`PHASE-5-triage-replay.md`): **lệch 0/8, hạ thấp L3: 0**.
**Giới hạn của con số này:** luật được chỉnh trên chính 8 mẫu ⇒ đây là tập hiệu chỉnh, không phải kiểm độc lập; cổng
v0.2 cần 10 task. Kiểm độc lập cần triage chạy sống trên task mới (sau khi release K) hoặc thêm mẫu mới.

Test: **164 passed + 1 skipped (Ran 165)** — thêm test từ khoá, luật B.
