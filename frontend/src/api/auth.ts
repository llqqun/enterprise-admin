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
