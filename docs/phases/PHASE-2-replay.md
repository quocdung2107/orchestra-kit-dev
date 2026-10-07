# Phase 2 — phát lại yêu cầu thật với `orc verify`

Sinh bởi `tools/phase2_replay.py` trên bản clone tạm (nguồn chỉ đọc).

## Kết quả orc theo yêu cầu

| Yêu cầu | Commit (gốc/app) | Lệnh (kết quả, giây, số test) | Ngoài write_scope | Nghi bí mật | Risk path |
|---|---|---|---|---|---|
| TASK-0001 | 21ff20b/904d9db | build pass 5.5s ; lint fail 1.0s ; test pass 0.9s {'pass': 8, 'fail': 0} | 0 | 0 | - |
| TASK-0003 | df0413f/429ca0e | build pass 5.2s ; lint fail 1.1s ; test pass 0.9s {'pass': 13, 'fail': 0} | 0 | 0 | - |
| TASK-0006 | a02657b/a949af2 | build pass 5.3s ; lint fail 1.0s ; test pass 0.9s {'pass': 20, 'fail': 0} | 0 | 0 | supabase/migrations/20261007000000_carriers_base.sql, supabase/migrations/20261007000100_carriers_community.sql, supabase/migrations/20261007000200_carriers_claim.sql |
| TASK-0016 | b530516/5f3f69f | build pass 5.4s ; lint fail 1.0s ; test pass 0.9s {'pass': 30, 'fail': 0} | 0 | 0 | - |
| TASK-0023 | f82a576/3056913 | build pass 5.5s ; lint fail 1.0s ; test pass 0.9s {'pass': 30, 'fail': 0} | 0 | 0 | app/.github/workflows/deploy.yml |

## So với EVD tự khai (từng task coder)

| Yêu cầu | Task | Kind | orc | Tự khai pass | Tự khai khác | Kết luận |
|---|---|---|---|---|---|---|
| TASK-0001 | TASK-0002 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0001 | TASK-0002 | build | pass | 2 | 0 | khớp |
| TASK-0001 | TASK-0002 | lint | fail | 2 | 0 | LỆCH |
| TASK-0001 | TASK-0002 | test | pass | 2 | 0 | khớp |
| TASK-0003 | TASK-0004 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0003 | TASK-0004 | build | pass | 0 | 0 | không có tự khai |
| TASK-0003 | TASK-0004 | lint | fail | 2 | 0 | LỆCH |
| TASK-0003 | TASK-0004 | test | pass | 2 | 0 | khớp |
| TASK-0003 | TASK-0005 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0003 | TASK-0005 | build | pass | 2 | 0 | khớp |
| TASK-0003 | TASK-0005 | lint | fail | 2 | 0 | LỆCH |
| TASK-0003 | TASK-0005 | test | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0008 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0008 | build | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0008 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0008 | test | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0009 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0009 | build | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0009 | lint | fail | 2 | 0 | LỆCH |
| TASK-0006 | TASK-0009 | test | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0010 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0010 | build | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0010 | lint | fail | 2 | 0 | LỆCH |
| TASK-0006 | TASK-0010 | test | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0011 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0011 | build | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0011 | lint | fail | 2 | 0 | LỆCH |
| TASK-0006 | TASK-0011 | test | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0012 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0012 | build | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0012 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0012 | test | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0013 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0013 | build | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0013 | lint | fail | 2 | 0 | LỆCH |
| TASK-0006 | TASK-0013 | test | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0014 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0014 | build | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0014 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0014 | test | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0015 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0006 | TASK-0015 | build | pass | 2 | 0 | khớp |
| TASK-0006 | TASK-0015 | lint | fail | 2 | 0 | LỆCH |
| TASK-0006 | TASK-0015 | test | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0018 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0018 | build | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0018 | lint | fail | 2 | 0 | LỆCH |
| TASK-0016 | TASK-0018 | test | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0019 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0019 | build | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0019 | lint | fail | 2 | 0 | LỆCH |
| TASK-0016 | TASK-0019 | test | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0020 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0020 | build | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0020 | lint | fail | 2 | 0 | LỆCH |
| TASK-0016 | TASK-0020 | test | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0021 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0021 | build | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0021 | lint | fail | 2 | 0 | LỆCH |
| TASK-0016 | TASK-0021 | test | pass | 2 | 0 | khớp |
| TASK-0016 | TASK-0022 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0016 | TASK-0022 | build | pass | 3 | 0 | khớp |
| TASK-0016 | TASK-0022 | lint | fail | 3 | 0 | LỆCH |
| TASK-0016 | TASK-0022 | test | pass | 3 | 0 | khớp |
| TASK-0023 | TASK-0025 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0025 | build | pass | 4 | 0 | khớp |
| TASK-0023 | TASK-0025 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0025 | test | pass | 3 | 0 | khớp |
| TASK-0023 | TASK-0026 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0026 | build | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0026 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0026 | test | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0027 | scope | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0027 | build | pass | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0027 | lint | fail | 0 | 0 | không có tự khai |
| TASK-0023 | TASK-0027 | test | pass | 0 | 0 | không có tự khai |

**LỆCH (tự khai pass, orc fail): 13**
