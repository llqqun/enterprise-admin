/** 在线用户（活动会话）。 */
import { request } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface OnlineSession {
  token_id: number
  access_jti: string
  user_name: string
  nick_name: string
  login_ip: string
  browser: string
  os: string
  login_time: string
  refresh_expire: string
}

export interface OnlineQuery {
  page_num?: number
  page_size?: number
  user_name?: string
  login_ip?: string
}

export function listOnline(params: OnlineQuery): Promise<PageResult<OnlineSession>> {
  return request.get<PageResult<OnlineSession>>('/monitor/online', { params })
}

export function forceLogout(accessJti: string): Promise<null> {
  return request.delete<null>(`/monitor/online/${accessJti}`)
}
