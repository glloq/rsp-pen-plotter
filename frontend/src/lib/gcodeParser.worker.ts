// Web Worker: off-main-thread G-code parsing (audit B2).
//
// ``parseGcode`` is a single synchronous pass that tessellates arcs and
// builds tens of thousands of SimSegment/SimEvent objects — on a large
// plot it froze the UI the moment the operator opened the Simulator tab
// or regenerated. Running it here keeps the main thread free; the result
// is a plain (structured-cloneable) object graph, so it crosses the
// worker boundary cleanly. The client lives in ``gcodeParser.ts``.

import { parseGcode, type ParseOptions } from './gcode'

interface ParseRequest {
  id: number
  code: string
  opts: ParseOptions
}

// ``self`` in a module worker is the DedicatedWorkerGlobalScope; cast to
// the minimal surface we use so the file typechecks under the DOM lib
// without pulling in the full webworker lib.
const ctx = self as unknown as {
  onmessage: ((e: MessageEvent<ParseRequest>) => void) | null
  postMessage: (message: unknown) => void
}

ctx.onmessage = (e) => {
  const { id, code, opts } = e.data
  try {
    const result = parseGcode(code, opts)
    ctx.postMessage({ id, ok: true, result })
  } catch (err) {
    ctx.postMessage({ id, ok: false, error: err instanceof Error ? err.message : String(err) })
  }
}
