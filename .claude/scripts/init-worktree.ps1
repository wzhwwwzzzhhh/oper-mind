# OperMind worktree 环境预热脚本 (Windows PowerShell)
# 用法：在新 worktree 根目录下执行 `.claude/scripts/init-worktree.ps1`
# 功能：建 venv、设 UTF-8 编码、装后端依赖、装前端依赖

param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

Write-Host "==> OperMind worktree 环境预热 (PowerShell)" -ForegroundColor Cyan

# 检查是否在项目根目录
if (-not (Test-Path "backend/requirements.txt") -or -not (Test-Path "frontend/package.json")) {
    Write-Host "错误：请在项目根目录下执行此脚本" -ForegroundColor Red
    exit 1
}

# 1. 后端环境
if (-not $SkipBackend) {
    Write-Host "`n[1/4] 创建后端 venv..." -ForegroundColor Green
    if (Test-Path "backend/.venv") {
        Write-Host "  .venv 已存在，跳过" -ForegroundColor Yellow
    } else {
        Push-Location backend
        python -m venv .venv
        Pop-Location
        Write-Host "  .venv 已创建" -ForegroundColor Green
    }

    Write-Host "`n[2/4] 设置 UTF-8 编码并安装后端依赖..." -ForegroundColor Green
    # 设置环境变量（当前会话有效）
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Push-Location backend
    & .venv\Scripts\pip.exe install --upgrade pip
    & .venv\Scripts\pip.exe install -r requirements.txt
    Pop-Location
    Write-Host "  后端依赖已安装" -ForegroundColor Green
} else {
    Write-Host "`n[1-2/4] 跳过后端环境（--SkipBackend）" -ForegroundColor Yellow
}

# 2. 前端环境
if (-not $SkipFrontend) {
    Write-Host "`n[3/4] 安装前端依赖..." -ForegroundColor Green
    Push-Location frontend
    npm install
    Pop-Location
    Write-Host "  前端依赖已安装" -ForegroundColor Green
} else {
    Write-Host "`n[3/4] 跳过前端环境（--SkipFrontend）" -ForegroundColor Yellow
}

# 3. 验证
Write-Host "`n[4/4] 验证环境..." -ForegroundColor Green
$allGood = $true

if (-not $SkipBackend) {
    if (Test-Path "backend/.venv/Scripts/python.exe") {
        Write-Host "  ✓ 后端 venv 可用" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 后端 venv 不可用" -ForegroundColor Red
        $allGood = $false
    }
}

if (-not $SkipFrontend) {
    if (Test-Path "frontend/node_modules") {
        Write-Host "  ✓ 前端 node_modules 可用" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 前端 node_modules 不可用" -ForegroundColor Red
        $allGood = $false
    }
}

if ($allGood) {
    Write-Host "`n✓ 环境预热完成！" -ForegroundColor Green
    Write-Host "  后端激活：cd backend && .venv\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "  前端启动：cd frontend && npm run dev" -ForegroundColor Cyan
} else {
    Write-Host "`n✗ 环境预热有错误，请检查日志" -ForegroundColor Red
    exit 1
}
