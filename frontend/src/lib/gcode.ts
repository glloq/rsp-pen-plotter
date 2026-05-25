export interface SimSegment {
  x0: number
  y0: number
  x1: number
  y1: number
  drawing: boolean
  duration: number
  startTime: number
  // Current pen slot / colour at the time the segment is plotted. Both
  // remain null until the first tool-change marker is parsed (or stay
  // null entirely on profiles that emit none).
  penSlot: number | null
  colorHex: string | null
  colorLabel: string | null
}

export interface SimBounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export type SimEventType = 'pen_up' | 'pen_down' | 'tool_change' | 'pause'

export interface SimEvent {
  type: SimEventType
  x: number
  y: number
  // Cumulative time in seconds at which the event occurs (matches
  // ``SimSegment.startTime``).
  time: number
  // Populated for tool_change events.
  penSlot?: number | null
  colorHex?: string | null
  colorLabel?: string | null
  // Free-text description for pause events (e.g. the raw G-code line).
  message?: string
}

export interface SimColor {
  hex: string
  label: string
  // Number of drawing segments emitted while this colour was active —
  // lets the UI show a usage hint next to the colour filter chip.
  segmentCount: number
}

export interface SimResult {
  segments: SimSegment[]
  events: SimEvent[]
  colors: SimColor[]
  // Distinct pen slots referenced by tool-change markers.
  penSlots: number[]
  drawingTimeSeconds: number
  travelTimeSeconds: number
  totalTimeSeconds: number
  bounds: SimBounds
}

export interface ParseOptions {
  penUpCommand: string
  penDownCommand: string
  travelSpeedMmS: number
  defaultDrawSpeedMmS: number
  // The profile's pause command (typically ``M0`` or ``M6``). Matched in
  // addition to the hard-coded M0/M1 fallbacks so non-standard dialects
  // still emit pause events.
  toolChangeCommand?: string
}

function parseCoord(token: string): number | null {
  const value = Number(token.slice(1))
  return Number.isFinite(value) ? value : null
}

// Recognise the two pen-change comment shapes emitted by the backend:
//   "; Change to pen slot 2 (Black)"           (multi-pen path)
//   "; Change pen: Red (#ff0000)"               (mono-pen path)
const TOOL_CHANGE_SLOT_RE = /^;\s*Change to pen slot\s+(\d+)\s*\(([^)]*)\)/i
const TOOL_CHANGE_COLOR_RE = /^;\s*Change pen:\s*(.+?)\s*\((#[0-9a-fA-F]{3,8})\)/

// Per-layer info marker — emitted by the backend for every layer regardless
// of pause policy so the parser can attribute every following segment to a
// colour / pen slot. Shape (fixed, machine-readable):
//   ; LAYER label="Black ink" color=#101820 slot=0
// All three keys are always present; colour / slot may be empty strings
// when the layer has no slot assignment.
const LAYER_INFO_RE = /^;\s*LAYER\s+label="([^"]*)"\s+color=(#[0-9a-fA-F]{3,8})?\s+slot=(\d*)/

function isPauseCommand(line: string, toolChangeCommand?: string): boolean {
  // Strip a trailing comment so ``M0 ; pause`` still matches.
  const code = line.split(';')[0]!.trim().toUpperCase()
  if (!code) return false
  if (toolChangeCommand && code === toolChangeCommand.trim().toUpperCase()) return true
  return code === 'M0' || code === 'M00' || code === 'M1' || code === 'M01'
}

/**
 * Parse G-code into timed segments + events for simulation.
 *
 * Recognises G0/G1 moves, pen-up/pen-down commands, tool-change markers
 * (slot- and colour-based comments emitted by the backend) and pause
 * commands. Each segment carries the current pen slot + colour, plus its
 * duration and cumulative start time so playback can be driven by a
 * single time cursor.
 */
