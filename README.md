# 门诊诊间语音识别与病历生成系统

实时语音转写 + AI 结构化病历生成 + 医疗质控

## 系统架构

| 模块 | 说明 | 端口 |
|------|------|------|
| `doctor-web` | 医生端 PC 网页前端 (Vue 3) | 5173 |
| `business-backend` | 主业务网关 (FastAPI) | 8000 |
| `asr-service` | 实时语音识别服务 (FunASR) | 8001 |
| `agent-service` | AI 认知智能体服务 (Agno) | 8002 |

## 第一阶段：ASR MVP

```bash
# 1. 启动 ASR 服务
cd asr-service
uv sync
uv run python server.py

# 2. 启动前端
cd doctor-web
npm install
npm run dev
```

前端直连 `ws://localhost:8001/ws/asr`，验证麦克风 → PCM → FunASR 流式识别闭环。
