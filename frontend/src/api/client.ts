import axios, { type AxiosInstance } from 'axios'

// Empty default = same origin, so the production appliance can serve the UI
// and API from one host without baking in an address. Dev sets VITE_API_URL
// (see .env.development) to reach the separate backend on port 8000.
const baseURL = import.meta.env.VITE_API_URL ?? ''
const apiKey = import.meta.env.VITE_API_KEY as string | undefined

export const api: AxiosInstance = axios.create({ baseURL, timeout: 30000 })

if (apiKey) {
  api.defaults.headers.common['X-API-Key'] = apiKey
}

export function websocketUrl(path: string): string {
  const origin = baseURL
    ? baseURL.replace(/^http/, 'ws')
    : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  const url = origin + path
  return apiKey ? `${url}?token=${encodeURIComponent(apiKey)}` : url
}

export interface HealthResponse {
  status: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>('/health')
  return response.data
}

export type AlgorithmKind = 'fill' | 'lines' | 'mono_stroke'
export type AlgorithmComplexity = 'low' | 'medium' | 'high'
// Preview latency/fidelity tier the operator picks in the preview pane.
// Defined here (rather than in useEditState) because /preview takes it
// as a form field, and the cost estimator + state composable both
// need to import it — keeping it next to the API client avoids a
// circular dependency.
export type PreviewQuality = 'draft' | 'standard' | 'final'

export interface AlgorithmInfo {
  name: string
  description: string
  kind: AlgorithmKind
  // Static cost class — server-declared, defaults to ``medium`` for any
  // algorithm registered without an explicit entry. Drives the preview
  // pane's seed estimate before the EMA has any real observations.
  complexity?: AlgorithmComplexity
}

export type SegmentationMethod = 'kmeans' | 'luminance_bands' | 'thresholds' | 'fixed_palette'

export async function getAlgorithms(): Promise<AlgorithmInfo[]> {
  const response = await api.get<AlgorithmInfo[]>('/algorithms')
  return response.data
}

export async function getFonts(): Promise<string[]> {
  const response = await api.get<string[]>('/fonts')
  return response.data
}

export interface Preset {
  name: string
  description: string
  options: Record<string, unknown>
}

export async function getPresets(): Promise<Preset[]> {
  const response = await api.get<Preset[]>('/presets')
  return response.data
}

export interface Macro {
  name: string
  description: string
  commands: string[]
}

export async function getMacros(): Promise<Macro[]> {
  const response = await api.get<Macro[]>('/macros')
  return response.data
}

export async function saveMacro(macro: Macro): Promise<Macro> {
  const response = await api.post<Macro>('/macros', macro)
  return response.data
}

export async function deleteMacro(name: string): Promise<void> {
  await api.delete(`/macros/${encodeURIComponent(name)}`)
}

export async function runMacro(name: string): Promise<void> {
  await api.post(`/macros/${encodeURIComponent(name)}/run`)
}

export interface JobRecord {
  job_id: string
  source_file: string
  source_mime: string
  profile_name: string
  status: string
  layer_count: number
  created_at: string
}

export async function getJobs(): Promise<JobRecord[]> {
  const response = await api.get<JobRecord[]>('/jobs')
  return response.data
}

export interface AuditEntry {
  id: number
  timestamp: string
  action: string
  detail: string
}

export async function getAudit(): Promise<AuditEntry[]> {
  const response = await api.get<AuditEntry[]>('/audit')
  return response.data
}

