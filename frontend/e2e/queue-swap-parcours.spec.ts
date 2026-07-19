// Queue swap parcours — E2E with fake hardware (v2 P8).
//
// Exercises the v2 realtime + structured-swap chain end to end against
// a live backend (OMNIPLOT_FAKE_HARDWARE=1):
//
//   1. API level: enqueue a program with a tool-change boundary, watch
//      the run pause with the STRUCTURED swap fields (reason / slot /
//      label), resume it, watch it complete.
//   2. WS level: /ws/queue pushes a fresh run-list frame on enqueue.
//   3. UI level: the SwapPromptModal pops for the paused run, shows the
//      ink, and its Resume button drives the run to completion.
//
// Gated on E2E_BACKEND_RUNNING=1 like the operator parcours — a
// Vite-only dev session skips cleanly.

import { expect, test, type APIRequestContext } from '@playwright/test'

const backendUp = process.env.E2E_BACKEND_RUNNING === '1'
const api = 'http://localhost:8000'

// A two-layer program with a guided tool-change boundary in the middle.
// "Custom CoreXY A3" is a manual_pause profile, so the M0 becomes an
// operator-confirm swap action carrying slot 1 + label "Red".
const SWAP_GCODE = 'G21\nG90\nG1 X1 Y1 F600\n; Change to pen slot 1 (Red)\nM0\nG1 X2 Y2\n'
const PROFILE = 'Custom CoreXY A3'

async function drainQueue(request: APIRequestContext): Promise<void> {
  // Deterministic slate: cancel anything active, then delete every run.
  const list = await (await request.get(`${api}/queue`)).json()
  for (const run of list) {
    if (['queued', 'running', 'paused'].includes(run.state)) {
      await request.post(`${api}/queue/${run.id}/cancel`)
    }
  }
  for (const run of list) {
    await request.delete(`${api}/queue/${run.id}`)
  }
}

async function connectFakePlotter(request: APIRequestContext): Promise<void> {
  const res = await request.post(`${api}/plotter/connect`, {
    data: { port: '/dev/fake-e2e', baudrate: 115200, terminator: 'lf' },
  })
  expect(res.ok()).toBeTruthy()
}

async function waitForRunState(
  request: APIRequestContext,
  runId: string,
  predicate: (run: Record<string, unknown>) => boolean,
  timeoutMs = 15_000,
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const run = await (await request.get(`${api}/queue/${runId}`)).json()
    if (predicate(run)) return run
    if (Date.now() > deadline) {
      throw new Error(`run ${runId} never matched: last state=${run.state}`)
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
}

test.describe('Queue swap parcours (fake hardware)', () => {
  test.skip(!backendUp, 'requires E2E_BACKEND_RUNNING=1 with OMNIPLOT_FAKE_HARDWARE=1')

  test.beforeEach(async ({ request }) => {
    await drainQueue(request)
  })

  test('run pauses with structured swap fields, resumes to completion (API)', async ({
    request,
  }) => {
    await connectFakePlotter(request)
    const created = await request.post(`${api}/queue`, {
      data: { name: 'e2e-swap-api', profile_name: PROFILE, gcode: SWAP_GCODE },
    })
    expect(created.ok()).toBeTruthy()
    const runId = (await created.json()).id as string

    // The worker picks the run up, streams to the boundary, and parks it
    // as a durable paused run carrying the structured swap description.
    const paused = await waitForRunState(
      request,
      runId,
      (run) => run.state === 'paused' && Boolean(run.swap_prompt),
    )
    expect(paused.swap_reason).toBe('tool_change')
    expect(paused.swap_slot).toBe(1)
    expect(paused.swap_label).toBe('Red')

    const resumed = await request.post(`${api}/queue/${runId}/resume`)
    expect(resumed.ok()).toBeTruthy()
    const done = await waitForRunState(request, runId, (run) => run.state === 'completed')
    // The prompt is cleared once the run completes.
    expect(done.swap_prompt).toBeNull()
  })

  test('/ws/queue pushes a fresh run-list frame on enqueue', async ({ page, request }) => {
    await page.goto('/')
    // Open the socket from the browser context and collect two frames:
    // the connect snapshot, then the enqueue push.
    const framesPromise = page.evaluate(
      (wsUrl) =>
        new Promise<unknown[][]>((resolve, reject) => {
          const ws = new WebSocket(wsUrl)
          const frames: unknown[][] = []
          ws.onmessage = (event) => {
            frames.push(JSON.parse(event.data as string) as unknown[])
            if (frames.length >= 2) {
              ws.close()
              resolve(frames)
            }
          }
          ws.onerror = () => reject(new Error('ws error'))
          setTimeout(() => reject(new Error('ws frames timeout')), 10_000)
        }),
      `${api.replace('http', 'ws')}/ws/queue`,
    )
    // Give the socket a beat to deliver its connect snapshot, then
    // mutate the queue — the tick must push a second frame.
    await page.waitForTimeout(500)
    const created = await request.post(`${api}/queue`, {
      data: { name: 'e2e-ws-push', profile_name: PROFILE, gcode: 'G1 X1' },
    })
    expect(created.ok()).toBeTruthy()

    const frames = await framesPromise
    expect(Array.isArray(frames[0])).toBeTruthy()
    const last = frames[frames.length - 1] as Array<Record<string, unknown>>
    expect(last.some((run) => run.name === 'e2e-ws-push')).toBeTruthy()
    // Summaries only — the full program payload never rides the socket.
    expect(last.every((run) => !('gcode' in run))).toBeTruthy()
  })

  test('SwapPromptModal pops for the paused run and Resume completes it (UI)', async ({
    page,
    request,
  }) => {
    await connectFakePlotter(request)
    const created = await request.post(`${api}/queue`, {
      data: { name: 'e2e-swap-ui', profile_name: PROFILE, gcode: SWAP_GCODE },
    })
    const runId = (await created.json()).id as string
    await waitForRunState(request, runId, (run) => run.state === 'paused')

    // The SPA (polling + /ws/queue) surfaces the paused run as the
    // full-screen swap modal, naming the ink to install.
    await page.goto('/')
    const modal = page.locator('[data-test="swap-prompt-modal"]')
    await expect(modal).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('[data-test="swap-prompt-text"]')).toContainText('Red')

    await page.locator('[data-test="swap-resume"]').click()
    await expect(modal).toBeHidden({ timeout: 10_000 })
    await waitForRunState(request, runId, (run) => run.state === 'completed')
  })
})
