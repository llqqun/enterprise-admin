/** 通知公告。 */
import { request } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface NoticeRow {
  notice_id: number
  notice_title: string
  /** 1 通知 / 2 公告 */
  notice_type: '1' | '2'
  notice_content: string
  /** 0 已发布 / 1 已撤回 */
  status: '0' | '1'
  remark: string | null
  create_time?: string | null
}

export interface NoticeQuery {
  page_num?: number
  page_size?: number
  notice_title?: string
  notice_type?: '1' | '2'
  status?: '0' | '1'
}

export function listNotices(params: NoticeQuery): Promise<PageResult<NoticeRow>> {
  return request.get<PageResult<NoticeRow>>('/system/notice', { params })
}

/** 首页用：只返回已发布的，最新在前。只要求登录。 */
export function latestNotices(): Promise<NoticeRow[]> {
  return request.get<NoticeRow[]>('/system/notice/latest')
}

export function createNotice(data: Partial<NoticeRow>): Promise<NoticeRow> {
  return request.post<NoticeRow>('/system/notice', data)
}

export function updateNotice(data: Partial<NoticeRow> & { notice_id: number }): Promise<NoticeRow> {
  return request.put<NoticeRow>('/system/notice', data)
}

export function deleteNotices(noticeIds: number[]): Promise<null> {
  return request.delete<null>(`/system/notice/${noticeIds.join(',')}`)
}
