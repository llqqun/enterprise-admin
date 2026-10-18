/**
 * 与后端 `{code, msg, data}` 信封对应的业务类型。
 *
 * 分页统一是 `{rows, total}` —— 后端每个列表接口都返回这个形状，包括树形的部门与菜单列表
 * （它们不分页，但仍用同一个信封，前端因此不必为某个接口写特例）。
 */

/** 任何列表接口的返回体。 */
export interface PageResult<T> {
  rows: T[]
  total: number
}

/** 列表接口的通用查询参数。后端把 `page_size` 夹在 1..100。 */
export interface PageQuery {
  page_num?: number
  page_size?: number
}

/** 状态：0 正常 / 1 停用。后端用字符串，不是数字。 */
export type StatusValue = '0' | '1'

export interface Post {
  post_id: number
  post_code: string
  post_name: string
  post_sort: number
  status: StatusValue
  remark: string | null
  create_time?: string | null
}

export interface PostQuery extends PageQuery {
  post_code?: string
  post_name?: string
  status?: StatusValue
}

/** 新增/修改岗位的提交体。 */
export interface PostForm {
  post_id?: number
  post_code: string
  post_name: string
  post_sort: number
  status: StatusValue
  remark?: string | null
}

/** 下拉选项：只含选择必需的三个字段。 */
export interface PostOption {
  post_id: number
  post_code: string
  post_name: string
}
