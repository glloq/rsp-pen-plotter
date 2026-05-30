<script setup lang="ts">
// Workspace rail (roadmap D.3 + Block C wire).
//
// Renders the v2 panels listed in the active workspace as a vertical
// stack to the right of the main canvas. Only mounts panels that map
// to a real v2 component — the v0.1 panel ids (source / style /
// preview / plot) are already covered by FilesPane + CanvasView and
// don't need a duplicate surface here.
//
// The rail auto-collapses when the active workspace contains nothing
// to render, so the Beginner workspace doesn't steal space.

import { computed, toRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../../stores/job'
import { usePlotterStore } from '../../stores/plotter'
import { useQueueStore } from '../../stores/queue'
import { useUiStore } from '../../stores/ui'
import { useWorkspacesStore, type PanelId } from '../../stores/workspaces'
import { normalizePens } from '../../composables/useProfileDraft'
import MachineStatusPill from '../MachineStatusPill.vue'
import LayerInspector from './LayerInspector.vue'
import MagazineView from './MagazineView.vue'
import PipelineInspector from './PipelineInspector.vue'
import RunActionsPanel from './RunActionsPanel.vue'
import RunTimeline from './RunTimeline.vue'

const emit = defineEmits<{
  (e: 'open-compare'): void
}>()

const { t } = useI18n()
const workspaces = useWorkspacesStore()
const job = useJobStore()
const queue = useQueueStore()
const plotter = usePlotterStore()
const ui = useUiStore()
const { status: plotterStatus } = storeToRefs(plotter)

const V2_PANELS: ReadonlySet<PanelId> = new Set<PanelId>([
  'layer_inspector',
  'pipeline_inspector',
  'queue',
  'magazine',
  'machine_telemetry',
  'compare',
])

const visiblePanels = computed(() => workspaces.active.panels.filter((id) => V2_PANELS.has(id)))

const activeRun = computed(() => queue.active[0] ?? null)
const activeLayers = computed(() => job.selectedPlacement?.layers ?? [])
const activeProfile = computed(() => job.selectedProfile)

async function onPause(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'pause')
}
async function onResume(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'resume')
}
async function onCancel(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'cancel')
}

// Magazine view edits route back to the canonical surfaces: toggling a
// slot's install state persists straight to the profile, while the ✎
// "edit slot" affordance opens the full magazine editor (Colours tab).
async function onToggleInstall(slotIndex: number): Promise<void> {
  const profile = activeProfile.value
  if (!profile) return
  const next = structuredClone(toRaw(profile))
  normalizePens(next)
  const pen = next.pens?.find((s) => s.index === slotIndex)
  if (!pen) return
  pen.installed = !pen.installed
  await job.saveProfile(next)
}

function onEditSlot(): void {
  ui.openPlotterSettings('colors')
}
</script>

<template>
  <aside
    v-if="visiblePanels.length"
    class="workspace-rail"
    data-test="workspace-rail"
    :aria-label="t('workspaces.railAria')"
  >
    <header class="workspace-rail__header">
      {{ workspaces.active.name }}
    </header>
    <div class="workspace-rail__body">
      <template v-for="id in visiblePanels" :key="id">
        <section v-if="id === 'layer_inspector'" :data-test="`rail-${id}`">
          <LayerInspector v-if="activeLayers.length" :layers="activeLayers" />
          <p v-else class="empty">{{ t('workspaces.empty.layers') }}</p>
        </section>
        <section v-else-if="id === 'pipeline_inspector'" :data-test="`rail-${id}`">
          <PipelineInspector :decision="null" />
        </section>
        <section v-else-if="id === 'magazine'" :data-test="`rail-${id}`">
          <MagazineView
            v-if="activeProfile"
            :slots="activeProfile.pens ?? []"
            :capacity="activeProfile.pen_slot_count"
            @toggle-install="onToggleInstall"
            @edit-slot="onEditSlot"
          />
          <p v-else class="empty">{{ t('workspaces.empty.magazine') }}</p>
        </section>
        <section v-else-if="id === 'queue'" :data-test="`rail-${id}`" class="space-y-2">
          <template v-if="activeRun">
            <RunTimeline :run="activeRun" />
            <RunActionsPanel
              :run="activeRun"
              @pause="onPause"
              @resume="onResume"
              @cancel="onCancel"
            />
          </template>
          <p v-else class="empty">{{ t('workspaces.empty.queue') }}</p>
        </section>
        <section v-else-if="id === 'machine_telemetry'" :data-test="`rail-${id}`" class="telemetry">
          <header class="telemetry__header">
            <strong>{{ t('workspaces.panel.machineTelemetry') }}</strong>
            <MachineStatusPill />
          </header>
          <ul class="telemetry__metrics">
            <li>
              <span>{{ t('workspaces.telemetry.state') }}</span>
              <span class="value">{{ t(`machine.${plotterStatus.state}`) }}</span>
            </li>
            <li v-if="plotterStatus.total > 0">
              <span>{{ t('workspaces.telemetry.progress') }}</span>
              <span class="value"> {{ plotterStatus.acked }} / {{ plotterStatus.total }} </span>
            </li>
            <li v-if="plotterStatus.message">
              <span>{{ t('workspaces.telemetry.message') }}</span>
              <span class="value">{{ plotterStatus.message }}</span>
            </li>
          </ul>
        </section>
        <section v-else-if="id === 'compare'" :data-test="`rail-${id}`">
          <button
            type="button"
            class="compare-launcher"
            data-test="rail-compare-open"
            @click="emit('open-compare')"
          >
            ⇄ {{ t('compare.open') }}
          </button>
          <p class="hint">{{ t('workspaces.empty.compareHint') }}</p>
        </section>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.workspace-rail {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  background: #fff;
  color: #1e293b;
  border-left: 1px solid #cbd5e1;
  padding: 0.75rem;
  min-width: 18rem;
  max-width: 24rem;
  overflow-y: auto;
}
.workspace-rail__header {
  font-weight: 600;
  font-size: 0.85rem;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.4rem;
}
.workspace-rail__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.empty {
  font-size: 0.8rem;
  color: #64748b;
  font-style: italic;
  margin: 0;
}
.telemetry__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #334155;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.35rem;
  margin-bottom: 0.35rem;
}
.telemetry__metrics {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.8rem;
}
.telemetry__metrics li {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
.telemetry__metrics .value {
  color: #1e293b;
  font-family: ui-monospace, Menlo, monospace;
}
.compare-launcher {
  width: 100%;
  padding: 0.4rem 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  color: #1e293b;
  font-size: 0.85rem;
  cursor: pointer;
}
.compare-launcher:hover {
  background: #e2e8f0;
}
.hint {
  font-size: 0.75rem;
  color: #64748b;
  margin: 0.3rem 0 0;
}
</style>
