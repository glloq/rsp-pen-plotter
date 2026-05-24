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
): Promise<OptimizeResponse> {
  const response = await api.post<OptimizeResponse>('/optimize', { svg, layers })
  return response.data
}

export interface GenerateLayer {
  layer_id: string
  target_pen_slot: number | null
  drawing_speed_mm_s: number | null
  source_color?: string | null
  color_label?: string | null
  pause_before?: PausePolicy
}

export interface Placement {
  sheet_width_mm: number
  sheet_height_mm: number
  offset_x_mm: number
  offset_y_mm: number
}

export interface GenerateResponse {
  gcode: string
  line_count: number
}

export async function generateGcode(
  svg: string,
  profileName: string,
  layers: GenerateLayer[],
  scaleMode: 'fit' | 'actual' = 'fit',
  marginMm = 10,
  placement?: Placement | null,
): Promise<GenerateResponse> {
  const response = await api.post<GenerateResponse>('/generate', {
    svg,
    profile_name: profileName,
    layers,
    scale_mode: scaleMode,
    margin_mm: marginMm,
    placement: placement ?? null,
  })
  return response.data
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
}

export async function preflightCheck(
  svg: string,
  profileName: string,
  layers: GenerateLayer[],
  scaleMode: 'fit' | 'actual' = 'fit',
  marginMm = 10,
  placement?: Placement | null,
): Promise<PreflightReport> {
  const response = await api.post<PreflightReport>('/preflight', {
    svg,
    profile_name: profileName,
    layers,
    scale_mode: scaleMode,
    margin_mm: marginMm,
    placement: placement ?? null,
  })
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

export async function plotterCommand(
  action: 'pause' | 'resume' | 'abort',
): Promise<PlotterStatus> {
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

export async function analyzeDocument(
  file: File,
  signal?: AbortSignal,
): Promise<DocumentAnalysis> {
  const form = new FormData()
  form.append('file', file)
  const response = await api.post<DocumentAnalysis>('/document/analyze', form, {
    signal,
    timeout: 30_000,
  })
  return response.data
}

export async function uploadFile(
  file: File,
  profileName: string,
  options?: Record<string, unknown>,
): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('profile_name', profileName)
  if (options) {
    form.append('options', JSON.stringify(options))
  }
  // No timeout: /upload with a high-res native source + a heavy
  // algorithm can legitimately take minutes. The Apply button shows
  // a loading state; future work can promote it to a progress toast
  // with cancel like /preview now does.
  const response = await api.post<UploadResponse>('/upload', form, { timeout: 0 })
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
): Promise<LibraryUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('folder', folder)
  if (options) {
    form.append('options', JSON.stringify(options))
  }
  const response = await api.post<LibraryUploadResponse>('/files', form)
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
  const response = await api.patch<LibraryFileRecord>(
    `/files/${encodeURIComponent(fileId)}`,
    patch,
  )
  return response.data
}

export async function deleteLibraryFile(fileId: string): Promise<void> {
  await api.delete(`/files/${encodeURIComponent(fileId)}`)
}
