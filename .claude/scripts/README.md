# Worktree 环境预热脚本

在新 worktree 里一把梭建立开发环境，消除重复踩坑（编码错误、装依赖等待）。

## 用法

在**新 worktree 的项目根目录**下执行：

**Windows (PowerShell)**
```powershell
.claude/scripts/init-worktree.ps1
```

**Unix/Linux/macOS (bash)**
```bash
.claude/scripts/init-worktree.sh
```

## 功能

1. 创建后端 `backend/.venv`（如不存在）
2. 设置 `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`（消除 Windows GBK 编码坑）
3. 安装后端依赖 `pip install -r backend/requirements.txt`
4. 安装前端依赖 `npm install`
5. 验证环境可用

## 参数

- `--SkipBackend` / `--skip-backend`：跳过后端环境
- `--SkipFrontend` / `--skip-frontend`：跳过前端环境

## 何时使用

- 新建 worktree 后首次开发前
- 切换到旧 worktree 但依赖已过期
- 协作者首次拉取代码

## 后续步骤

环境预热完成后：
- 后端激活（Windows）：`cd backend && .venv\Scripts\Activate.ps1`
- 后端激活（Unix）：`cd backend && source .venv/bin/activate`
- 前端启动：`cd frontend && npm run dev`
- 后端启动：`cd backend && uvicorn src.app:app --reload`

## 排查

如遇编码错误，手动设置：
```powershell
# PowerShell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```
```bash
# bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
```
