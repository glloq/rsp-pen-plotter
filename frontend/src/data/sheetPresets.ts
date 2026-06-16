// Shared paper-format presets (A6 … Letter), dimensions in mm and in
// PORTRAIT orientation. Consumed by both the plan view's LayoutSection and
// the editor modal's SheetPicker so a sheet picked in one matches the other —
// the two used to keep hand-maintained, must-stay-identical copies of this
// table.

export interface SheetPreset {
  name: string
  /** Width in mm (portrait). */
  w: number
  /** Height in mm (portrait). */
  h: number
}

export const SHEET_PRESETS: SheetPreset[] = [
  { name: 'A6', w: 105, h: 148 },
  { name: 'A5', w: 148, h: 210 },
  { name: 'A4', w: 210, h: 297 },
  { name: 'A3', w: 297, h: 420 },
  { name: 'A2', w: 420, h: 594 },
  { name: 'Letter', w: 216, h: 279 },
]
