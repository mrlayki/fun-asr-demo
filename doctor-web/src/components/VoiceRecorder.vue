<script setup>
/**
 * VoiceRecorder.vue — Core recording + transcription component
 *
 * Pipeline: Microphone → AudioWorklet (resample to 16kHz PCM) → WebSocket → ASR
 * Display:  partial (gray italic) / final (black) text segments
 */
import { ref, computed, onUnmounted, nextTick } from 'vue'

// ── Configuration (fail-fast: no silent fallback) ──
const ASR_WS_URL = import.meta.env.VITE_ASR_WS_URL
const configError = ref(
  ASR_WS_URL ? '' : '错误：未配置 VITE_ASR_WS_URL 环境变量。请在 .env 文件中设置 ASR WebSocket 地址。'
)

// ── State ──
const isRecording = ref(false)
const isConnecting = ref(false)
const connectionStatus = ref('disconnected') // 'disconnected' | 'connecting' | 'connected' | 'error'
const errorMessage = ref('')
const elapsedSeconds = ref(0)
const finalTexts = ref([])      // Array of finalized text segments
const partialText = ref('')     // Current partial recognition result

// ── Refs for cleanup ──
let audioContext = null
let mediaStream = null
let workletNode = null
let websocket = null
let timerInterval = null
const transcriptContainer = ref(null)

// ── Computed ──
const formattedTime = computed(() => {
  const mins = Math.floor(elapsedSeconds.value / 60).toString().padStart(2, '0')
  const secs = (elapsedSeconds.value % 60).toString().padStart(2, '0')
  return `${mins}:${secs}`
})

const fullTranscript = computed(() => {
  return finalTexts.value.join('')
})

const hasContent = computed(() => {
  return finalTexts.value.length > 0 || partialText.value.length > 0
})

// ── Auto-scroll transcript area ──
function scrollToBottom() {
  nextTick(() => {
    if (transcriptContainer.value) {
      transcriptContainer.value.scrollTop = transcriptContainer.value.scrollHeight
    }
  })
}

// ── WebSocket Management ──
function connectWebSocket() {
  return new Promise((resolve, reject) => {
    connectionStatus.value = 'connecting'
    isConnecting.value = true

    websocket = new WebSocket(ASR_WS_URL)

    websocket.onopen = () => {
      connectionStatus.value = 'connected'
      isConnecting.value = false
      errorMessage.value = ''
      resolve()
    }

    websocket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        if (msg.type === 'partial') {
          partialText.value = msg.text || ''
          scrollToBottom()
        } else if (msg.type === 'final') {
          finalTexts.value.push(msg.text || '')
          partialText.value = ''
          scrollToBottom()
        } else if (msg.type === 'error') {
          errorMessage.value = `ASR 服务错误: ${msg.text}`
        }
      } catch (e) {
        console.error('Failed to parse ASR message:', e)
      }
    }

    websocket.onerror = (err) => {
      console.error('WebSocket error:', err)
      connectionStatus.value = 'error'
      isConnecting.value = false
      errorMessage.value = '无法连接到 ASR 服务，请确认 asr-service 已启动。'
      reject(new Error('WebSocket connection failed'))
    }

    websocket.onclose = () => {
      connectionStatus.value = 'disconnected'
      isConnecting.value = false
    }
  })
}

