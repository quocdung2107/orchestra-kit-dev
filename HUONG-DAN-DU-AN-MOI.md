# Áp dụng orchestra-kit cho dự án mới — ví dụ Koinonia

Kit và Graphify đã cài trên máy này (dùng chung mọi dự án), nên mỗi dự án mới chỉ cần
khoảng 10 phút. Mỗi dự án có `.orchestra/` riêng, tri thức không trộn (D6).

## Khảo sát D:\Bible (2026-10-06, chỉ đọc)

| Thư mục | Tình trạng | Áp dụng? |
|---|---|---|
| `koinonia-bible` | App chính: Electron + React/TS (renderer) + Python backend; GitHub `quocdung2107/koinonia-bible-app`; **56 file đang sửa dở** | **Có — làm trước** |
| `kononia`, `KoinoNet`, `koinonia-site` | git chưa có commit nào | Để sau, khi quay lại làm |

Dựng thử graph `koinonia-bible` vào thư mục tạm (không đụng dự án): renderer 312 file / 2.253 node,
backend 27 file / 519 node, electron 49 file / 426 node, remote-client 12 file / 63 node — lần đầu ~17 giây.

## Các bước cho `D:\Bible\koinonia-bible`

Mở VS Code ở `D:\Bible\koinonia-bible`, mở terminal (PowerShell).

**1. Cất việc dở trước** (để commit orchestra không lẫn code đang sửa):

```powershell
git status
```

Commit hoặc stash 56 file đang đổi theo cách anh/chị vẫn làm.

**2. Khởi tạo** — `CLAUDE.md` đã có nên `orc init` không ghi đè:

```powershell
orc init --project-id koinonia-bible --goal "App Kinh Thánh Koinonia: đọc, ghi chú, trình chiếu (Studio/Presentation) trên Electron; backend Python SQLite."
```

**3. Bật graph** — thêm vào cuối `.orchestra\config.yaml`:

```yaml
graph:
  engine: graphify
  max_files: 12
  max_results: 40
  hub_degree: 25
  roots:
    - {path: renderer, include: [src]}
    - {path: backend}
    - {path: electron}
    - {path: remote-client, include: [src]}
```

```powershell
orc graph update
orc graph status
orc graph view --open
```

`status` phải là `fresh`, khoảng 400 file.

**4. Thêm mục Orchestra vào `CLAUDE.md`** (giữ nguyên nội dung cũ, dán thêm cuối file):

```markdown
## Orchestra (đa-agent)
- Trạng thái công việc trong `.orchestra/`; chỉ lệnh `orc` ghi `.orchestra/state/`.
- Đầu phiên có brief tự nạp. Yêu cầu mới: `/auto <yêu cầu>` (hiểu & thiết kế → hỏi Dung → plan → code → review → báo cáo).
- `HANDOFF_VSCODE.md` và `VIEC_CON_TON_DONG.md` vẫn dùng song song.
- Graph code: `orc graph status|view`. Graph không thấy lời gọi RPC bằng chuỗi renderer → backend Python,
  và không chứa `renderer/locales/*.json` (quy tắc vi/en vẫn theo mục Conventions).
- Lệnh kiểm: `cd renderer && ../node_modules/.bin/tsc --noEmit -p tsconfig.json` và
  `npx vite build --config renderer/vite.config.ts`.
```

**5. Viết `KNOWLEDGE_MAP.md`** — mở phiên Claude Code mới trong dự án, gõ:

> Đọc code thật và HANDOFF_VSCODE.md, viết `.orchestra/knowledge/KNOWLEDGE_MAP.md` 8–10 node domain
> (Group Lock, Output Lock, Routing Editor, slide v2, backend RPC…), mỗi node có Code: đường dẫn. Không sửa code.

**6. Cho phép agent chạy lệnh kiểm** — tạo `.claude\settings.json` (dự án đã có `settings.local.json`, không đụng):

```json
{
  "permissions": {
    "allow": [
      "Bash(npx vite build *)", "Bash(npx vitest *)", "Bash(npm run test:prod)",
      "Bash(git status *)", "Bash(git status)", "Bash(git diff *)", "Bash(git diff)",
      "Bash(git log *)", "Bash(git add *)", "Bash(git commit *)", "Bash(git checkout -b *)"
    ]
  }
}
```

**7. Commit riêng phần orchestra**:

```powershell
orc validate
git add .orchestra CLAUDE.md .claude/settings.json
git commit -m "Thêm orchestra-kit"
```

Lưu ý: repo này có remote GitHub, nên khi push thì `.orchestra/` (plan, quyết định, handoff) cũng lên GitHub.
Cache graph nằm trong `.orchestra/cache/` đã được gitignore.

**8. Dùng**: bấm **New session**, gõ `/auto <yêu cầu>`. Xem bản đồ code: `orc graph view --open`.

## Dự án khác (mẫu chung)

1. `orc init --project-id <ten> --goal "<mục tiêu một câu>"`
2. Thêm `graph.roots` theo thư mục code thật. Không đặt root ở thư mục bị `.gitignore` của repo cha loại (lỗi F1).
3. `orc graph update` → `fresh` → `orc graph view --open`
4. Mục Orchestra trong CLAUDE.md, KNOWLEDGE_MAP 5–10 node, `.claude/settings.json`, commit riêng.