export interface WorkspaceBounds {
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

export interface EbbConfig {
  steps_per_mm: number
  servo_up: number
  servo_down: number
  servo_rate: number
  serial_terminator: 'cr' | 'lf' | 'crlf'
}

export interface Point {
  x: number
  y: number
}

export interface PenSlot {
  index: number
  name: string
  color: string
  installed: boolean
  position: Point | null
  pen_up_command: string | null
  pen_down_command: string | null
}

export type GcodeDialect = 'grbl' | 'marlin' | 'klipper' | 'ebb' | 'custom'
export type Origin = 'top_left' | 'bottom_left' | 'center'
export type ToolChangeMethod = 'manual_pause' | 'carousel' | 'rack' | 'none'

export interface MachineProfile {
  name: string
  units: 'mm' | 'inch'
  workspace: WorkspaceBounds
  origin: Origin
  gcode_dialect: GcodeDialect
  pen_up_command: string
  pen_down_command: string
  tool_change_method: ToolChangeMethod
  tool_change_command: string
  drawing_speed_mm_s: number
  travel_speed_mm_s: number
  acceleration_mm_s2: number
  pen_slot_count: number
  supports_arcs: boolean
  arc_tolerance_mm: number
  ebb: EbbConfig | null
  pens: PenSlot[] | null
  // v0.2 capability model. When set, the backend persists it
  // verbatim; when null the backend derives one from the legacy
  // tool_change_* fields on the fly via ``derive_capabilities``.
  // The CapabilityWizard sends a fully-formed block here when
  // creating a profile, so manual_prompt templates and host_macro
  // line lists round-trip cleanly.
  capabilities?: Record<string, unknown> | null
}

export async function getProfiles(): Promise<MachineProfile[]> {
  const response = await api.get<MachineProfile[]>('/profiles')
  return response.data
}

export async function saveProfile(profile: MachineProfile): Promise<MachineProfile> {
  const response = await api.post<MachineProfile>('/profiles', profile)
  return response.data
}

export async function deleteProfile(name: string): Promise<void> {
  await api.delete(`/profiles/${encodeURIComponent(name)}`)
}

export async function exportProfileYaml(name: string): Promise<string> {
  const response = await api.get<string>(`/profiles/${encodeURIComponent(name)}/export`)
  return response.data
}

export interface BoundingBox {
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

export type PausePolicy = 'auto' | 'always' | 'never'

export type ColorAssignment = 'auto' | 'manual'

export interface LayerInfo {
  layer_id: string
  source_color: string
  target_pen_slot: number | null
  draw_order: number
  total_length_mm: number
  path_count: number
  bbox: BoundingBox
  optimize: boolean
  simplify_tolerance_mm: number
  drawing_speed_mm_s: number | null
  color_label: string | null
  pause_before: PausePolicy
  // Operator-facing colour pick: which hex from the active pool this
  // layer should be drawn with. Populated by the auto-attribution
  // step at /upload + /rerender; the operator can override per layer
  // through the LayerCard picker. ``null`` falls back to source_color.
  assigned_color_hex: string | null
  // Tracks whether ``assigned_color_hex`` came from the auto-nearest
  // step or from a manual override. ``"auto"`` rows refresh on
  // pool changes; ``"manual"`` rows stay pinned.
  color_assignment: ColorAssignment
}

export interface Job {
  job_id: string
  source_file: string
  source_mime: string
  profile_name: string
  layers: LayerInfo[]
  created_at: string
  status: string
}

export interface UploadResponse {
  job: Job
  svg: string
  warnings?: string[]
  metadata?: Record<string, unknown>
}

export interface ToolpathMetrics {
  pen_up_before_mm: number
  pen_up_after_mm: number
  reduction_pct: number
}

export interface LayerOptimization {
  layer_id: string
  optimize: boolean
  simplify_tolerance_mm: number
}

export interface OptimizeResponse {
  svg: string
  layers: LayerInfo[]
  metrics: ToolpathMetrics
}

export async function optimizeToolpaths(
  svg: string,
  layers: LayerOptimization[],
  signal?: AbortSignal,
): Promise<OptimizeResponse> {
  const response = await api.post<OptimizeResponse>('/optimize', { svg, layers }, { signal })
  return response.data
}

// Generate / preflight request shapes are defined by the backend
// Pydantic models and exposed via ``domain/print-plan.ts``. Consumers
// that need the layer / placement / plan types should import them
// directly from there.
import type { PrintPlan, ResolvedPlan } from '../domain/print-plan'

export interface GenerateResponse {
  gcode: string
  line_count: number
  plan_hash: string
  resolved_plan: ResolvedPlan
}

/** Submit a :class:`PrintPlan` to ``/generate`` and return the G-code. */
export async function generateGcode(
  plan: PrintPlan,
  signal?: AbortSignal,
  options: { allowMissingSlots?: boolean } = {},
): Promise<GenerateResponse> {
  const body = options.allowMissingSlots ? { ...plan, allow_missing_slots: true } : plan
  const response = await api.post<GenerateResponse>('/generate', body, { signal })
  return response.data
}

/** Shape of the 409 ``detail`` returned when /generate refuses missing slots. */
export interface MissingPenSlotsDetail {
  reason: 'missing_pen_slots'
  slots: number[]
  message: string
}

/**
 * Recognise the structured 409 response from /generate so the UI can
 * branch on it (prompt the operator, offer the override) instead of
 * dumping the JSON detail into a toast.
 */
export function asMissingPenSlots(err: unknown): MissingPenSlotsDetail | null {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status !== 409) return null
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (
    detail &&
    typeof detail === 'object' &&
    (detail as { reason?: unknown }).reason === 'missing_pen_slots' &&
    Array.isArray((detail as { slots?: unknown }).slots)
  ) {
    return detail as MissingPenSlotsDetail
  }
  return null
}

export interface PreflightReport {
  ok: boolean
  within_bounds: boolean
  width_mm: number
  height_mm: number
  scale: number
  drawing_length_mm: number
  travel_length_mm: number
  estimated_seconds: number
  pen_changes: number
  layer_count: number
  path_count: number
  missing_pen_slots: number[]
  warnings: string[]
  // Set by ``/preflight`` so the frontend can correlate the report with
  // the matching ``/generate`` response — equal hashes mean both
  // endpoints resolved the plan identically.
  plan_hash?: string | null
}

/** Submit a :class:`PrintPlan` to ``/preflight`` and return the report. */
export async function preflightCheck(
  plan: PrintPlan,
  signal?: AbortSignal,
): Promise<PreflightReport> {
  const response = await api.post<PreflightReport>('/preflight', plan, { signal })
  return response.data
}

/** Estimate metrics for a standalone SVG (used by Compare drawer
 *  to fill per-variant metrics without building a full plan). */
export async function preflightSvg(
  svg: string,
  profileName: string,
  signal?: AbortSignal,
): Promise<PreflightReport> {
  const response = await api.post<PreflightReport>(
    '/preflight/svg',
    { svg, profile_name: profileName },
    { signal },
  )
  return response.data
}

/** Fetch an archived resolved plan by its stable hash. */
export async function getResolvedPlan(planHash: string): Promise<ResolvedPlan> {
  const response = await api.get<ResolvedPlan>(`/plans/${encodeURIComponent(planHash)}`)
  return response.data
}

export type RunState = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'canceled'

export interface PrintRun {
  id: string
  name: string
  profile_name: string
  gcode: string
  total_lines: number
  acked_lines: number
  state: RunState
  priority: number
  error: string | null
  /** Layers skipped at runtime under a ``skip_layer`` recovery
   *  policy. Populated by the backend when ``StreamError`` triggers
   *  the skip-and-continue path; empty otherwise. The UI surfaces it
   *  on the run row + a critical toast. */
  skipped_layers?: string[]
  created_at: string
  updated_at: string
}

export async function listQueue(): Promise<PrintRun[]> {
  const response = await api.get<PrintRun[]>('/queue')
  return response.data
}

export async function enqueuePrint(
  name: string,
  profileName: string,
  gcode: string,
  priority = 0,
): Promise<PrintRun> {
  const response = await api.post<PrintRun>('/queue', {
    name,
    profile_name: profileName,
    gcode,
    priority,
  })
  return response.data
}

export async function queueRunAction(
  id: string,
  action: 'pause' | 'resume' | 'cancel',
): Promise<PrintRun> {
  const response = await api.post<PrintRun>(`/queue/${encodeURIComponent(id)}/${action}`)
  return response.data
}

export async function deleteQueuedRun(id: string): Promise<void> {
  await api.delete(`/queue/${encodeURIComponent(id)}`)
}

export interface PlotterStatus {
  connected: boolean
  total: number
  sent: number
  acked: number
  state: string
  message?: string | null
}

export async function plotterConnect(
  port: string,
  baudrate: number,
  terminator: 'cr' | 'lf' | 'crlf' = 'lf',
): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>('/plotter/connect', {
    port,
    baudrate,
    terminator,
  })
  return response.data
}