export function parseGcode(gcode: string, options: ParseOptions): SimResult {
  const segments: SimSegment[] = []
  const events: SimEvent[] = []
  let x = 0
  let y = 0
  let penDown = false
  let feedMmS = options.defaultDrawSpeedMmS
  let drawingTime = 0
  let travelTime = 0
  let elapsed = 0

  // Current pen state — updated by tool-change comments. Stays null until
  // the first tool-change marker so generic G-code without annotations
  // still parses (segments just get null metadata).
  let currentPenSlot: number | null = null
  let currentColorHex: string | null = null
  let currentColorLabel: string | null = null

  // Aggregations exposed via SimResult.
  const colorStats = new Map<string, SimColor>()
  const penSet = new Set<number>()

  const bounds: SimBounds = {
    minX: Infinity,
    minY: Infinity,
    maxX: -Infinity,
    maxY: -Infinity,
  }

  const include = (px: number, py: number): void => {
    bounds.minX = Math.min(bounds.minX, px)
    bounds.minY = Math.min(bounds.minY, py)
    bounds.maxX = Math.max(bounds.maxX, px)
    bounds.maxY = Math.max(bounds.maxY, py)
  }

  for (const raw of gcode.split('\n')) {
    const line = raw.trim()
    if (line === '') continue

    // Pen-change comments — backend emits these immediately before the
    // ``tool_change_command``. Update the current pen/colour and emit a
    // tool_change event at the pen's current location.
    if (line.startsWith(';')) {
      const layerMatch = line.match(LAYER_INFO_RE)
      if (layerMatch) {
        const label = (layerMatch[1] ?? '').trim()
        const hex = (layerMatch[2] ?? '').toLowerCase()
        const slotStr = layerMatch[3] ?? ''
        const slot = slotStr === '' ? null : Number(slotStr)
        const changed =
          (hex || null) !== currentColorHex ||
          (slot ?? null) !== currentPenSlot ||
          (label || null) !== currentColorLabel
        if (slot !== null && Number.isFinite(slot)) {
          currentPenSlot = slot
          penSet.add(slot)
        }
        if (hex) currentColorHex = hex
        if (label) currentColorLabel = label
        // Only emit a visible tool_change event when the layer actually
        // introduces a new pen/colour — otherwise the simulator would
        // flood the canvas with markers on a single-colour drawing.
        if (changed) {
          events.push({
            type: 'tool_change',
            x,
            y,
            time: elapsed,
            penSlot: currentPenSlot,
            colorHex: currentColorHex,
            colorLabel: currentColorLabel,
          })
        }
        continue
      }
      const slotMatch = line.match(TOOL_CHANGE_SLOT_RE)
      if (slotMatch) {
        const slot = Number(slotMatch[1])
        const label = (slotMatch[2] ?? '').trim()
        if (Number.isFinite(slot)) {
          currentPenSlot = slot
          penSet.add(slot)
          // Colour stays as previously known (slot-based change doesn't
          // carry colour info), but if the label is a recognisable
          // colour name the UI can still use it.
          if (label) currentColorLabel = label
          events.push({
            type: 'tool_change',
            x,
            y,
            time: elapsed,
            penSlot: slot,
            colorHex: currentColorHex,
            colorLabel: currentColorLabel,
          })
        }
        continue
      }
      const colorMatch = line.match(TOOL_CHANGE_COLOR_RE)
      if (colorMatch) {
        const label = (colorMatch[1] ?? '').trim()
        const hex = (colorMatch[2] ?? '').toLowerCase()
        currentColorLabel = label || hex
        currentColorHex = hex
        events.push({
          type: 'tool_change',
          x,
          y,
          time: elapsed,
          penSlot: currentPenSlot,
          colorHex: hex,
          colorLabel: currentColorLabel,
        })
        continue
      }
      // Other comments are ignored.
      continue
    }

    if (line === options.penUpCommand.trim()) {
      penDown = false
      events.push({ type: 'pen_up', x, y, time: elapsed })
      continue
    }
    if (line === options.penDownCommand.trim()) {
      penDown = true
      events.push({ type: 'pen_down', x, y, time: elapsed })
      continue
    }

    if (isPauseCommand(line, options.toolChangeCommand)) {
      events.push({ type: 'pause', x, y, time: elapsed, message: line })
      continue
    }

    const tokens = line.split(/\s+/)
    const code = tokens[0]
    if (code !== 'G0' && code !== 'G1' && code !== 'G00' && code !== 'G01') continue

    let nx = x
    let ny = y
    for (const token of tokens.slice(1)) {
      if (token.startsWith('X')) {
        const v = parseCoord(token)
        if (v !== null) nx = v
      } else if (token.startsWith('Y')) {
        const v = parseCoord(token)
        if (v !== null) ny = v
      } else if (token.startsWith('F')) {
        const v = parseCoord(token)
        if (v !== null && v > 0) feedMmS = v / 60
      }
    }

    const rapid = code === 'G0' || code === 'G00'
    const drawing = penDown && !rapid
    const length = Math.hypot(nx - x, ny - y)
    const speed = drawing ? feedMmS : options.travelSpeedMmS
    const duration = speed > 0 ? length / speed : 0

    segments.push({
      x0: x,
      y0: y,
      x1: nx,
      y1: ny,
      drawing,
      duration,
      startTime: elapsed,
      penSlot: currentPenSlot,
      colorHex: currentColorHex,
      colorLabel: currentColorLabel,
    })
    if (drawing) {
      drawingTime += duration
      include(x, y)
      include(nx, ny)
      // Track segments-per-colour so the filter UI can hide colours that
      // never end up drawing anything.
      const key = currentColorHex ?? '__nocolor__'
      const existing = colorStats.get(key)
      if (existing) {
        existing.segmentCount += 1
      } else {
        colorStats.set(key, {
          hex: currentColorHex ?? '',
          label: currentColorLabel ?? currentColorHex ?? '',
          segmentCount: 1,
        })
      }
    } else {
      travelTime += duration
    }
    elapsed += duration
    x = nx
    y = ny
  }

  if (bounds.minX === Infinity) {
    bounds.minX = 0
    bounds.minY = 0
    bounds.maxX = 1
    bounds.maxY = 1
  }

  return {
    segments,
    events,
    colors: [...colorStats.values()],
    penSlots: [...penSet].sort((a, b) => a - b),
    drawingTimeSeconds: drawingTime,
    travelTimeSeconds: travelTime,
    totalTimeSeconds: drawingTime + travelTime,
    bounds,
  }
}
