# FunASR 实时语音转写本地独立服务 (UV 加持版)

本项目是基于阿里 [FunASR](https://github.com/modelscope/FunASR) 核心源码深度精简、跨平台自适应封装的本地/生产环境级实时语音识别微服务。

通过现代化的包管理器 `uv` 进行运行时隔离，它不仅能够优雅地在你的 Mac 本地启动调试，也能通过提供的 `docker-compose.yml` 在 Linux + GPU 的生产环境中实现一键裸金属级别的极致部署体验。

## 🎯 核心能力与亮点

- **真正的跨平台**：内置了针对复杂环境（如 Intel Mac 的 `llvmlite` 编译失败、NumPy 2.0 ABI 崩溃等）的动态防御代码，本地开发与生产环境隔离互不影响。
- **纯粹且轻量**：没有庞杂的中间层代码，直连原汁原味的官方 WebSocket 推理引擎。
- **性能拉满**：支持在线流式识别（2pass-online）与离线端点精准断句纠错（2pass-offline）融合输出；自动识别并在有条件时使用 GPU 推理。
- **开箱即用的调试套件**：附带极致美观的原生 H5 前端测试页面，方便你与业务侧联调。

---

## 🛠️ 如何启动服务

### 方案 A: 开发者本地测试 (Mac / Windows / Linux)

只需确保你的机器上安装了 Python 3.10+ 和包管理器 [uv](https://docs.astral.sh/uv/)。

```bash
# 启动管理脚本
python3 asr_manager.py

# 按照提示输入 `1` 即可
```
*初次启动会自动在 `temp_asr_models` 目录下缓存约 2.3GB 的模型文件，之后均可秒起。*

### 方案 B: 运维生产环境部署 (推荐使用 Docker)

为了最大限度发挥算力并保持环境绝对纯净，将本项目交付给运维时，推荐使用 Docker。

**前置要求**：
- Linux 服务器。
- 安装好 Docker 与 Docker Compose。
- 安装好 Nvidia 显卡驱动及 NVIDIA Container Toolkit。

**一键拉起**：
```bash
docker-compose up -d --build
```
*配置已默认开启了 `NVIDIA_VISIBLE_DEVICES=all` 和 GPU 透传能力。*

---

## 📖 业务端对接指南

- **调试页面**：保持服务端开启，用浏览器直接双击打开项目中的 `index.html` 即可看到炫酷的实时测试工具。
- **API 文档**：请查阅本目录下的 [API_INTEGRATION_GUIDE.md](./API_INTEGRATION_GUIDE.md)，内含详尽的 WebSocket 握手参数、热词使用方式以及原生 JS 接入范例。

---

## 📂 目录结构说明

```text
.
├── asr_manager.py              # 服务核心拉起与环境隔离脚手架 (主入口)
├── funasr_wss_server.py        # 首次运行时自动从官方拉取的 WebSocket 服务端脚本
├── temp_asr_models/            # 动态下载的模型缓存大文件 (切勿提交到 Git)
├── Dockerfile                  # GPU 生产环境的容器镜像定义文件
├── docker-compose.yml          # GPU 生产环境的一键编排配置
├── index.html                  # 精美的前端 WebSocket 录音/降采样/实时展示调试终端
└── API_INTEGRATION_GUIDE.md    # 标准化交接的 API 对接说明书
```
