/** 参数配置。 */
import { request } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface ConfigRow {
  config_id: number
  config_name: string
  config_key: string
  config_value: string
  is_builtin: boolean
  remark: string | null
  create_time?: string | null
}

export interface ConfigQuery {
  page_num?: number
  page_size?: number
  config_name?: string
  config_key?: string
}

export function listConfigs(params: ConfigQuery): Promise<PageResult<ConfigRow>> {
  return request.get<PageResult<ConfigRow>>('/system/config', { params })
}

export function createConfig(data: Partial<ConfigRow>): Promise<ConfigRow> {
  return request.post<ConfigRow>('/system/config', data)
}

export function updateConfig(data: Partial<ConfigRow> & { config_id: number }): Promise<ConfigRow> {
  return request.put<ConfigRow>('/system/config', data)
}

export function deleteConfigs(configIds: number[]): Promise<null> {
  return request.delete<null>(`/system/config/${configIds.join(',')}`)
}

/** 按键取参数值。只需要登录，不需要「参数管理」权限。 */
export function getConfigValue(key: string): Promise<string> {
  return request.get<string>(`/system/config/configKey/${key}`)
}
