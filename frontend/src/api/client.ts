import axios, { type AxiosInstance } from 'axios'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api: AxiosInstance = axios.create({ baseURL, timeout: 30000 })

export function websocketUrl(path: string): string {
  return baseURL.replace(/^http/, 'ws') + path
}

export interface HealthResponse {
  status: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>('/health')
  return response.data
}

export interface AlgorithmInfo {
  name: string
  description: string
}

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
): Promise<GenerateResponse> {
  const response = await api.post<GenerateResponse>('/generate', {
    svg,
    profile_name: profileName,
    layers,
    scale_mode: scaleMode,
    margin_mm: marginMm,
  })
  return response.data
}

export interface PlotterStatus {
  connected: boolean
  total: number
  sent: number
  acked: number
  state: string
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
  const response = await api.post<UploadResponse>('/upload', form)
  return response.data
}
