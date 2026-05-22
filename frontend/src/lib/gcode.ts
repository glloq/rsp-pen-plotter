export interface SimSegment {
  x0: number
  y0: number
  x1: number
  y1: number
  drawing: boolean
  duration: number
  startTime: number
}

export interface SimBounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export interface SimResult {
  segments: SimSegment[]
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
}

function parseCoord(token: string): number | null {
  const value = Number(token.slice(1))
  return Number.isFinite(value) ? value : null
}

/**
 * Parse G-code into timed segments for simulation.
 *
 * Recognizes G0/G1 moves and pen-up/pen-down commands (matched against the
 * profile's exact command strings). Each segment carries its duration and
 * cumulative start time so playback can be driven by a single time cursor.
 */
export function parseGcode(gcode: string, options: ParseOptions): SimResult {
  const segments: SimSegment[] = []
  let x = 0
  let y = 0
  let penDown = false
  let feedMmS = options.defaultDrawSpeedMmS
  let drawingTime = 0
  let travelTime = 0
  let elapsed = 0

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
    if (line === '' || line.startsWith(';')) continue
    if (line === options.penUpCommand.trim()) {
      penDown = false
      continue
    }
    if (line === options.penDownCommand.trim()) {
      penDown = true
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

    segments.push({ x0: x, y0: y, x1: nx, y1: ny, drawing, duration, startTime: elapsed })
    if (drawing) {
      drawingTime += duration
      include(x, y)
      include(nx, ny)
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
    drawingTimeSeconds: drawingTime,
    travelTimeSeconds: travelTime,
    totalTimeSeconds: drawingTime + travelTime,
    bounds,
  }
}