export async function plotterDisconnect(): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>('/plotter/disconnect')
  return response.data
}

export async function plotterJog(
  dxMm: number,
  dyMm: number,
  profileName: string,
): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>('/plotter/jog', {
    dx_mm: dxMm,
    dy_mm: dyMm,
    profile_name: profileName,
  })
  return response.data
}

export async function plotterGoto(
  xMm: number,
  yMm: number,
  profileName: string,
): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>('/plotter/goto', {
    x_mm: xMm,
    y_mm: yMm,
    profile_name: profileName,
  })
  return response.data
}

export async function plotterHome(profileName: string): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>(
    `/plotter/home?profile_name=${encodeURIComponent(profileName)}`,
  )
  return response.data
}

export async function plotterRun(gcode: string): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>('/plotter/run', { gcode })
  return response.data
}

export async function plotterCommand(action: 'pause' | 'resume' | 'abort'): Promise<PlotterStatus> {
  const response = await api.post<PlotterStatus>(`/plotter/${action}`)
  return response.data
}

export interface SystemUpdateResponse {
  ok: boolean
  previous_commit: string | null
  new_commit: string | null
  updated: boolean
  log: string
  needs_restart: boolean
  forced: boolean
}

export async function systemUpdate(force = false): Promise<SystemUpdateResponse> {
  const response = await api.post<SystemUpdateResponse>(
    '/system/update',
    { force },
    {
      // The update script can take a while (apt, npm install, build).
      timeout: 5 * 60 * 1000,
    },
  )
  return response.data
}

