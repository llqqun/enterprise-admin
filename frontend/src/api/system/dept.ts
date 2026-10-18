/**
 * 与 `api/system/post.ts` 同一约定：用 `request`（已剥壳），返回业务数据。
 * 写接口的失败提示由响应拦截器统一处理，页面只需关心成功分支。
 */
import { request } from '@/utils/request'
import type { Dept, DeptForm, DeptQuery, TreeSelectNode } from '@/types/api/system'

/** 部门列表是树形且**不分页**，但仍用统一的分页信封。 */
export function listDepts(params: DeptQuery): Promise<{ rows: Dept[]; total: number }> {
  return request.get('/system/dept', { params })
}

export function deptTreeSelect(): Promise<TreeSelectNode[]> {
  return request.get<TreeSelectNode[]>('/system/dept/treeselect')
}

export function getDept(deptId: number): Promise<Dept> {
  return request.get<Dept>(`/system/dept/${deptId}`)
}

export function createDept(data: DeptForm): Promise<Dept> {
  return request.post<Dept>('/system/dept', data)
}

export function updateDept(data: DeptForm & { dept_id: number }): Promise<Dept> {
  return request.put<Dept>('/system/dept', data)
}

export function deleteDept(deptId: number): Promise<null> {
  return request.delete<null>(`/system/dept/${deptId}`)
}