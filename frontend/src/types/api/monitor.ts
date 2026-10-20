/** 监控模块的响应类型。 */

import type { PageQuery } from './system'

/** 登录状态：0 成功 / 1 失败。 */
export type LoginStatus = '0' | '1'

export interface LoginLog {
  info_id: number
  user_name: string
  ipaddr: string
  login_location: string
  browser: string
  os: string
  status: LoginStatus
  msg: string
  login_time: string
}

export interface LoginLogQuery extends PageQuery {
  user_name?: string
  status?: LoginStatus
  /** `YYYY-MM-DD`，闭区间。 */
  begin_date?: string
  end_date?: string
}
