#!/usr/bin/env bash
# OperMind worktree 环境预热脚本 (Unix/Linux/macOS)
# 用法：在新 worktree 根目录下执行 `.claude/scripts/init-worktree.sh`
# 功能：建 venv、设 UTF-8 编码、装后端依赖、装前端依赖

set -e

SKIP_BACKEND=false
SKIP_FRONTEND=false

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-backend)
      SKIP_BACKEND=true
      shift
      ;;
    --skip-frontend)
      SKIP_FRONTEND=true
      shift
      ;;
    *)
      echo "未知参数: $1"
      echo "用法: $0 [--skip-backend] [--skip-frontend]"
      exit 1
      ;;
  esac
done

echo "==> OperMind worktree 环境预热 (bash)"

# 检查是否在项目根目录
if [[ ! -f "backend/requirements.txt" ]] || [[ ! -f "frontend/package.json" ]]; then
  echo "错误：请在项目根目录下执行此脚本"
  exit 1
fi

# 1. 后端环境
if [[ "$SKIP_BACKEND" == false ]]; then
  echo -e "\n[1/4] 创建后端 venv..."
  if [[ -d "backend/.venv" ]]; then
    echo "  .venv 已存在，跳过"
  else
    cd backend
    python3 -m venv .venv
    cd ..
    echo "  .venv 已创建"
  fi

  echo -e "\n[2/4] 设置 UTF-8 编码并安装后端依赖..."
  # 设置环境变量
  export PYTHONUTF8=1
  export PYTHONIOENCODING=utf-8

  cd backend
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  cd ..
  echo "  后端依赖已安装"
else
  echo -e "\n[1-2/4] 跳过后端环境（--skip-backend）"
fi

# 2. 前端环境
if [[ "$SKIP_FRONTEND" == false ]]; then
  echo -e "\n[3/4] 安装前端依赖..."
  cd frontend
  npm install
  cd ..
  echo "  前端依赖已安装"
else
  echo -e "\n[3/4] 跳过前端环境（--skip-frontend）"
fi

# 3. 验证
echo -e "\n[4/4] 验证环境..."
ALL_GOOD=true

if [[ "$SKIP_BACKEND" == false ]]; then
  if [[ -f "backend/.venv/bin/python" ]]; then
    echo "  ✓ 后端 venv 可用"
  else
    echo "  ✗ 后端 venv 不可用"
    ALL_GOOD=false
  fi
fi

if [[ "$SKIP_FRONTEND" == false ]]; then
  if [[ -d "frontend/node_modules" ]]; then
    echo "  ✓ 前端 node_modules 可用"
  else
    echo "  ✗ 前端 node_modules 不可用"
    ALL_GOOD=false
  fi
fi

if [[ "$ALL_GOOD" == true ]]; then
  echo -e "\n✓ 环境预热完成！"
  echo "  后端激活：cd backend && source .venv/bin/activate"
  echo "  前端启动：cd frontend && npm run dev"
else
  echo -e "\n✗ 环境预热有错误，请检查日志"
  exit 1
fi
