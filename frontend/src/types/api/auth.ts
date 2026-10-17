/** Authentication and permission payloads, mirroring the backend schemas. */

export interface LoginParams {
  username: string
  password: string
  code: string
  uuid: string
}

export interface LoginResult {
  access_token: string
  refresh_token: string
  expires_in: number
  token_type: string
}

export interface CaptchaResult {
  uuid: string
  /** base64 PNG without a `data:` prefix; empty when captcha is disabled. */
  img: string
  captcha_enabled: boolean
}

export interface UserProfile {
  user_id: number
  user_name: string
  nick_name: string
  dept_id: number | null
  email: string | null
  phonenumber: string | null
  sex: string | null
  avatar: string | null
  status: string
}

export interface ProfileResult {
  user: UserProfile
  roles: string[]
  permissions: string[]
}

/** One node of the dynamic route tree the backend hands out after login. */
export interface RouterItem {
  name: string
  path: string
  hidden: boolean
  component: string | null
  meta: {
    title: string
    icon: string | null
  }
  children: RouterItem[]
}
