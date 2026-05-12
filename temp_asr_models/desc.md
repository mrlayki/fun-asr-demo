# 2-pass双路混合解码架构

### 0. 前端音频捕获与流式切片 (Frontend Audio Capture & Streaming)

- **物理采样**：浏览器基于 `AudioContext` 或 `AudioWorklet` 获取麦克风硬件输入，通常重采样为标准的 **16kHz、16-bit、单声道 (Mono) 的原始 PCM (Pulse Code Modulation) 裸流**。
- **前端降噪**：部分场景下依赖浏览器底层的 WebRTC 模块进行回声消除 (AEC)、自动增益控制 (AGC) 和静音抑制/降噪 (NS)。
- **流式封包**：将连续的 PCM 数据流按照固定帧长（如 100ms/包）进行 Chunking（切片），并通过 WebSocket 持久化长连接，以二进制流的形式高频推送到后端网关。

### 1. VAD 模型：基于声学特征的端点检测 (FSMN-VAD)

- **特征提取**：接收到 PCM 流后，后端首先提取音频的 Fbank (Filterbank) 或 MFCC 声学特征。
- **帧级别分类**：FSMN (Feedforward Sequential Memory Network) 模型对特征进行逐帧扫描，进行二分类预测（Speech vs. Non-speech），以此过滤掉纯背景底噪和无意义的环境音。
- **状态机调度 (Endpoint Detection)**：通过设定 `max_end_silence_time`（如 500ms）和 `max_start_silence_time` 阈值，计算连续非语音帧的长度。一旦超过阈值，VAD 触发截断逻辑（Endpointing），向下游抛出 `is_speaking: False` 的事件，强行将连续流切分为独立的 Utterance（语音段）张量。

### 2. Online 模型：受限上下文的流式解码 (Streaming ASR Engine)

- **机制**：在 VAD 判定为激活状态期间，音频切片被连续喂给在线模型（如 Paraformer-online）。
- **Chunk-based 解码**：采用带有限前向看（Lookahead）机制的网络结构。模型仅依赖历史 Chunk 和少量未来 Chunk 的声学上下文进行推理。
- **输出特性**：由于缺乏全局感受野，其输出为 Intermediate Hypothesis（中间假设态/ Partial Result）。它具有极低的计算延迟（Latency），用于前端快速渲染不断自我修正的临时文本，但存在同音词错误且无标点输出。

### 3. Offline 模型：全局注意力的非自回归解码 (Full-Context ASR)

- **触发机制**：由 VAD 的 Endpoint 事件触发。获取一整段完整的 Utterance 音频张量。
- **全局特征融合**：模型（如 Paraformer-Nano / Qwen-ASR）利用 Transformer/Conformer 架构中的全局自注意力机制（Global Self-Attention），在空间维度上完整映射整句话的声学特征与语义依赖。
- **NAR 输出**：采用非自回归（Non-Autoregressive）或大模型自回归解码，对整句序列进行打分并输出最优路径（1-best）。其牺牲了几百毫秒的结算延迟，换取极高的 CER（字符错误率）下降，提供最终的高置信度文本。

### 4. SV 模型：声纹特征提取与在线聚类 (Speaker Verification & Diarization)

- **Embedding 提取**：在 Offline 阶段同步触发。CampPlus 等模型将整段 Utterance 的声学特征映射到一个固定维度的高维空间，输出一个稠密向量（如 192 维的 d-vector 或 x-vector）。
- **L2 归一化**：对特征向量进行 L2 Normalization，消除音频响度带来的向量模长干扰。
- **动态聚类计算**：将新向量与内存中维护的“当前会话说话人矩阵（Session Speaker Centroids）”进行点乘，计算余弦相似度（Cosine Similarity）。
- **EMA 中心点更新**：若最大相似度大于设定的 Threshold，则归类为已知说话人，并基于指数移动平均（EMA, 例如 `alpha = 0.8`）动态平滑更新该说话人的中心向量簇，以抵抗长时间对话带来的音色漂移。若均小于阈值，则初始化一个新的特征簇。

### 5. Punc 模型：基于序列标注的标点恢复 (Punctuation Restoration)

- **NLP 下游任务**：接收 Offline ASR 输出的无标点纯文本序列（Token Sequence）。
- **Token Classification**：通常基于 BERT 或 Transformer 编码器。模型将标点恢复建模为一个标准的序列标注任务（Sequence Labeling），预测每个 Token 后方插入逗号、句号、问号或空标签（None）的概率分布（Softmax）。
- **结果聚合**：将预测的高概率标点符号与原始文本重新拼接，生成具备完整语法结构的最终 JSON 响应，推送至前端业务层。*(注：若使用自带语感的大模型如 Qwen3 作为 Offline，此独立组件通常被旁路/省去)*。