// Opt-in diagnostic logger for the "k-means choice reverts to fixed_palette
// on tab switch" investigation. OFF by default — set
// ``localStorage.kdiag = '1'`` in the browser console, reproduce the bug,
// then read the console (filter on ``[KDIAG]``). Remove once the root
// cause is found.
//
// Kept allocation-free and guarded behind a cached flag so it costs
// nothing when disabled.
let _on: boolean | null = null

function enabled(): boolean {
  if (_on === null) {
    try {
      _on = typeof localStorage !== 'undefined' && localStorage.getItem('kdiag') === '1'
    } catch {
      _on = false
    }
  }
  return _on
}

export function kdiag(...args: unknown[]): void {
  if (!enabled()) return
  console.log('[KDIAG]', ...args)
}

export function kdiagTrace(label: string): void {
  if (!enabled()) return
  console.trace(`[KDIAG] ${label}`)
}
