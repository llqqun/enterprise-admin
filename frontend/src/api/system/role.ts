/**
 * 与 `api/system/post.ts` 同一约定：用 `request`（已剥壳），返回业务数据。
 * 写接口的失败提示由响应拦截器统一处理，页面只需关心成功分支。
 */
import { request } from '@/utils/request'
import type { PageResult, Role, RoleDataScope, RoleForm, RoleQuery, UserRow } from '@/types/api/system'

export function listRoles(params: RoleQuery): Promise<PageResult<Role>> {
  return request.get<PageResult<Role>>('/system/role', { params })
}

export function getRole(roleId: number): Promise<Role> {
  return request.get<Role>(`/system/role/${roleId}`)
}

export function createRole(data: RoleForm): Promise<Role> {
  return request.post<Role>('/system/role', data)
}

export function updateRole(data: RoleForm & { role_id: number }): Promise<Role> {
  return request.put<Role>('/system/role', data)
}

export function deleteRoles(roleIds: number[]): Promise<null> {
  return request.delete<null>(`/system/role/${roleIds.join(',')}`)
}

export function changeRoleStatus(roleId: number, status: string): Promise<null> {
  return request.put<null>('/system/role/changeStatus', { role_id: roleId, status })
}

export function setRoleDataScope(data: RoleDataScope): Promise<Role> {
  return request.put<Role>('/system/role/dataScope', data)
}

export function allocatedUsers(roleId: number, params?: { page_num?: number; page_size?: number }) {
  return request.get<PageResult<UserRow>>('/system/role/authUser/allocatedList', {
    params: { role_id: roleId, ...params },
  })
}

export function cancelUserRole(roleId: number, userId: number): Promise<null> {
  return request.put<null>('/system/role/authUser/cancel', { role_id: roleId, user_id: userId })
}