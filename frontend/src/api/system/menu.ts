/**
 * 与 `api/system/post.ts` 同一约定：用 `request`（已剥壳），返回业务数据。
 * 写接口的失败提示由响应拦截器统一处理，页面只需关心成功分支。
 */
import { request } from '@/utils/request'
import type { MenuItem, TreeSelectNode } from '@/types/api/system'

export function listMenus(params?: { menu_name?: string; status?: string }) {
  return request.get<{ rows: MenuItem[]; total: number }>('/system/menu/list', { params })
}

export function menuTreeSelect(): Promise<TreeSelectNode[]> {
  return request.get<TreeSelectNode[]>('/system/menu/treeselect')
}

/** 角色授权弹窗：完整菜单树 + 已勾选的菜单 ID。 */
export function roleMenuTreeSelect(roleId: number): Promise<{ menus: TreeSelectNode[]; checkedKeys: number[] }> {
  return request.get(`/system/menu/roleMenuTreeselect/${roleId}`)
}

export function getMenu(menuId: number): Promise<MenuItem> {
  return request.get<MenuItem>(`/system/menu/${menuId}`)
}

export function createMenu(data: Partial<MenuItem>): Promise<MenuItem> {
  return request.post<MenuItem>('/system/menu', data)
}

export function updateMenu(data: Partial<MenuItem>): Promise<MenuItem> {
  return request.put<MenuItem>('/system/menu', data)
}

export function deleteMenu(menuId: number): Promise<null> {
  return request.delete<null>(`/system/menu/${menuId}`)
}