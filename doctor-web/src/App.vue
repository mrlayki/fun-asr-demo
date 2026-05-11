<script setup>
import VoiceRecorder from './components/VoiceRecorder.vue'
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
    <!-- Header -->
    <header class="bg-gradient-to-r from-primary-700 via-primary-600 to-medical shadow-lg">
      <div class="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
          <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </div>
        <div>
          <h1 class="text-xl font-bold text-white tracking-tight">诊间语音识别</h1>
          <p class="text-sm text-blue-100/80">门诊病历实时转写系统</p>
        </div>
        <div class="ml-auto flex items-center gap-2 text-xs text-blue-100/60">
          <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          Phase 1 · ASR MVP
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main class="max-w-5xl mx-auto px-6 py-8">
      <VoiceRecorder />
    </main>

    <!-- Footer -->
    <footer class="text-center py-6 text-xs text-slate-400">
      门诊诊间语音识别与病历生成系统 v0.1
    </footer>
  </div>
</template>
