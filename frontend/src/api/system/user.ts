/**
 * 与 `api/system/post.ts` 同一约定：用 `request`（已剥壳），返回业务数据。
 * 写接口的失败提示由响应拦截器统一处理，页面只需关心成功分支。
 */
import { request } from '@/utils/request'
import type { PageResult, UserForm, UserQuery, UserRow } from '@/types/api/system'

export function listUsers(params: UserQuery): Promise<PageResult<UserRow>> {
  return request.get<PageResult<UserRow>>('/system/user', { params })
}

export function createUser(data: UserForm): Promise<UserRow> {
  return request.post<UserRow>('/system/user', data)
}

export function updateUser(data: UserForm & { user_id: number }): Promise<UserRow> {
  return request.put<UserRow>('/system/user', data)
}

export function deleteUsers(userIds: number[]): Promise<null> {
  return request.delete<null>(`/system/user/${userIds.join(',')}`)
}

export function resetUserPassword(userId: number, password: string): Promise<null> {
  return request.put<null>('/system/user/resetPwd', { user_id: userId, password })
}

export function changeUserStatus(userId: number, status: string): Promise<null> {
  return request.put<null>('/system/user/changeStatus', { user_id: userId, status })
}