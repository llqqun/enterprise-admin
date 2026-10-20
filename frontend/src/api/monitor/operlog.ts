/** 操作日志（只读视图 + 受控删除）。 */
import { request } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface OperLog {
  oper_id: number
  title: string
  business_type: number
  method: string
  request_method: string
  oper_name: string
  dept_name: string
  oper_url: string
  oper_ip: string
  oper_location: string
  oper_param: string | null
  json_result: string | null
  status: '0' | '1'
  error_msg: string | null
  cost_ms: number
  oper_time: string
}

export interface OperLogQuery {
  page_num?: number
  page_size?: number
  title?: string
  oper_name?: string
  status?: '0' | '1'
}

export function listOperLogs(params: OperLogQuery): Promise<PageResult<OperLog>> {
  return request.get<PageResult<OperLog>>('/monitor/operlog', { params })
}

export function deleteOperLogs(operIds: number[]): Promise<null> {
  return request.delete<null>(`/monitor/operlog/${operIds.join(',')}`)
}

export function cleanOperLogs(): Promise<null> {
  return request.delete<null>('/monitor/operlog/clean')
}
