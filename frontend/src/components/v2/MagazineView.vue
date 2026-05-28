<script setup lang="ts">
// Magazine view (roadmap C.4 / audit #2 + #7).
//
// Renders the operator's pen magazine as a grid of slots — each
// slot showing its colour, install state, and per-slot calibration
// hint. Pure / props-driven; the editing surface is intentionally
// left to the existing profile editor today, but the component
// exposes events ('toggle-install', 'edit-slot') so a future
// wrapper can wire them up.

import { computed } from 'vue'
import type { PenSlot } from '../../api/client'

const props = defineProps<{
  slots: readonly PenSlot[]
  capacity?: number
  simulationSlot?: number | null
}>()

const emit = defineEmits<{
  (e: 'toggle-install', slotIndex: number): void
  (e: 'edit-slot', slotIndex: number): void
}>()

// Pad the visible grid to ``capacity`` so an empty 6-slot magazine
// still renders six "empty" placeholders. The audit's "vue magazine"
// brief asks for physical accuracy: missing pens are first-class.
const visible = computed(() => {
  const known = new Map(props.slots.map((s) => [s.index, s]))
  const cap = Math.max(props.capacity ?? props.slots.length, props.slots.length, 1)
  const rows: ({ slot: PenSlot } | { empty: number })[] = []
  for (let i = 0; i < cap; i++) {
    const s = known.get(i)
    if (s) rows.push({ slot: s })
    else rows.push({ empty: i })
  }
  return rows
})
</script>

<template>
  <section class="magazine" data-test="magazine-view" :aria-label="'Pen magazine'">
    <header>
      <h3>Magasin</h3>
      <span class="count">{{ slots.length }} / {{ capacity ?? slots.length }} slots</span>
    </header>
    <ul class="grid">
      <li
        v-for="(entry, i) in visible"
        :key="i"
        class="slot-cell"
        :class="{
          empty: 'empty' in entry,
          installed: 'slot' in entry && entry.slot.installed,
          simulating: 'slot' in entry && entry.slot.index === simulationSlot,
        }"
        :data-test="`slot-${i}`"
      >
        <template v-if="'slot' in entry">
          <button
            type="button"
            class="install-toggle"
            :aria-pressed="entry.slot.installed"
            :title="entry.slot.installed ? 'Désinstaller' : 'Installer'"
            :data-test="`slot-${i}-toggle`"
            @click="emit('toggle-install', entry.slot.index)"
          >
            <span class="dot" :style="{ background: entry.slot.color }" />
          </button>
          <div class="meta">
            <span class="idx">#{{ entry.slot.index }}</span>
            <span class="name">{{ entry.slot.name || entry.slot.color }}</span>
            <span v-if="entry.slot.position !== null" class="calib">
              calibré ({{ entry.slot.position.x.toFixed(1) }},
              {{ entry.slot.position.y.toFixed(1) }})
            </span>
            <span v-else class="calib uncalib">non calibré</span>
          </div>
          <button
            type="button"
            class="edit"
            :data-test="`slot-${i}-edit`"
            @click="emit('edit-slot', entry.slot.index)"
          >
            ✎
          </button>
        </template>
        <template v-else>
          <span class="dot empty-dot" />
          <span class="idx">#{{ entry.empty }}</span>
          <span class="name">vide</span>
        </template>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.magazine {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  font-family: system-ui, sans-serif;
  font-size: 0.875rem;
  background: white;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.5rem;
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.count {
  color: #666;
  font-size: 0.85rem;
}
.grid {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.5rem;
}
.slot-cell {
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  padding: 0.5rem;
  display: grid;
  grid-template-columns: 2rem 1fr 1.5rem;
  gap: 0.5rem;
  align-items: center;
  background: #fafafa;
}
.slot-cell.empty {
  opacity: 0.55;
}
.slot-cell.installed {
  background: white;
}
.slot-cell.simulating {
  outline: 2px solid #1f6feb;
  outline-offset: -2px;
}
.install-toggle {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
}
.dot {
  display: inline-block;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.2);
}
.empty-dot {
  background: #e0e0e0;
  border-style: dashed;
}
.meta {
  display: flex;
  flex-direction: column;
  font-size: 0.8rem;
}
.idx {
  font-weight: 600;
  font-family: ui-monospace, Menlo, monospace;
}
.calib {
  font-size: 0.7rem;
  color: #2e7d32;
}
.uncalib {
  color: #b26a00;
}
.edit {
  border: 1px solid #d0d0d0;
  background: white;
  cursor: pointer;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 0.8rem;
}
</style>
