<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

// Compact file-action menu shown next to the file name in the modal
// header. Replaces the bulky "Source" card body that used to occupy
// the top of the Source tab: the modal opens with a file already
// selected 100% of the time (the operator clicked "Edit" on a file in
// the library), so the picker was redundant. Change file and Clear
// remain reachable but stop competing with the actual conversion
// settings for screen real-estate.

defineProps<{
  hasFile: boolean
}>()

const emit = defineEmits<{
  (e: 'change'): void
  (e: 'clear'): void
}>()

const { t } = useI18n()

const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

function toggle(): void {
  open.value = !open.value
}

function onChange(): void {
  open.value = false
  emit('change')
}
function onClear(): void {
  open.value = false
  emit('clear')
}

function onDocClick(event: MouseEvent): void {
  if (!open.value) return
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => window.addEventListener('mousedown', onDocClick))
onBeforeUnmount(() => window.removeEventListener('mousedown', onDocClick))
</script>

<template>
  <div ref="menuRef" class="relative">
    <button
      type="button"
      class="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
      :title="t('editModal.fileActions')"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="toggle"
    >
      ⋯
    </button>
    <div
      v-if="open"
      role="menu"
      class="absolute right-0 z-20 mt-1 w-48 overflow-hidden rounded border border-slate-700 bg-slate-800 shadow-xl"
    >
      <button
        type="button"
        role="menuitem"
        class="block w-full px-3 py-1.5 text-left text-xs text-slate-200 hover:bg-slate-700"
        @click="onChange"
      >
        {{ t('upload.changeFile') }}
      </button>
      <button
        v-if="hasFile"
        type="button"
        role="menuitem"
        class="block w-full px-3 py-1.5 text-left text-xs text-rose-300 hover:bg-rose-950/60"
        @click="onClear"
      >
        ✕ {{ t('upload.clear') }}
      </button>
    </div>
  </div>
</template>