export interface SystemVersionResponse {
  version: string
  commit: string | null
  branch: string | null
  dirty: boolean
  dirty_files: string[]
}

export async function systemVersion(): Promise<SystemVersionResponse> {
  const response = await api.get<SystemVersionResponse>('/system/version')
  return response.data
}

export interface SystemCheckUpdateResponse {
  update_available: boolean
  current_commit: string | null
  remote_commit: string | null
  behind: number
  branch: string | null
  error: string | null
}

export async function systemCheckUpdate(): Promise<SystemCheckUpdateResponse> {
  const response = await api.get<SystemCheckUpdateResponse>('/system/check-update', {
    // Backend caps fetch at 15s, give the HTTP layer a bit more headroom.
    timeout: 20_000,
  })
  return response.data
}

export interface PreviewResponse {
  svg: string
  elapsed_ms: number
  palette: Array<{ color: string; coverage: number }>
  warnings: string[]
  cached: boolean
}

// One pass within a multi-pass layer override: a single colour can be
// drawn as the stack of several algorithms (e.g. contours outline +
// crosshatch fill) using a single ink.
export interface LayerPass {
  algorithm: string
  algorithm_options?: Record<string, unknown>
}

export interface LayerAlgorithmOverride {
  layer_id: string
  // Legacy single-algorithm shape. Kept for back-compat; ``passes`` (when
  // non-empty) takes precedence on the backend.
  algorithm?: string
  algorithm_options?: Record<string, unknown>
  passes?: LayerPass[]
}

export interface RerenderResponse {
  svg: string
  warnings: string[]
}

export async function rerenderJob(
  jobId: string,
  layers: LayerAlgorithmOverride[],
  signal?: AbortSignal,
): Promise<RerenderResponse> {
  const response = await api.post<RerenderResponse>(
    '/rerender',
    { job_id: jobId, layers },
    // No timeout: a heavy multi-pass stack on a high-res placement
    // can take a while. The caller passes ``signal`` so the operator
    // can cancel.
    { signal, timeout: 0 },
  )
  return response.data
}

// ============================== SLO ===================================
// HTTP surface for the SLO budget evaluator (D.4) consumed by the
// Settings → SLO dashboard.

export type SloSeverity = 'healthy' | 'warning' | 'breach'

export interface SloBudget {
  metric: string
  label: string
  p95_ms: number
  min_samples: number
  warn_breach_ratio: number
  alert_on_breach: boolean
}

export interface SloMetricSample {
  metric: string
  value_ms: number
}

