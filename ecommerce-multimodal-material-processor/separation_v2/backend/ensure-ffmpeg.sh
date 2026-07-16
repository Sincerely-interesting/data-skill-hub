#!/bin/sh
# ============================================================================
# 入口脚本：容器每次启动自动确保 ffmpeg 可用
# ----------------------------------------------------------------------------
# 背景：电商打标网关对视频单元需要 ffmpeg 做"自适应压缩"，否则原样发送
#       触发 413 被跳过（服务端无 ffmpeg 时日志会打印该提示）。
#       但容器重建/重拉镜像后 ffmpeg 会丢，每次手动进终端装很麻烦。
#       本脚本在网关启动前自检并安装 ffmpeg，然后"接力"执行原启动命令。
#
# 位置约定：本文件必须放在 backend/ 根目录（与 gateway.py 同级），
#           因为部署时只上传 backend/ 内的文件，外围目录不会被传上去。
#
# 1Panel 用法（运行环境 → Python 创建的应用）：
#   1) 把 backend/ 整目录上传（本脚本随之进容器，假设挂载点为 /app 或项目根）
#   2) 应用「启动命令」填（工作目录已指向 backend 挂载点）：
#         sh ensure-ffmpeg.sh python gateway.py
#   3) 保存并重建/重启容器。之后每次启动都会自动装好 ffmpeg。
# ============================================================================

set -e

ensure_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1; then
    echo "[ensure-ffmpeg] ffmpeg 已存在: $(command -v ffmpeg)"
    return 0
  fi
  echo "[ensure-ffmpeg] 未检测到 ffmpeg，尝试安装..."

  # Debian / Ubuntu 系（本容器实测为 Debian 13 trixie，apt-get 在 /usr/bin）
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update \
      && apt-get install -y ffmpeg \
      && rm -rf /var/lib/apt/lists/*
  # Alpine 系
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache ffmpeg
  else
    echo "[ensure-ffmpeg] 未找到受支持的包管理器(apt-get/apk)，跳过安装" >&2
  fi
}

# 装不上也不阻塞网关启动（视频单元会降级为原样发送/跳过，图片不受影响）
ensure_ffmpeg || true

# 接力执行容器原本的命令（如 python gateway.py），并替换当前进程，
# 这样网关进程拿到 PID 1 信号，重启/停止都正常。
exec "$@"
