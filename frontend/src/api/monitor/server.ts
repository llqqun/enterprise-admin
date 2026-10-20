/** 服务监控。 */
import { request } from '@/utils/request'

export interface CpuInfo {
  cores_logical: number
  cores_physical: number | null
  percent: number
}

export interface MemoryInfo {
  total_mb: number
  used_mb: number
  available_mb: number
  percent: number
}

export interface SwapInfo {
  total_mb: number
  used_mb: number
  percent: number
}

export interface DiskInfo {
  mount: string
  fstype: string
  total_mb: number
  used_mb: number
  free_mb: number
  percent: number
}

export interface ProcessInfo {
  pid: number
  rss_mb: number
  threads: number
  uptime_seconds: number
  started_at: string
}

export interface RuntimeInfo {
  python: string
  implementation: string
  platform: string
  machine: string
  hostname: string
  pid: number
}

export interface ServerStatus {
  cpu: CpuInfo
  memory: MemoryInfo
  swap: SwapInfo
  disk: DiskInfo[]
  process: ProcessInfo
  runtime: RuntimeInfo
  packages: Record<string, string | null>
}

export function getServerStatus(): Promise<ServerStatus> {
  return request.get<ServerStatus>('/monitor/server')
}