export interface SloBudgetStatus {
  budget: SloBudget
  severity: SloSeverity
  observed_p95_ms: number
  breach_count: number
  sample_count: number
}

export interface SloBudgetReport {
  statuses: SloBudgetStatus[]
  overall: SloSeverity
}

export async function getSloBudgets(): Promise<SloBudget[]> {
  const response = await api.get<SloBudget[]>('/slo/budgets')
  return response.data
}

export async function evaluateSloBudgets(
  samples: SloMetricSample[],
  budgets?: SloBudget[],
): Promise<SloBudgetReport> {
  const response = await api.post<SloBudgetReport>('/slo/evaluate', { samples, budgets })
  return response.data
}

// ============================== Manifests =============================

export interface ManifestMetaInfo {
  domain: string
  manifest_version: number
  schema_semver: string
  generated_at: string
  deprecations: { feature: string; deprecated_since: string; remove_after: string }[]
  feature_flags: Record<string, boolean>
}

export interface ManifestEnvelope<T> {
  meta: ManifestMetaInfo
  entries: T[]
}

export async function getManifestDomain(
  domain: string,
): Promise<ManifestEnvelope<Record<string, unknown>>> {
  const response = await api.get<ManifestEnvelope<Record<string, unknown>>>(
    `/manifests/${domain}`,
  )
  return response.data
}

export async function listManifestDomains(): Promise<string[]> {
  const response = await api.get<{ domains: string[] }>('/manifests')
  return response.data.domains
}

/** Shape of the structured ``detail`` returned by /rerender on a 404. */
export type RerenderUnavailableReason =
  | 'unknown_job'
  | 'not_rerenderable'
  | 'missing_bitmap_options'
  | 'missing_original_bytes'
  | 'corrupt_bitmap_options'
  | 'segmentation_failed'

export interface RerenderUnavailableDetail {
  reason: RerenderUnavailableReason
  job_id: string
  message: string
}

/**
 * Recognise the structured 404 from /rerender so the UI can pick a
 * precise prompt — "re-upload this file" vs "not a bitmap source" vs
 * a generic toast — instead of just dumping the message.
 */
export function asRerenderUnavailable(err: unknown): RerenderUnavailableDetail | null {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status !== 404) return null
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (
    detail &&
    typeof detail === 'object' &&
    typeof (detail as { reason?: unknown }).reason === 'string'
  ) {
    return detail as RerenderUnavailableDetail
  }
  return null
}

export interface IntegrityIssue {
  file_id: string
  source_file: string
  reason: string
}

export interface IntegrityReport {
  checked: number
  rerenderable: number
  issues: IntegrityIssue[]
}

/** Library integrity snapshot — see backend ``GET /files/integrity``. */
export async function getFilesIntegrity(): Promise<IntegrityReport> {
  const response = await api.get<IntegrityReport>('/files/integrity')
  return response.data
}

export interface TypographyPreviewResponse {
  svg: string
  truncated: boolean
}

// Live Hershey preview for `.txt` / `.md` sources. Mirrors
// ``previewBitmap``'s contract but hits ``/preview-text`` — the Hershey
// renderer is pure-Python and cheap, so no concurrency limit / cache
// layer beyond what the browser itself provides.
export async function previewText(
  file: File,
  options: Record<string, unknown> | undefined,
  signal?: AbortSignal,
): Promise<TypographyPreviewResponse> {
  const form = new FormData()
  form.append('file', file)
  if (options) form.append('options', JSON.stringify(options))
  const response = await api.post<TypographyPreviewResponse>('/preview-text', form, {
    signal,
    timeout: 15_000,
  })
  return response.data
}

export async function previewBitmap(
  file: File,
  algorithm: string,
  options: Record<string, unknown> | undefined,
  signal?: AbortSignal,
  quality: 'draft' | 'standard' | 'final' = 'standard',
): Promise<PreviewResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('algorithm', algorithm)
  if (options) form.append('options', JSON.stringify(options))
  form.append('quality', quality)
  const response = await api.post<PreviewResponse>('/preview', form, {
    signal,
    // No timeout. Heavy styles (high-density stippling, fine
    // contours, TSP, spiral at Max+ detail, or large native-res
    // sources) can legitimately take minutes on a Pi-class device.
    // The frontend surfaces a cancellable progress toast wired to
    // ``signal`` so the operator interrupts long renders rather than
    // axios giving up at an arbitrary deadline.
    timeout: 0,
  })
  return response.data
}

