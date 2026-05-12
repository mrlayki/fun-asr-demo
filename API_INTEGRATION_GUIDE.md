# FunASR 实时语音转写 WebSocket 对接文档

本文档适用于业务端（前端、客户端）开发人员对接本地/服务端的 FunASR 实时语音转写（2pass 模式）服务。

## 1. 接口基础信息

- **通信协议**：WebSocket (`ws://` 或 `wss://`)
- **默认地址**：`ws://<服务端IP>:10095`
- **音频格式要求**：
  - 采样率 (Sample Rate)：`16000 Hz`
  - 位深 (Bit Depth)：`16 bit` (Int16 / PCM)
  - 声道 (Channels)：`1` (单声道)
  - 传输格式：`Binary ArrayBuffer`

---

## 2. 通信时序与报文定义

对接采用 **全双工通信**，分为三个核心阶段：初始化、音频流传输、结束会话。

### 阶段一：建立连接与初始化 (文本消息)

建立 WebSocket 连接后，客户端必须**首发**一条 JSON 格式的配置消息。如果不发送此消息直接发送音频，服务端会丢弃音频数据。

**发送示例 (JSON String):**
```json
{
  "mode": "2pass",
  "chunk_size": [5, 10, 5],
  "chunk_interval": 10,
  "audio_fs": 16000,
  "wav_name": "microphone",
  "is_speaking": true,
  "hotwords": "阿里 达摩院" 
}
```

**关键字段说明**：
- `mode`: `"2pass"` 表示启用“实时流式输出(online)”+“断句离线精纠错(offline)”的双引擎模式。
- `audio_fs`: 采样率，强烈建议固定为 `16000`。
- `is_speaking`: `true` 告诉服务端接下来会源源不断地发送音频。
- `hotwords`: [可选] 热词配置，用于提升专有名词识别率。支持以下两种格式：
  - **空格分隔的字符串** (默认权重)：如 `"阿里 达摩院"`
  - **带权重的 JSON 字典** (权重一般在 1~100 之间，建议 20 左右)：如 `{"阿里": 20, "达摩院": 50}`

---

### 阶段二：流式音频传输 (二进制消息)

发送完初始化 JSON 后，客户端开始高频地将音频的 PCM 二进制数据块直接发送给服务端。

**发送要求**：
- **格式**：原生 `Int16Array` 转换成的 `ArrayBuffer`。
- **不带包头**：纯粹的 PCM 数据，**不要**带 WAV header（无 RIFF 头）。
- **帧率**：建议每隔几百毫秒（例如每收集到 4096 帧）发送一次。

#### 此时服务端的响应 (实时返回 JSON)

在传输音频期间，服务端会不断返回 JSON 结果，分为两种类型：**Partial（中间结果）** 和 **Final（断句最终结果）**。

**中间结果示例（语速快时频发）：**
```json
{
  "mode": "2pass-online",
  "text": "今天天气",
  "wav_name": "microphone",
  "is_final": false
}
```
*前端处理逻辑*：通常用灰色字体显示 `text` 内容，代表 AI 还在听、可能会自我纠正。

**断句最终结果示例（VAD 检测到说话停顿）：**
```json
{
  "mode": "2pass-offline",
  "text": "今天天气真不错。",
  "wav_name": "microphone",
  "spk_name": "unknown",
  "spk_score": 0.0,
  "is_final": true,
  "timestamp": [[0, 200], [200, 400], ...],
  "punc_array": [...]
}
```
*前端处理逻辑*：此时这句文字已经完全确认（且加上了标点符号），用黑色/主色字体固定显示，并清空“中间结果”区域。

---

### 阶段三：结束会话 (文本消息)

当用户点击“停止录音”时，客户端需向服务端发送一个结束信号，告知当前语音结束，服务端会立刻强制结算最后一段话的 Final 结果。

**发送示例 (JSON String):**
```json
{
  "is_speaking": false
}
```
发送完成后，客户端可主动关闭 WebSocket (`ws.close()`)。

---

## 3. 前端浏览器 (Web JS) 接入参考代码

如果你是在浏览器环境接入，获取 16000Hz 16bit PCM 音频的参考逻辑如下：

```javascript
// 注意：必须传入 "binary" 子协议，否则服务端会拒绝连接报 NegotiationError
let websocket = new WebSocket("ws://127.0.0.1:10095", "binary");
websocket.binaryType = 'arraybuffer'; // 必须设置！

websocket.onopen = () => {
    // 1. 建立连接后立刻发送配置
    websocket.send(JSON.stringify({
        mode: "2pass",
        chunk_size: [5, 10, 5],
        chunk_interval: 10,
        audio_fs: 16000,
        wav_name: "web_microphone",
        is_speaking: true,
        hotwords: "需要增强识别 的 专有名词" // [可选] 可传字符串或 JSON 字典
    }));
};

websocket.onmessage = (event) => {
    const res = JSON.parse(event.data);

    // ⚠️ 重要：离线模型(SenseVoiceSmall)会在文本前附加特殊标记，必须清洗！
    // 示例原始输出: "<|zh|><|NEUTRAL|><|Speech|><|woitn|>你好世界"
    // 清洗后: "你好世界"
    if (res.text) {
        res.text = res.text.replace(/<\|[^|]*\|>/g, '').trim();
    }

    if (res.is_final) {
        console.log("✅ 最终句断定：", res.text);
    } else {
        console.log("⏳ 实时过程：", res.text);
    }
};

// 2. 采集麦克风并降采样发送
navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
    // 强制使用 16000 采样率
    const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    
    // 创建处理器节点 (bufferSize: 4096)
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    processor.onaudioprocess = (e) => {
        if (websocket.readyState !== WebSocket.OPEN) return;
        
        const float32Data = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(float32Data.length);
        
        // Float32 转 Int16 PCM
        for (let i = 0; i < float32Data.length; i++) {
            let s = Math.max(-1, Math.min(1, float32Data[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        // 发送二进制 ArrayBuffer
        websocket.send(pcmData.buffer);
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
});

// 3. 停止录音
function stopRecording() {
    websocket.send(JSON.stringify({ is_speaking: false }));
    // 断开 audio 节点，关闭连接...
}
```
