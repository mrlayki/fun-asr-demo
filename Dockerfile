# 运维 Linux + NVIDIA GPU 用；Mac 或无 GPU 请用 Dockerfile.mac（见 docker-compose.mac.yml）
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# 设置时区和非交互模式
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 安装 Python 3.10、ffmpeg、curl
RUN apt-get update && apt-get install -y \
    python3.10 python3-pip python3.10-venv \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# 让 python3 指向 python3.10
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

# 全局安装极速包管理工具 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# 设置工作目录
WORKDIR /app

# 拷贝核心文件 (包括我们修复过的服务端脚本)
COPY asr_manager.py .
COPY funasr_wss_server.py .
COPY model.py ctc.py ./
COPY tools/ ./tools/

# 设置环境变量，让脚本直接进入非交互式启动模式
ENV ASR_AUTO_START=true

# 暴露 WebSocket 端口
EXPOSE 10095

# 启动服务
CMD ["python3", "asr_manager.py"]
