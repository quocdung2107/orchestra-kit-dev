@echo off
rem Chạy orc của bố cục plugin từ terminal, dùng khi thử nhánh packaging.
rem Trỏ tới worktree C:\Users\quocd\orchestra-kit-pkg; bản cài thật (marketplace) nằm trong
rem ~/.claude/plugins/... và Claude Code tự thêm plugins/orchestra/bin vào PATH của phiên.
rem `orc` trong PATH của user vẫn là kit cũ (C:\Users\quocd\orchestra-kit\cli) cho WMS/Koinonia.
python "%~dp0..\plugins\orchestra\bin\orc" %*
