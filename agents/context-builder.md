---
name: context-builder
description: (Chưa dùng — giai đoạn sau theo D7.) Dựng gói ngữ cảnh CTX cho một TASK từ KNOWLEDGE_MAP và code. Không gọi agent này trong MVP.
tools: Read, Grep, Glob
---

**Placeholder (D7).** Trong MVP, Orchestrator không gọi agent này. Gói ngữ cảnh
(CTX-x) được tạo tay bằng `orc new context --task TASK-x --summary "..." --paths ...`.

Giai đoạn sau: đọc `.orchestra/knowledge/KNOWLEDGE_MAP.md` và code để viết
`.orchestra/contexts/<CTX-ID>.md` (file cần đọc, đoạn trích, quy ước), trả envelope YAML
như các agent khác. Graphify (tự dựng KNOWLEDGE_MAP) và chạy song song nhiều Coder
bằng git worktree cũng để giai đoạn sau.
