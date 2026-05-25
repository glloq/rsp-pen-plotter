<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFileManager, FILE_ACCEPT } from '../../composables/useFileManager'
import { validateUploadFile } from '../../api/uploadValidation'
import { useToastStore } from '../../stores/toasts'

// Edge-case overlay shown when the modal opens on a placement that
// has no attached file at all (rare: typically a placement created via
// drop-anywhere that never received bytes, or one whose library bytes
// were evicted without a fallback). The rest of the time, the modal
// opens with the file already attached, so this overlay never renders.
//
// Replaces the previous SourceTab + FileSourceCard dropzone path, which
// also let the operator change the active file once it WAS attached.
// That extra capability is gone: changing the file from inside the
// editor leaked too much state across edits; the user now goes back to
// FilesPane to pick a different placement instead.

const { t } = useI18n()
const fm = useFileManager(t)
const toasts = useToastStore()
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function openPicker(): void {
  fileInput.value?.click()
}

// Run client-side validation before staging the file in the editor.
// Without this, an oversize / wrong-type drop would silently feed the
// /preview scheduler and only surface as an error round-trips later —
// and the operator would lose any draft edits when the upload finally
// failed at the network layer.
function acceptFile(file: File | null): void {
  if (!file) return
  const issue = validateUploadFile(file)
  if (issue) {
    toasts.error(issue.message)
    return
  }
  fm.setFile(file)
}

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  acceptFile(target.files?.[0] ?? null)
  target.value = ''
}

function onDrop(event: DragEvent): void {
  dragOver.value = false
  acceptFile(event.dataTransfer?.files?.[0] ?? null)
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
  dragOver.value = true
}

function onDragLeave(): void {
  dragOver.value = false
}
</script>

<template>
  <div
    class="flex h-full items-center justify-center p-6"
    @dragenter.prevent="dragOver = true"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <input
      ref="fileInput"
      type="file"
      class="hidden"
      :accept="FILE_ACCEPT"
      @change="onFileChange"
    />
    <button
      type="button"
      class="flex w-full max-w-md flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition"
      :class="
        dragOver
          ? 'border-emerald-500 bg-emerald-950/40 text-emerald-100'
          : 'border-slate-700 bg-slate-900/40 text-slate-300 hover:border-slate-500'
      "
      @click="openPicker"
    >
      <span class="text-2xl" aria-hidden="true">📎</span>
      <span class="text-sm font-medium">{{ t('upload.dropHere') }}</span>
      <span class="text-[10px] text-slate-500">{{ t('upload.pick') }}</span>
    </button>
  </div>
</template>
