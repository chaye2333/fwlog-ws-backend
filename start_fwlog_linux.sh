#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="${SCRIPT_DIR}/fwlog_ws_backend"
VENV_DIR="${BOT_DIR}/.venv"
SESSION_NAME="fwlog_bot"
REQ_FILE="${BOT_DIR}/requirements.txt"

echo "=== fwlog 聊天记录转海豹日志工具 一键启动脚本 ==="

if [ ! -d "${BOT_DIR}" ]; then
  echo "未找到 fwlog_ws_backend 目录，请确认脚本放在项目根目录。"
  exit 1
fi

# Python check and install
if command -v python3 >/dev/null 2>&1; then
  echo "检测到 python3：$(python3 --version)"
else
  echo "未检测到 python3。"
  read -r -p "是否自动安装 python3（需要 root / sudo 权限）？[y/N] " yn
  case "$yn" in
    [Yy]*)
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
      elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y python3 python3-venv python3-pip || sudo yum install -y python3
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-venv python3-pip || sudo dnf install -y python3
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm python
      else
        echo "无法自动识别包管理器，请手动安装 python3 后重试。"
        exit 1
      fi
      ;;
    *)
      echo "已取消自动安装 python3。"
      exit 1
      ;;
  esac
fi

# Screen check and install
if ! command -v screen >/dev/null 2>&1; then
  echo "未检测到 screen。"
  read -r -p "是否自动安装 screen？[y/N] " yn
  case "$yn" in
    [Yy]*)
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y screen
      elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y screen
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y screen
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm screen
      else
        echo "无法自动识别包管理器，请手动安装 screen 后重试。"
        exit 1
      fi
      ;;
    *)
      echo "已取消自动安装 screen。"
      exit 1
      ;;
  esac
fi

echo "准备虚拟环境：${VENV_DIR}"
if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
if [ -f "${REQ_FILE}" ]; then
  echo "使用 requirements.txt 安装依赖：${REQ_FILE}"
  pip install -r "${REQ_FILE}"
else
  echo "未找到 requirements.txt，正在安装 websockets..."
  pip install websockets==10.4
fi
deactivate

if screen -list | grep -q "[.]${SESSION_NAME}"; then
  echo "检测到已存在的 screen 会话：${SESSION_NAME}"
  read -r -p "是否重启该会话？[y/N] " yn
  case "$yn" in
    [Yy]*)
      screen -S "${SESSION_NAME}" -X quit || true
      ;;
    *)
      echo "保持原有会话不变。"
      echo "你可以通过以下命令查看或进入会话："
      echo "  screen -ls"
      echo "  screen -r ${SESSION_NAME}"
      exit 0
      ;;
  esac
fi

echo "在 screen 会话 ${SESSION_NAME} 中启动 fwlog_ws_bot.py ..."
# Correctly set CWD and activate venv inside screen
screen -dmS "${SESSION_NAME}" bash -c "cd \"${SCRIPT_DIR}\" && source \"${VENV_DIR}/bin/activate\" && python3 fwlog_ws_backend/fwlog_ws_bot.py"

echo "启动完成。"
echo "查看会话：screen -ls"
echo "进入会话：screen -r ${SESSION_NAME}"
