/** Shapes shared by every endpoint. */

export interface ApiResult<T> {
  code: number
  msg: string
  data: T
}

export interface PageQuery {
  page_num?: number
  page_size?: number
}

export interface PageData<T> {
  rows: T[]
  total: number
}
