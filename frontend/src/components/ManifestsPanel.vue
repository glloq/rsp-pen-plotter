<script setup lang="ts">
// Manifests diagnostics panel (roadmap Block D wire).
//
// Renders the backend manifest envelopes — version, generated_at,
// deprecations, feature_flags — so the operator can verify which
// versions of the contract their UI is talking to. This is the
// observability counterpart to the ManifestFallbackBanner: the
// banner signals "we lost the backend", the panel signals "here's
// exactly what the backend claims".

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getManifestDomain,
  listManifestDomains,
  type ManifestEnvelope,
} from '../api/client'
import { errorDetail } from '../api/error'

const { t } = useI18n()
const domains = ref<string[]>([])
const envelopes = ref<Record<string, ManifestEnvelope<Record<string, unknown>>>>({})
const loading = ref(false)
const error = ref<string | null>(null)

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const list = await listManifestDomains()
    domains.value = list
    const fetched: Record<string, ManifestEnvelope<Record<string, unknown>>> = {}
    for (const domain of list) {
      try {
        fetched[domain] = await getManifestDomain(domain)
      } catch {
        // Skip individual domain failures; the others may still load.
      }
    }
    envelopes.value = fetched
  } catch (err) {
    error.value = errorDetail(err, t('manifests.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section class="space-y-4 text-sm text-slate-200" data-test="manifests-panel">
    <header class="flex items-center justify-between">
      <h3 class="text-base font-semibold">{{ t('manifests.title') }}</h3>
      <button
        type="button"
        class="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        :disabled="loading"
        data-test="manifests-refresh"
        @click="refresh"
      >
        {{ t('manifests.refresh') }}
      </button>
    </header>

    <p class="text-xs text-slate-400">{{ t('manifests.intro') }}</p>
    <p v-if="error" class="text-xs text-red-400">{{ error }}</p>

    <article
      v-for="domain in domains"
      :key="domain"
      class="rounded border border-slate-700 bg-slate-800/40 p-3 space-y-1.5"
      :data-test="`manifest-card-${domain}`"
    >
      <header class="flex items-baseline justify-between">
        <h4 class="font-semibold text-slate-100">{{ domain }}</h4>
        <span
          v-if="envelopes[domain]"
          class="text-[10px] uppercase tracking-wider text-slate-400"
        >
          v{{ envelopes[domain].meta.manifest_version }} ·
          schema {{ envelopes[domain].meta.schema_semver }}
        </span>
      </header>
      <p v-if="envelopes[domain]" class="text-[11px] text-slate-500">
        {{ t('manifests.generatedAt') }}:
        <span class="font-mono">{{ envelopes[domain].meta.generated_at }}</span>
      </p>
      <p
        v-if="envelopes[domain] && envelopes[domain].entries.length"
        class="text-[11px] text-slate-400"
      >
        {{ t('manifests.entriesCount', { count: envelopes[domain].entries.length }) }}
      </p>
      <div
        v-if="envelopes[domain] && Object.keys(envelopes[domain].meta.feature_flags).length"
        class="space-x-1"
      >
        <span
          v-for="(value, flag) in envelopes[domain].meta.feature_flags"
          :key="flag"
          class="inline-block rounded bg-slate-700 px-1.5 py-0.5 text-[10px]"
          :class="value ? 'text-emerald-300' : 'text-slate-400'"
        >
          {{ flag }}: {{ value ? 'on' : 'off' }}
        </span>
      </div>
      <ul
        v-if="envelopes[domain] && envelopes[domain].meta.deprecations.length"
        class="list-disc pl-5 text-[11px] text-amber-300"
      >
        <li v-for="d in envelopes[domain].meta.deprecations" :key="d.feature">
          {{ d.feature }} — deprecated {{ d.deprecated_since }}, removed after
          {{ d.remove_after }}
        </li>
      </ul>
    </article>
  </section>
</template>
