/** Authentication endpoints. */

import type {
  CaptchaResult,
  LoginParams,
  LoginResult,
  ProfileResult,
  RouterItem,
} from '@/types/api/auth'
import { request } from '@/utils/request'

export function getCaptcha(): Promise<CaptchaResult> {
  return request.get<CaptchaResult>('/auth/captchaImage')
}

export function login(data: LoginParams): Promise<LoginResult> {
  return request.post<LoginResult>('/auth/login', data)
}

export function logout(): Promise<null> {
  return request.post<null>('/auth/logout')
}

export function getProfile(): Promise<ProfileResult> {
  return request.get<ProfileResult>('/auth/profile')
}

export function getRouters(): Promise<RouterItem[]> {
  return request.get<RouterItem[]>('/auth/routers')
}

/** 只包含昵称/邮箱/手机/性别 —— 其余字段是管理动作，走 /system/user。 */
export interface ProfilePatch {
  nick_name: string
  email: string | null
  phonenumber: string | null
  sex: string | null
}

export function updateProfile(data: ProfilePatch): Promise<ProfileResult['user']> {
  return request.put<ProfileResult['user']>('/auth/profile', data)
}

export function changePassword(data: {
  old_password: string
  new_password: string
}): Promise<{ revoked_sessions: number }> {
  return request.put<{ revoked_sessions: number }>('/auth/password', data)
}
