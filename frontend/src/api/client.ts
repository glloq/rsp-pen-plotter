import axios, { type AxiosInstance } from 'axios'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api: AxiosInstance = axios.create({ baseURL })

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