// Per-page text + image block analysis for a PDF document. The result
// is read-only on the backend (no persistence) and feeds the editor's
// BlockMapCard so the user can map a render preset onto each block.
export interface AnalyzedBlock {
  id: string
  kind: 'text' | 'image'
  bbox: [number, number, number, number]
  text_sample?: string | null
  char_count?: number | null
}

export interface AnalyzedPage {
  page_index: number
  width_mm: number
  height_mm: number
  blocks: AnalyzedBlock[]
}

export interface DocumentAnalysis {
  pages: AnalyzedPage[]
}

export async function analyzeDocument(file: File, signal?: AbortSignal): Promise<DocumentAnalysis> {
  const form = new FormData()
  form.append('file', file)
  const response = await api.post<DocumentAnalysis>('/document/analyze', form, {
    signal,
    timeout: 30_000,
  })
  return response.data
}

// Per-upload options every uploader can opt into without changing call
// sites that don't need them. ``onProgress`` is called whenever axios
// reports new bytes pushed to the server — once the body is fully sent,
// we emit one final ``100`` and the server starts its (untimed)
// conversion work, which the UI surfaces as a separate "converting"
// phase. ``signal`` lets the caller abort the in-flight POST.
export interface UploadOptions {
  onProgress?: (percent: number) => void
  signal?: AbortSignal
}

export async function uploadFile(
  file: File,
  profileName: string,
  options?: Record<string, unknown>,
  upload?: UploadOptions,
): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('profile_name', profileName)
  if (options) {
    form.append('options', JSON.stringify(options))
  }
  // No timeout: /upload with a high-res native source + a heavy
  // algorithm can legitimately take minutes. ``onProgress`` drives a
  // cancellable progress toast in the upload flow; before the toast
  // change, the Apply button only ever showed a generic spinner.
  const response = await api.post<UploadResponse>('/upload', form, {
    timeout: 0,
    signal: upload?.signal,
    onUploadProgress: upload?.onProgress
      ? (e) => {
          if (!e.total) return
          upload.onProgress!(Math.round((e.loaded / e.total) * 100))
        }
      : undefined,
  })
  return response.data
}

// --- File library ------------------------------------------------------

// Fetch the original uploaded bytes for a library entry and wrap them
// in a File object. Lets the editor re-attach a placement's source
// after a refresh / drag-from-library — both flows lose the in-memory
// File handle, but the bytes survive in the library on disk.
export async function downloadOriginalFile(
  fileId: string,
  filename: string,
  mime: string,
): Promise<File> {
  const response = await api.get<Blob>(`/files/${encodeURIComponent(fileId)}/original`, {
    responseType: 'blob',
    timeout: 30_000,
  })
  return new File([response.data], filename, { type: mime })
}

// Absolute URL for the same ``/files/{id}/original`` route, suitable for
// dropping straight into an ``<img>`` / SVG ``<image href>`` so the
// browser HTTP cache covers repeat loads. Used by the canvas to show the
// source preview instead of the plotter SVG.
export function libraryFileOriginalUrl(fileId: string): string {
  return `${baseURL}/files/${encodeURIComponent(fileId)}/original`
}

export interface LibraryFileRecord {
  file_id: string
  sha256: string
  source_file: string
  source_mime: string
  size_bytes: number
  layer_count: number
  folder: string
  created_at: string
}

export interface LibraryFileDetail extends LibraryFileRecord {
  svg: string
  layers: LayerInfo[]
  warnings: string[]
  upload_metadata: Record<string, unknown>
  // True when the upload produced a cached bitmap segmentation, so
  // /rerender can re-run a different algorithm against it. False for
  // vector sources (SVG, PDF) — the algorithm picker has no effect there.
  rerenderable?: boolean
}

export interface LibraryUploadResponse {
  file: LibraryFileDetail
  existing: boolean
}

