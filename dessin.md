# 角色定义
你是一个资深的全栈 AI 应用架构师和高级开发工程师。请根据以下需求文档，为我从零开始编写一个“门诊诊间语音识别与病历生成系统”。

# 核心业务场景
医生坐在科室与患者面诊，在 PC 网页端开启录音。系统需要实时将医生的语音转写为文字（支持实时预览与修正）。问诊结束后，系统自动根据完整的转写文本，生成结构化的门诊病历，并进行医疗规则质控。
*注：第一阶段基于 FunASR 实现普通话实时识别闭环；系统架构必须预留方言模型替换能力。上海话、四川话等方言支持作为后续模型评估与增强目标，可通过替换或扩展 asr-service 中的 ASR Engine 实现。*

# 🚫 核心红线要求（CRITICAL RULES：绝对禁止 Mock）
本项目为生产级架构，**绝对禁止任何形式的 Mock 数据、假流程或降级处理**。如果你无法实现真实逻辑，必须让程序报错，绝不允许写假代码糊弄。
1. `asr-service` 必须真实加载 FunASR 模型，处理真实音频字节流。**实现 FunASR 流式推理时，必须按照 FunASR 官方 streaming websocket/server 示例或 AutoModel streaming 接口编写；绝不要臆造不存在的参数。** 若接口不兼容，必须在代码注释中说明需要调整的位置。
2. `doctor-web` 必须真实采集麦克风音频，重写 PCM 并通过 WebSocket 发送真实二进制流。
3. `business-backend` 必须真实代理 WebSocket 音频流和返回结果。
4. `agent-service` 必须真实使用 Agno 框架调用 LLM。优先读取 `OPENAI_BASE_URL`（如果不存在则读取 `OPENAI_API_BASE`）、`OPENAI_API_KEY` 和 `MODEL_ID`。
5. **强制结构化输出**：Agent 内部必须使用 Agno Agent + Pydantic `output_schema` 实现结构化输出。HTTP 服务层请使用 FastAPI 自定义业务路由，确保业务后端可以直接调用 REST API，避免过度设计。
6. **禁止硬编码**：不允许返回固定文本、不允许使用 `setTimeout`/`asyncio.sleep` 模拟识别结果、不允许伪造 partial/final 状态。
7. **容灾策略**：后端服务在关键环境变量缺失时必须在启动时崩溃（Crash）或返回明确 HTTP 500 错误；前端关键配置缺失时必须在页面显示明确错误，不允许静默使用假地址。
8. **依赖管理**：所有 Python 服务必须使用 `uv` 进行环境和依赖管理。**必须生成 `pyproject.toml` 和 `uv.lock`，绝对禁止生成和使用 `requirements.txt` 和 `pip`**。

# 系统整体架构
系统由 4 个独立的微服务/模块组成，你需要按模块为我分步编写代码：

1. `doctor-web`: 医生端 PC 网页前端（Vue 3）。
2. `business-backend`: 主业务网关系统（Python FastAPI）。
3. `asr-service`: 实时语音识别公共服务。
4. `agent-service`: 包含两个 Agno (Phidata) 智能体的认知服务。

---

## 模块详细技术规范与编码要求

### 模块 1：doctor-web (前端)
* **技术栈**: Vue 3 (Composition API) + Vite + TailwindCSS。
* **核心功能**:
  1. 麦克风采集: 使用 `getUserMedia` 获取音频流。
  2. 音频处理: 必须编写独立的 `AudioWorkletProcessor`，在浏览器端实时将音频流重采样为 **16kHz, 16-bit, 单声道 PCM** 格式。
  3. WebSocket 推流: 将切片好的 PCM chunk（建议 100-200ms）持续发送给后端。
  4. UI 展示: 实时区分渲染 `partial`（灰色/倾斜）和 `final`（黑色）文本，并展示最终生成的结构化病历和质控结果。

### 模块 2：business-backend (主业务后端/网关)
* **技术栈**: Python 3.10+ + FastAPI + Uvicorn + uv。
* **核心功能**:
  1. WebSocket 网关接受前端连接。
  2. **双向透传 (Proxy)**: 实时透传前端二进制流给内网 `asr-service`，并将 JSON 结果原样推回前端。
  3. **业务编排 API**: 提供 `/api/generate-record`，接收完整转写文本，依次调用 `agent-service` 组合结果返回。

### 模块 3：asr-service (实时语音识别服务)
* **技术栈**: Python 3.10+ + FastAPI + websockets + FunASR + uv。
* **核心模型**: `paraformer-zh-streaming` (ASR), `fsmn-vad` (VAD), `ct-punc` (标点恢复)。
* **编码要求**: 
  - 必须独立解耦。在应用启动时（Lifespan）真实加载模型。
  - 对外提供 WebSocket 接口接收 PCM 字节流，并实时返回 `{"type": "partial"/"final", "text": "..."}`。
  - 编写 `Dockerfile`。

### 模块 4：agent-service (认知智能体服务)
* **技术栈**: Python 3.10+ + FastAPI + Agno 框架 + Pydantic + uv。
* **核心要求**: 
  - 通过 `.env` 注入环境变量。使用 Agno 的 `OpenAILike` 引擎，通过 Pydantic 约束输出格式。
  
  **Agent 1: `medical-record-agent`**
  - **输入**: 完整 ASR 文本。
  - **Pydantic Schema**: 包含 `chief_complaint`, `present_illness`, `past_history`, `diagnosis`, `treatment_plan` (全为字符串)。

  **Agent 2: `medical-qc-agent`**
  - **输入**: Agent 1 输出的 JSON 数据。
  - **Pydantic Schema**: 包含 `is_passed` (布尔), `risk_level` (低中高枚举), `warnings` (字符串列表), `suggestions` (字符串列表)。

---

# 执行指令 (核心原则：按阶段交付)

为了保证项目的渐进式交付并降低技术风险，请务必**严格按以下阶段顺序**为我生成代码。每完成一个阶段的代码输出，请停下来等待我的指令（例如回复“继续”）：

**第一阶段：跑通实时语音识别闭环（ASR MVP）**
1. **生成全局目录结构**。
2. **编写 `asr-service`**：生成 `pyproject.toml`（绝对不要 `requirements.txt`），配置 fastapi, funasr, websockets 等依赖。编写 `server.py` 实现**真实的模型加载与 WebSocket 推理**。
3. **编写 `doctor-web` (MVP版)**：配置前端并编写 `AudioWorklet` 重采样脚本和 Vue 组件。此时前端先**直连** `asr-service`，验证真实的麦克风 PCM 推流。

**第二阶段：接入业务网关层**
4. **编写 `business-backend`**：使用 `uv` 生成 `pyproject.toml`。实现 WebSocket 双向代理透传路由，然后修改第一阶段的前端代码连接到此网关。

**第三阶段：实现 AI 认知与质控**
5. **编写 `agent-service`**：生成 `pyproject.toml`，基于 Agno 和 Pydantic 编写两个 Agent 服务，确保读取真实环境变量调用 `OpenAILike` 模型。
6. **全链路整合**：在业务网关中打通 `/api/generate-record`，在前端补充触发按钮与病历渲染 UI。

我已准备好。请开始执行【第一阶段】。

第一阶段只生成 `asr-service` 和 `doctor-web` 的完整代码；`business-backend` 和 `agent-service` 仅在目录结构中预留，不能提前实现。