/** 登录日志（只读）。 */
import { request } from '@/utils/request'

import type { LoginLog, LoginLogQuery } from '@/types/api/monitor'
import type { PageResult } from '@/types/api/system'

export function listLoginLogs(params: LoginLogQuery): Promise<PageResult<LoginLog>> {
  return request.get<PageResult<LoginLog>>('/monitor/loginlog', { params })
}