export type LibrarySortKey = 'name' | 'date' | 'type'
export type LibrarySortOrder = 'asc' | 'desc'

export async function uploadToLibrary(
  file: File,
  folder = '',
  options?: Record<string, unknown>,
  upload?: UploadOptions,
): Promise<LibraryUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('folder', folder)
  if (options) {
    form.append('options', JSON.stringify(options))
  }
  // ``timeout: 0`` so a heavy converter on a Pi-class device isn't
  // killed at the default 30 s deadline. Cancellation belongs to the
  // operator via ``signal``, not to an arbitrary axios timeout.
  const response = await api.post<LibraryUploadResponse>('/files', form, {
    timeout: 0,
    signal: upload?.signal,
    onUploadProgress: upload?.onProgress
      ? (e) => {
          if (!e.total) return
          upload.onProgress!(Math.round((e.loaded / e.total) * 100))
        }
      : undefined,
  })
  return response.data
}

export interface ListLibraryParams {
  folder?: string | null
  search?: string | null
  sort?: LibrarySortKey
  order?: LibrarySortOrder
}

export async function listLibraryFiles(
  params: ListLibraryParams = {},
): Promise<LibraryFileRecord[]> {
  const response = await api.get<LibraryFileRecord[]>('/files', {
    params: {
      folder: params.folder ?? undefined,
      search: params.search ?? undefined,
      sort: params.sort ?? 'date',
      order: params.order ?? 'desc',
    },
  })
  return response.data
}

export async function getLibraryFile(fileId: string): Promise<LibraryFileDetail> {
  const response = await api.get<LibraryFileDetail>(`/files/${encodeURIComponent(fileId)}`)
  return response.data
}

export async function listLibraryFolders(): Promise<string[]> {
  const response = await api.get<string[]>('/files/folders')
  return response.data
}

export async function patchLibraryFile(
  fileId: string,
  patch: { source_file?: string; folder?: string },
): Promise<LibraryFileRecord> {
  const response = await api.patch<LibraryFileRecord>(`/files/${encodeURIComponent(fileId)}`, patch)
  return response.data
}

export async function deleteLibraryFile(fileId: string): Promise<void> {
  await api.delete(`/files/${encodeURIComponent(fileId)}`)
}

// --- Available colours ----------------------------------------------------
//
// Global app-wide inventory of inks the operator owns but doesn't necessarily
// mount in the magazine. Feeds the per-layer colour picker when the operator
// selects the ``available`` or ``union`` palette source.

export interface AvailableColor {
  color_id: string
  hex: string
  name: string
  position: number
  created_at: string
}

export async function listAvailableColors(): Promise<AvailableColor[]> {
  const response = await api.get<AvailableColor[]>('/available-colors')
  return response.data
}

export async function createAvailableColor(
  hex: string,
  name: string = '',
): Promise<AvailableColor> {
  const response = await api.post<AvailableColor>('/available-colors', { hex, name })
  return response.data
}

export async function patchAvailableColor(
  colorId: string,
  patch: Partial<Pick<AvailableColor, 'hex' | 'name' | 'position'>>,
): Promise<AvailableColor> {
  const response = await api.patch<AvailableColor>(
    `/available-colors/${encodeURIComponent(colorId)}`,
    patch,
  )
  return response.data
}

export async function deleteAvailableColor(colorId: string): Promise<void> {
  await api.delete(`/available-colors/${encodeURIComponent(colorId)}`)
}

// --- Palette source setting ----------------------------------------------
//
// Three-way toggle the operator picks in the Plotter drawer's Couleurs
// tab. Decides where the per-layer colour picker reads from: the
// installed pens magazine, the global available-colours inventory, or
// the union of both (dedup by hex).

export type PaletteSource = 'pens' | 'available' | 'union'

export interface PaletteSourceResponse {
  source: PaletteSource
}

export async function getPaletteSource(): Promise<PaletteSource> {
  const response = await api.get<PaletteSourceResponse>('/settings/palette-source')
  return response.data.source
}

export async function setPaletteSource(source: PaletteSource): Promise<PaletteSource> {
  const response = await api.put<PaletteSourceResponse>('/settings/palette-source', {
    source,
  })
  return response.data.source
}
