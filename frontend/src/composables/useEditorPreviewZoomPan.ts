// Zoom / pan gesture state for the V2 editor preview pane.
//
// Extracted from ``EditPreviewPane.vue`` (Phase 4 of the editor audit) so
// the wheel-zoom / drag-pan / double-click-recentre vocabulary the pane
// shares with the rest of the app lives in one testable place. Pure
// interaction state — no props, no stores — so it unit-tests without a DOM
// mount. The view is intentionally NOT reset on prop changes: the operator
// can flip intent ↔ palette while zoomed into a detail and stay there.
import { computed, ref } from 'vue'

const MIN_ZOOM = 0.2
const MAX_ZOOM = 16

export function useEditorPreviewZoomPan() {
  const zoom = ref(1)
  const panX = ref(0)
  const panY = ref(0)
  const panning = ref(false)
  let panStartX = 0
  let panStartY = 0
  let panInitX = 0
  let panInitY = 0

  // The transform applied to the preview stage. Drops the ease transition
  // while actively panning so the drag tracks the pointer 1:1.
  const contentStyle = computed(() => ({
    transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
    transformOrigin: 'center center',
    transition: panning.value ? 'none' : 'transform 0.08s ease-out',
  }))

  function clampZoom(value: number): number {
    return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value))
  }
  function onWheel(event: WheelEvent): void {
    event.preventDefault()
    const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
    zoom.value = clampZoom(zoom.value * factor)
  }
  function onPanStart(event: PointerEvent): void {
    if (event.button !== 0 && event.button !== 1) return
    panning.value = true
    panStartX = event.clientX
    panStartY = event.clientY
    panInitX = panX.value
    panInitY = panY.value
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }
  function onPanMove(event: PointerEvent): void {
    if (!panning.value) return
    panX.value = panInitX + (event.clientX - panStartX)
    panY.value = panInitY + (event.clientY - panStartY)
  }
  function onPanEnd(event: PointerEvent): void {
    if (!panning.value) return
    panning.value = false
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  }
  function zoomIn(): void {
    zoom.value = clampZoom(zoom.value * 1.25)
  }
  function zoomOut(): void {
    zoom.value = clampZoom(zoom.value / 1.25)
  }
  function resetView(): void {
    zoom.value = 1
    panX.value = 0
    panY.value = 0
  }

  return {
    zoom,
    panX,
    panY,
    panning,
    contentStyle,
    onWheel,
    onPanStart,
    onPanMove,
    onPanEnd,
    zoomIn,
    zoomOut,
    resetView,
  }
}
