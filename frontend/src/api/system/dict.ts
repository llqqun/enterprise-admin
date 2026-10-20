/** 字典接口。 */
import { request } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface DictTypeRow {
  dict_id: number
  dict_name: string
  dict_type: string
  status: '0' | '1'
  remark: string | null
  create_time?: string | null
}

export interface DictDataRow {
  dict_code: number
  dict_type: string
  dict_label: string
  dict_value: string
  dict_sort: number
  tag_type: string
  css_class: string
  is_default: boolean
  status: '0' | '1'
  remark: string | null
}

export interface DictTypeQuery {
  page_num?: number
  page_size?: number
  dict_name?: string
  dict_type?: string
  status?: '0' | '1'
}

export interface DictDataQuery {
  page_num?: number
  page_size?: number
  dict_type?: string
  dict_label?: string
  status?: '0' | '1'
}

// --- 类型 -----------------------------------------------------------------

export function listDictTypes(params: DictTypeQuery): Promise<PageResult<DictTypeRow>> {
  return request.get<PageResult<DictTypeRow>>('/system/dict/type', { params })
}

export function createDictType(data: Partial<DictTypeRow>): Promise<DictTypeRow> {
  return request.post<DictTypeRow>('/system/dict/type', data)
}

export function updateDictType(data: Partial<DictTypeRow> & { dict_id: number }): Promise<DictTypeRow> {
  return request.put<DictTypeRow>('/system/dict/type', data)
}

export function deleteDictTypes(dictIds: number[]): Promise<null> {
  return request.delete<null>(`/system/dict/type/${dictIds.join(',')}`)
}

// --- 数据 -----------------------------------------------------------------

export function listDictData(params: DictDataQuery): Promise<PageResult<DictDataRow>> {
  return request.get<PageResult<DictDataRow>>('/system/dict/data', { params })
}

/** 按类型取**启用中**的选项。只需要登录，不需要字典管理权限。 */
export function dictByType(dictType: string): Promise<DictDataRow[]> {
  return request.get<DictDataRow[]>(`/system/dict/data/type/${dictType}`)
}

export function createDictData(data: Partial<DictDataRow>): Promise<DictDataRow> {
  return request.post<DictDataRow>('/system/dict/data', data)
}

export function updateDictData(data: Partial<DictDataRow> & { dict_code: number }): Promise<DictDataRow> {
  return request.put<DictDataRow>('/system/dict/data', data)
}

export function deleteDictData(dictCodes: number[]): Promise<null> {
  return request.delete<null>(`/system/dict/data/${dictCodes.join(',')}`)
}
