# asr-service

实时语音识别公共服务，基于 FunASR。

## 模型

| 模型 | 用途 |
|------|------|
| `paraformer-zh-streaming` | 流式 ASR |
| `fsmn-vad` | 语音端点检测 |
| `ct-punc` | 标点恢复 |

## 启动

```bash
cp .env.example .env
uv sync
uv run python server.py
```

## WebSocket 协议

**地址**: `ws://localhost:8001/ws/asr`

**客户端 → 服务端**: 16kHz/16-bit/mono PCM binary frames

**客户端 → 服务端**: `"STOP"` 文本消息表示录音结束

**服务端 → 客户端**:
```json
{"type": "partial", "text": "正在识别的文本"}
{"type": "final", "text": "已确认的文本，带标点。"}
```
