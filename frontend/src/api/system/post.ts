/**
 * 岗位接口。
 *
 * 用 `request` 而不是裸 `service`：`service` 的响应拦截器返回的是 AxiosResponse，
 * 调用方得自己取 `.data.data`；`request` 把它剥成了业务数据，失败时已经弹过提示并 reject。
 */
import { request } from '@/utils/request'

import type { PageResult, Post, PostForm, PostOption, PostQuery } from '@/types/api/system'

export function listPosts(params: PostQuery): Promise<PageResult<Post>> {
  return request.get<PageResult<Post>>('/system/post', { params })
}

export function getPost(postId: number): Promise<Post> {
  return request.get<Post>(`/system/post/${postId}`)
}

export function createPost(data: PostForm): Promise<Post> {
  return request.post<Post>('/system/post', data)
}

export function updatePost(data: PostForm & { post_id: number }): Promise<Post> {
  return request.put<Post>('/system/post', data)
}

export function deletePosts(postIds: number[]): Promise<null> {
  // 后端接受逗号分隔的 id 列表；非数字会在那里得到 422。
  return request.delete<null>(`/system/post/${postIds.join(',')}`)
}

export function listPostOptions(): Promise<PostOption[]> {
  return request.get<PostOption[]>('/system/post/optionselect')
}
