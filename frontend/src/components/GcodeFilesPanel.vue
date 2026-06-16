<script setup lang="ts">
// G-code file library for the Plotter tab.
//
// Lists the saved G-code programs (files) and lets the operator save the
// current program, pick one and print it on demand, rename or delete it.
// Saving never starts a print — printing is the explicit "Print selection"
// action, which enqueues the file as a run on the plotter.
//
// Per the agreed design the list shows the active print's state inline
// ("printing") with no cockpit here: pause / stop live in the header
// transport. The "is this file printing?" flag comes from the queue
// store (polled in the background), matched by ``gcode_file_id``.

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GcodeFileSummary, PrintRun } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useGcodeFilesStore } from '../stores/gcodeFiles'
import { useJobStore } from '../stores/job'
import { useQueueStore } from '../stores/queue'

const { t } = useI18n()
const job = useJobStore()
const files = useGcodeFilesStore()
const queue = useQueueStore()
const availableColors = useAvailableColorsStore()

const canSave = computed(() => Boolean(job.gcode))
const selectedId = ref<string | null>(null)

// Active runs keyed by the library file they were launched from, so a
// row can show its live state inline.
const runByFile = computed(() => {
  const map = new Map<string, PrintRun>()
  for (const run of queue.active) {
    if (run.gcode_file_id) map.set(run.gcode_file_id, run)
  }
  return map
})
function runFor(id: string): PrintRun | undefined {
  return runByFile.value.get(id)
}

function select(id: string): void {
  selectedId.value = selectedId.value === id ? null : id
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function logOdometerForCurrentJob(): void {
  for (const [hex, mm] of Object.entries(job.lengthMmByColor)) {
    void availableColors.addToOdometer(hex, mm)
  }
}

async function saveCurrent(): Promise<void> {
  if (!job.gcode) return
  const name = job.job?.source_file ?? 'gcode'
  const created = await files.save(name, job.selectedProfileName, job.gcode)
  if (created) {
    selectedId.value = created.id
    // The saved program is what the operator intends to draw, and the
    // file no longer carries per-colour lengths — advance the ink
    // odometer here, the one point the current job's data still matches.
    logOdometerForCurrentJob()
  }
}

async function printSelected(): Promise<void> {
  const id = selectedId.value
  if (!id) return
  const ok = await files.print(id)
  // Pull the queue immediately so the row flips to "printing" without
  // waiting for the next poll tick.
  if (ok) await queue.load()
}

// Inline rename.
const editingId = ref<string | null>(null)
const editName = ref('')
function startRename(file: GcodeFileSummary): void {
  editingId.value = file.id
  editName.value = file.name
}
async function commitRename(): Promise<void> {
  const id = editingId.value
  if (!id) return
  const name = editName.value.trim()
  editingId.value = null
  if (name) await files.rename(id, name)
}
function cancelRename(): void {
  editingId.value = null
}

async function removeFile(file: GcodeFileSummary): Promise<void> {
  const confirmed = await confirmAction({
    title: t('gcodeFiles.deleteTitle'),
    message: t('gcodeFiles.deleteMsg', { name: file.name }),
    confirmLabel: t('gcodeFiles.delete'),
    cancelLabel: t('gcodeFiles.cancel'),
    danger: true,
  })
  if (!confirmed) return
  if (selectedId.value === file.id) selectedId.value = null
  await files.remove(file.id)
}

const printDisabled = computed(
  () =>
    !selectedId.value ||
    files.isBusy(selectedId.value) ||
    Boolean(selectedId.value && runFor(selectedId.value)),
)

onMounted(() => {
  void files.refresh()
})
</script>

<template>
  <div class="space-y-2" data-test="gcode-files-panel">
    <!-- Save the current generated program into the library. -->
    <button
      v-if="canSave"
      type="button"
      class="w-full rounded bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
      :disabled="files.saving"
      data-test="gcode-save-current"
      @click="saveCurrent"
    >
      + {{ t('gcodeFiles.saveCurrent') }}
    </button>
    <p v-else class="px-1 text-xs text-slate-500">{{ t('gcodeFiles.generateFirst') }}</p>

    <!-- File list. -->
    <ul v-if="files.hasFiles" class="space-y-1" data-test="gcode-file-list">
      <li
        v-for="file in files.files"
        :key="file.id"
        class="rounded-lg border px-2.5 py-1.5"
        :class="
          selectedId === file.id
            ? 'border-emerald-600 bg-emerald-950/30'
            : 'border-slate-700 bg-slate-800/60'
        "
        :data-test="`gcode-file-${file.id}`"
      >
        <div class="flex items-center gap-2">
          <input
            v-if="editingId === file.id"
            v-model="editName"
            class="min-w-0 flex-1 rounded border border-slate-600 bg-slate-900 px-1.5 py-0.5 text-xs text-slate-100"
            :aria-label="t('gcodeFiles.rename')"
            @keyup.enter="commitRename"
            @keyup.esc="cancelRename"
            @blur="commitRename"
          />
          <button
            v-else
            type="button"
            class="min-w-0 flex-1 text-left"
            :data-test="`gcode-file-select-${file.id}`"
            @click="select(file.id)"
          >
            <span class="block truncate text-xs font-medium text-slate-200">{{ file.name }}</span>
            <span class="text-[10px] text-slate-500">
              {{ formatSize(file.size_bytes) }} · {{ file.line_count }} {{ t('gcode.lines') }}
            </span>
          </button>

          <!-- Live print state, inline (no controls — stop lives in the header). -->
          <span
            v-if="runFor(file.id)"
            class="shrink-0 rounded bg-emerald-900/60 px-1.5 py-0.5 text-[10px] font-medium text-emerald-200"
            :data-test="`gcode-file-state-${file.id}`"
          >
            {{ t(`queue.state.${runFor(file.id)!.state}`) }}
          </span>

          <template v-if="editingId !== file.id">
            <button
              type="button"
              class="shrink-0 rounded px-1 py-0.5 text-xs text-slate-400 hover:bg-slate-700 disabled:opacity-30"
              :disabled="files.isBusy(file.id) || Boolean(runFor(file.id))"
              :aria-label="t('gcodeFiles.rename')"
              :title="t('gcodeFiles.rename')"
              @click="startRename(file)"
            >
              ✎
            </button>
            <button
              type="button"
              class="shrink-0 rounded px-1 py-0.5 text-xs text-red-300 hover:bg-red-900/40 disabled:opacity-30"
              :disabled="files.isBusy(file.id) || Boolean(runFor(file.id))"
              :aria-label="t('gcodeFiles.delete')"
              :title="t('gcodeFiles.delete')"
              @click="removeFile(file)"
            >
              🗑
            </button>
          </template>
        </div>
      </li>
    </ul>
    <p
      v-else
      class="rounded-lg border border-dashed border-slate-700 px-3 py-3 text-center text-xs text-slate-500"
    >
      {{ t('gcodeFiles.empty') }}
    </p>

    <!-- Print the selected file on demand. -->
    <button
      v-if="files.hasFiles"
      type="button"
      class="w-full rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="printDisabled"
      data-test="gcode-print-selected"
      @click="printSelected"
    >
      ▶ {{ t('gcodeFiles.print') }}
    </button>

    <p v-if="files.error" class="text-[10px] text-red-400">{{ files.error }}</p>
  </div>
</template>