// ── Audio Pipeline Setup ──
async function startRecording() {
  if (configError.value) return
  errorMessage.value = ''

  try {
    // 1. Connect WebSocket first
    await connectWebSocket()

    // 2. Get microphone access
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,  // Hint only — browser may ignore
        echoCancellation: true,
        noiseSuppression: true,
      }
    })

    // 3. Create AudioContext
    audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(mediaStream)

    // 4. Load AudioWorklet processor
    await audioContext.audioWorklet.addModule('/audio-processor.js')
    workletNode = new AudioWorkletNode(audioContext, 'pcm-resampler-processor')

    // 5. Handle PCM chunks from worklet → send via WebSocket
    workletNode.port.onmessage = (event) => {
      if (websocket && websocket.readyState === WebSocket.OPEN) {
        // event.data is an ArrayBuffer containing Int16 PCM samples
        websocket.send(event.data)
      }
    }

    // 6. Connect audio graph: mic → worklet
    source.connect(workletNode)
    // Don't connect to destination (we don't want playback)

    // 7. Start timer
    elapsedSeconds.value = 0
    timerInterval = setInterval(() => {
      elapsedSeconds.value++
    }, 1000)

    isRecording.value = true
  } catch (err) {
    console.error('Failed to start recording:', err)
    if (err.name === 'NotAllowedError') {
      errorMessage.value = '麦克风权限被拒绝，请在浏览器设置中允许麦克风访问。'
    } else if (err.name === 'NotFoundError') {
      errorMessage.value = '未检测到麦克风设备。'
    } else {
      errorMessage.value = `录音启动失败: ${err.message}`
    }
    cleanup()
  }
}

async function stopRecording() {
  // Send STOP signal to ASR service before closing
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    try {
      // Tell worklet to flush remaining samples
      if (workletNode) {
        workletNode.port.postMessage('stop')
        // Small delay to let the last chunk go through
        await new Promise(resolve => setTimeout(resolve, 200))
      }
      websocket.send('STOP')
      // Wait a bit for final results
      await new Promise(resolve => setTimeout(resolve, 500))
    } catch (e) {
      console.warn('Error sending STOP:', e)
    }
  }

  cleanup()
  isRecording.value = false
}

function cleanup() {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
  if (workletNode) {
    workletNode.disconnect()
    workletNode = null
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop())
    mediaStream = null
  }
  if (audioContext && audioContext.state !== 'closed') {
    audioContext.close()
    audioContext = null
  }
  if (websocket) {
    if (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING) {
      websocket.close()
    }
    websocket = null
  }
}

function clearTranscript() {
  finalTexts.value = []
  partialText.value = ''
}

onUnmounted(() => {
  cleanup()
})
</script>

