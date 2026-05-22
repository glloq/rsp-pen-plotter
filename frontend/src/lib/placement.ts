import type { BoundingBox, MachineProfile } from '../api/client'

export interface Placement {
  /** Scale factor applied to user units to reach workspace millimeters. */
  scale: number
  /** Map a user-unit point to workspace millimeters. */
  transform: (x: number, y: number) => [number, number]
  /** Drawing footprint in workspace millimeters, as a bounding box. */
  footprint: BoundingBox
  /** Drawing dimensions in millimeters. */
  widthMm: number
  heightMm: number
  /** Whether the placed drawing falls outside the workspace. */
  exceeds: boolean
}

export function unionBounds(boxes: BoundingBox[]): BoundingBox | null {
  if (boxes.length === 0) return null
  const u: BoundingBox = {
    x_min: Infinity,
    y_min: Infinity,
    x_max: -Infinity,
    y_max: -Infinity,
  }
  for (const b of boxes) {
    u.x_min = Math.min(u.x_min, b.x_min)
    u.y_min = Math.min(u.y_min, b.y_min)
    u.x_max = Math.max(u.x_max, b.x_max)
    u.y_max = Math.max(u.y_max, b.y_max)
  }
  return Number.isFinite(u.x_min) ? u : null
}

/**
 * Mirror of the backend `_make_transform` / `_exceeds_workspace` logic
 * (backend/pen_plotter/core/gcode.py), so the preview shows the same
 * placement, scale and out-of-bounds state the generator will produce.
 */
export function computePlacement(
  bounds: BoundingBox,
  profile: MachineProfile,
  scaleMode: 'fit' | 'actual',
  marginMm: number,
): Placement {
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  const bboxW = Math.max(bounds.x_max - bounds.x_min, 1e-9)
  const bboxH = Math.max(bounds.y_max - bounds.y_min, 1e-9)

  let scale: number
  if (scaleMode === 'actual') {
    scale = 1.0
  } else {
    const usableW = Math.max(wsW - 2 * marginMm, 1e-9)
    const usableH = Math.max(wsH - 2 * marginMm, 1e-9)
    scale = Math.min(usableW / bboxW, usableH / bboxH)
  }

  const bboxCx = (bounds.x_min + bounds.x_max) / 2
  const bboxCy = (bounds.y_min + bounds.y_max) / 2
  const wsCx = (ws.x_min + ws.x_max) / 2
  const wsCy = (ws.y_min + ws.y_max) / 2
  const yUp = profile.origin === 'bottom_left' || profile.origin === 'center'

  const transform = (x: number, y: number): [number, number] => [
    wsCx + (x - bboxCx) * scale,
    wsCy + (y - bboxCy) * scale * (yUp ? -1 : 1),
  ]

  const corners: [number, number][] = [
    transform(bounds.x_min, bounds.y_min),
    transform(bounds.x_min, bounds.y_max),
    transform(bounds.x_max, bounds.y_min),
    transform(bounds.x_max, bounds.y_max),
  ]
  const footprint: BoundingBox = {
    x_min: Math.min(...corners.map((c) => c[0])),
    y_min: Math.min(...corners.map((c) => c[1])),
    x_max: Math.max(...corners.map((c) => c[0])),
    y_max: Math.max(...corners.map((c) => c[1])),
  }

  const tol = 0.01
  const exceeds = corners.some(
    ([x, y]) =>
      x < ws.x_min - tol || x > ws.x_max + tol || y < ws.y_min - tol || y > ws.y_max + tol,
  )

  return {
    scale,
    transform,
    footprint,
    widthMm: bboxW * scale,
    heightMm: bboxH * scale,
    exceeds,
  }
}
