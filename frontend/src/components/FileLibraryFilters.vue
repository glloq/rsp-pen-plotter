<script setup lang="ts">
// Search + sort + folder filter bar for FilesPane (L10 #5 extract).
//
// Pure presentational: receives the current filter state as props
// and emits intent events the orchestrator forwards to the library
// store. The debounce for the search input lives in the parent
// (FilesPane) so each keystroke doesn't cross the component
// boundary, only the committed value does.

import { useI18n } from 'vue-i18n'
import type { LibrarySortKey } from '../api/client'

const { t } = useI18n()

defineProps<{
  searchInput: string
  sortKey: LibrarySortKey
  sortOrder: 'asc' | 'desc'
  folderFilter: string | null
  folders: string[]
}>()

const emit = defineEmits<{
  'update:searchInput': [value: string]
  searchInput: []
  sortChange: [event: Event]
  orderToggle: []
  folderChange: [event: Event]
}>()
</script>

<template>
  <div class="mt-2 space-y-1">
    <input
      :value="searchInput"
      type="search"
      :placeholder="t('files.search')"
      class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
      @input="
        (e) => {
          emit('update:searchInput', (e.target as HTMLInputElement).value)
          emit('searchInput')
        }
      "
    />
    <div class="flex items-center gap-1 text-[11px]">
      <select
        :value="sortKey"
        class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
        :title="t('files.sort')"
        @change="(e) => emit('sortChange', e)"
      >
        <option value="name">{{ t('files.sortName') }}</option>
        <option value="date">{{ t('files.sortDate') }}</option>
        <option value="type">{{ t('files.sortType') }}</option>
      </select>
      <button
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 hover:border-slate-500"
        :title="sortOrder === 'asc' ? t('files.sortAsc') : t('files.sortDesc')"
        @click="emit('orderToggle')"
      >
        {{ sortOrder === 'asc' ? '▲' : '▼' }}
      </button>
      <select
        :value="folderFilter === null ? '__all__' : folderFilter"
        class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
        :title="t('files.folder')"
        @change="(e) => emit('folderChange', e)"
      >
        <option value="__all__">{{ t('files.allFolders') }}</option>
        <option value="">{{ t('files.rootFolder') }}</option>
        <option v-for="f in folders" :key="f" :value="f">{{ f }}</option>
        <option value="__new__">{{ t('files.newFolder') }}</option>
      </select>
    </div>
  </div>
</template>
