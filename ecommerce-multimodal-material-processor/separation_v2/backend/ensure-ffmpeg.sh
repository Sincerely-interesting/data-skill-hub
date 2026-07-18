#!/bin/sh
# ============================================================================
# 入口脚本：容器每次启动自动确保 ffmpeg 可用
# ----------------------------------------------------------------------------
# 背景：电商打标网关对视频单元需要 ffmpeg 做"自适应压缩"，否则原样发送
#       触发 413 被跳过。
#
# 方案选择（按适用性排序）：
#   A) apt + 国内镜像源（默认）：ffmpeg deb 包仅几 MB，国内源秒级完成
#   B) 静态二进制兜底：约 40MB，适合无 apt 或网络特殊环境
#
# 位置约定：backend/ 根目录（与 gateway.py 同级，随 backend 上传进容器）
#
# 1Panel 启动命令：
#   sh ensure-ffmpeg.sh bash -c 'pip install ... && uvicorn ...'
# ============================================================================

set -e

ensure_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1; then
    echo "[ensure-ffmpeg] ffmpeg 已存在: $(command -v ffmpeg)"
    return 0
  fi
  echo "[ensure-ffmpeg] 未检测到 ffmpeg..."

  # ---- 方案A：apt + 国内镜像源（小包，国内秒级）----
  if command -v apt-get >/dev/null 2>&1; then
    echo "[ensure-ffmpeg] 使用 apt 安装（切换国内源）..."
    _codename="$(cat /etc/os-release 2>/dev/null | grep '^VERSION_CODENAME=' | cut -d= -f2 || echo trixie)"
    # 覆写为清华源（Debian 全架构支持）
    cat > /etc/apt/sources.list <<SOURCES
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ ${_codename} main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ ${_codename}-updates main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian-security ${_codename}-security main contrib non-free non-free-firmware
SOURCES
    # 清除可能的额外源（避免命中慢源）
    rm -f /etc/apt/sources.list.d/*.list 2>/dev/null || true
    echo "[ensure-ffmpeg] 已切换清华镜像 (${_codename})"
    apt-get update -qq && apt-get install -y --no-install-recommends ffmpeg
    rm -rf /var/lib/apt/lists/*
    echo "[ensure-ffmpeg] OK: $(command -v ffmpeg)"
    return 0
  fi

  # ---- 方案B：Alpine apk ----
  if command -v apk >/dev/null 2>&1; then
    echo "[ensure-ffmpeg] 使用 apk 安装..."
    apk add --no-cache ffmpeg
    echo "[ensure-ffmpeg] OK: $(command -v ffmpeg)"
    return 0
  fi

  # ---- 方案C：静态二进制兜底（~40MB，较慢）----
  _arch=""
  case "$(uname -m)" in
    x86_64|amd64)  _arch="amd64" ;;
    aarch64|arm64) _arch="arm64" ;;
    *)             _arch="amd64" ;;
  esac
  _url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${_arch}-static.tar.xz"
  echo "[ensure-ffmpeg] 下载静态 ffmpeg (${_arch})，约40MB请耐心等待..."

  if command -v wget >/dev/null 2>&1; then
    wget -qO /tmp/ffmpeg.tar.xz "$_url" \
      && tar xf /tmp/ffmpeg.tar.xz -C /tmp \
      && cp /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ \
      && chmod +x /usr/local/bin/ffmpeg \
      && rm -rf /tmp/ffmpeg-*-static /tmp/ffmpeg.tar.xz \
      && echo "[ensure-ffmpeg] OK: $(command -v ffmpeg)"
    return $?
  elif command -v curl >/dev/null 2>&1; then
    curl -sL "$_url" -o /tmp/ffmpeg.tar.xz \
      && tar xf /tmp/ffmpeg.tar.xz -C /tmp \
      && cp /tmp/ffmpeg-*-static/ffmpeg /usr/local/bin/ \
      && chmod +x /usr/local/bin/ffmpeg \
      && rm -rf /tmp/ffmpeg-*-static /tmp/ffmpeg.tar.xz \
      && echo "[ensure-ffmpeg] OK: $(command -v ffmpeg)"
    return $?
  fi

  echo "[ensure-ffmpeg] 无可用安装方式，跳过" >&2
}

ensure_ffmpeg || true
exec "$@"
