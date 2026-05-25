<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import GenerateSection from './GenerateSection.vue'

const { t } = useI18n()
const store = useJobStore()

// Mirrors PlanRail's collapsible aside so the Simulator tab gets the
// same affordance for tucking the (dense) gcode-calculation panel out
// of the way on narrow screens.
const collapsed = ref(false)
</script>

<template>
  <aside
    v-if="store.layers.length"
    class="flex h-full min-h-0 flex-col border-l border-slate-700 bg-slate-900/40 transition-all"
    :class="collapsed ? 'w-8' : 'w-72'"
  >
    <header class="flex items-center justify-between border-b border-slate-700 px-2 py-1.5">
      <h3 v-if="!collapsed" class="text-[11px] uppercase tracking-wider text-slate-400">
        {{ t('simRail.title') }}
      </h3>
      <button
        type="button"
        class="ml-auto rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-300 hover:bg-slate-700"
        :aria-label="collapsed ? t('planRail.expand') : t('planRail.collapse')"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? '‹' : '›' }}
      </button>
    </header>

    <div v-if="!collapsed" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-2">
      <GenerateSection />
    </div>
  </aside>
</template>
