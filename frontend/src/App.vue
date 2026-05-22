<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAlgorithms, getFonts, getHealth, type AlgorithmInfo } from './api/client'

const status = ref<string | null>(null)
const version = ref<string | null>(null)
const error = ref<string | null>(null)
const algorithms = ref<AlgorithmInfo[]>([])
const fonts = ref<string[]>([])

onMounted(async () => {
  try {
    const health = await getHealth()
    status.value = health.status
    version.value = health.version
    ;[algorithms.value, fonts.value] = await Promise.all([getAlgorithms(), getFonts()])
  } catch {
    error.value = 'API unreachable'
  }
})
</script>

<template>
  <main class="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center gap-6">
    <h1 class="text-4xl font-bold tracking-tight">OmniPlot</h1>
    <p class="text-slate-400">Universal pen plotter studio</p>

    <div
      v-if="error"
      class="rounded-md bg-red-900/60 border border-red-500 px-4 py-2 text-red-200"
    >
      {{ error }}
    </div>
    <div
      v-else-if="status"
      class="rounded-md bg-emerald-900/40 border border-emerald-500 px-4 py-2 text-emerald-200 font-mono"
    >
      API: {{ status }} (v{{ version }})
    </div>
    <div v-else class="text-slate-500 font-mono">Checking API…</div>

    <section v-if="algorithms.length" class="w-full max-w-md">
      <h2 class="text-sm uppercase tracking-wide text-slate-400 mb-2">Raster algorithms</h2>
      <ul class="space-y-2">
        <li
          v-for="algo in algorithms"
          :key="algo.name"
          class="rounded-md bg-slate-800 border border-slate-700 px-3 py-2"
        >
          <span class="font-mono text-emerald-300">{{ algo.name }}</span>
          <span class="text-slate-400"> — {{ algo.description }}</span>
        </li>
      </ul>
    </section>

    <section v-if="fonts.length" class="w-full max-w-md">
      <h2 class="text-sm uppercase tracking-wide text-slate-400 mb-2">
        Hershey fonts ({{ fonts.length }})
      </h2>
      <p class="text-slate-400 font-mono text-sm break-words">{{ fonts.join(', ') }}</p>
    </section>
  </main>
</template>
