/** 文件上传与下载。 */
import { request, service } from '@/utils/request'

import type { PageResult } from '@/types/api/system'

export interface FileRow {
  file_id: number
  original_name: string
  extension: string
  content_type: string
  size_bytes: number
  upload_by: string
  create_time?: string | null
}

export interface FileQuery {
  page_num?: number
  page_size?: number
  original_name?: string
}

export function listFiles(params: FileQuery): Promise<PageResult<FileRow>> {
  return request.get<PageResult<FileRow>>('/file', { params })
}

/** 上传。用 `FormData`，让浏览器自己带 boundary。 */
export function uploadFile(file: File): Promise<FileRow> {
  const form = new FormData()
  form.append('file', file)
  return request.post<FileRow>('/file/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteFiles(fileIds: number[]): Promise<null> {
  return request.delete<null>(`/file/${fileIds.join(',')}`)
}

/**
 * 下载。
 *
 * 刻意**不走** `request`：那个封装会剥掉统一信封，而文件是二进制。这里用裸 `service` 拿
 * `responseType: 'blob'`，再由调用方触发浏览器保存 —— 响应拦截器对非信封响应是放行的。
 */
export async function downloadFile(fileId: number, fileName: string): Promise<void> {
  const response = await service.get<Blob>(`/file/download/${fileId}`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