<template>
  <!-- Config Error Banner -->
  <div v-if="configError"
    class="rounded-2xl bg-red-50 border border-red-200 p-6 text-center">
    <div class="w-12 h-12 mx-auto mb-3 rounded-full bg-red-100 flex items-center justify-center">
      <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
      </svg>
    </div>
    <p class="text-red-700 font-medium">{{ configError }}</p>
  </div>

  <!-- Main Interface -->
  <div v-else class="space-y-6">
    <!-- Connection Status Badge -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="inline-block w-2.5 h-2.5 rounded-full transition-colors duration-300"
          :class="{
            'bg-slate-300': connectionStatus === 'disconnected',
            'bg-amber-400 animate-pulse': connectionStatus === 'connecting',
            'bg-emerald-500': connectionStatus === 'connected',
            'bg-red-500': connectionStatus === 'error',
          }"
        ></span>
        <span class="text-sm text-slate-500">
          {{ connectionStatus === 'disconnected' ? '未连接' :
             connectionStatus === 'connecting' ? '连接中...' :
             connectionStatus === 'connected' ? 'ASR 已连接' :
             '连接失败' }}
        </span>
      </div>
      <button v-if="hasContent && !isRecording"
        @click="clearTranscript"
        class="text-sm text-slate-400 hover:text-slate-600 transition-colors">
        清空记录
      </button>
    </div>

    <!-- Error Banner -->
    <div v-if="errorMessage"
      class="rounded-xl bg-red-50 border border-red-100 px-4 py-3 flex items-start gap-3">
      <svg class="w-5 h-5 text-red-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p class="text-sm text-red-600">{{ errorMessage }}</p>
    </div>

    <!-- Transcription Area -->
    <div class="glass-card rounded-2xl shadow-lg shadow-blue-100/50 overflow-hidden">
      <!-- Section Header -->
      <div class="px-6 py-4 bg-gradient-to-r from-primary-600 to-medical flex items-center gap-3">
        <svg class="w-5 h-5 text-white/80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <h2 class="text-white font-semibold tracking-wide">语音转写结果</h2>
        <span v-if="isRecording" class="ml-auto flex items-center gap-2 text-xs text-white/70">
          <span class="inline-block w-2 h-2 rounded-full bg-red-400 animate-pulse"></span>
          录音中
        </span>
      </div>

      <!-- Transcript Content -->
      <div ref="transcriptContainer"
        class="px-6 py-5 min-h-[280px] max-h-[480px] overflow-y-auto">
        <!-- Empty state -->
        <div v-if="!hasContent"
          class="flex flex-col items-center justify-center py-16 text-slate-300">
          <svg class="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          <p class="text-lg font-medium">点击下方按钮开始录音</p>
          <p class="text-sm mt-1">语音将被实时转写为文字</p>
        </div>

        <!-- Transcript text -->
        <div v-else class="leading-8 text-base">
          <!-- Final segments -->
          <span v-for="(text, idx) in finalTexts" :key="'f-' + idx"
            class="text-slate-800 font-normal">{{ text }}</span>
          <!-- Partial (current recognition) -->
          <span v-if="partialText"
            class="text-slate-400 italic partial-cursor">{{ partialText }}</span>
        </div>
      </div>

      <!-- Character count -->
      <div v-if="hasContent" class="px-6 pb-3 text-right">
        <span class="text-xs text-slate-300">{{ fullTranscript.length + partialText.length }} 字</span>
      </div>
    </div>

    <!-- Recording Controls -->
    <div class="glass-card rounded-2xl shadow-lg shadow-blue-100/50 px-6 py-5">
      <div class="flex items-center justify-center gap-8">
        <!-- Timer -->
        <div class="flex items-center gap-3 min-w-[120px]">
          <div v-if="isRecording" class="flex items-center gap-0.5 text-primary-500">
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
          </div>
          <span class="font-mono text-2xl font-light"
            :class="isRecording ? 'text-slate-700' : 'text-slate-300'">
            {{ formattedTime }}
          </span>
        </div>

        <!-- Record / Stop Button -->
        <button
          @click="isRecording ? stopRecording() : startRecording()"
          :disabled="isConnecting"
          class="group relative w-16 h-16 rounded-full transition-all duration-300 focus:outline-none focus:ring-4 focus:ring-offset-2"
          :class="isRecording
            ? 'bg-gradient-to-br from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 focus:ring-red-200 shadow-lg shadow-red-200'
            : 'bg-gradient-to-br from-primary-500 to-primary-600 hover:from-primary-600 hover:to-primary-700 focus:ring-primary-200 shadow-lg shadow-primary-200'
          "
          :title="isRecording ? '停止录音' : '开始录音'"
        >
          <!-- Recording: show stop icon -->
          <div v-if="isRecording"
            class="w-5 h-5 mx-auto rounded-sm bg-white transition-transform group-hover:scale-110">
          </div>
          <!-- Not recording: show mic icon -->
          <svg v-else class="w-7 h-7 mx-auto text-white transition-transform group-hover:scale-110"
            fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          <!-- Connecting spinner -->
          <div v-if="isConnecting"
            class="absolute inset-0 flex items-center justify-center">
            <div class="w-16 h-16 rounded-full border-4 border-transparent border-t-white animate-spin"></div>
          </div>
        </button>

        <!-- Status text -->
        <div class="min-w-[120px] text-sm text-center"
          :class="isRecording ? 'text-red-500' : 'text-slate-400'">
          {{ isConnecting ? '连接中...' : isRecording ? '点击停止录音' : '点击开始录音' }}
        </div>
      </div>
    </div>

    <!-- Tips -->
    <div class="rounded-xl bg-amber-50/60 border border-amber-100 px-5 py-4">
      <div class="flex gap-3">
        <svg class="w-5 h-5 text-amber-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="text-sm text-amber-700 space-y-1">
          <p class="font-medium">语音录入提示</p>
          <ul class="list-disc list-inside text-amber-600 space-y-0.5">
            <li>请对准麦克风清晰说话，描述患者主诉及现病史</li>
            <li>灰色斜体文字为实时识别中间结果，黑色文字为已确认结果</li>
            <li>录音结束后可查看完整转写文本</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
