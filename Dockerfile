FROM python:3.10-slim

# 设置时区和非交互模式
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 安装基础依赖: ffmpeg (处理音频) 和 curl (下载工具)
RUN apt-get update && apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# 全局安装极速包管理工具 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# 设置工作目录
WORKDIR /app

# 拷贝核心管理脚本
COPY asr_manager.py .

# 设置环境变量，让脚本直接进入非交互式启动模式
ENV ASR_AUTO_START=true

# 暴露 WebSocket 端口
EXPOSE 10095

# 启动服务
CMD ["python3", "asr_manager.py"]
