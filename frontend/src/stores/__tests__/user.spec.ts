/** User store: login, profile hydration and teardown. */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getAccessToken, getRefreshToken, setTokens } from '@/utils/auth'

const loginApi = vi.fn<(params: unknown) => Promise<unknown>>()
const logoutApi = vi.fn<() => Promise<null>>()
const getProfile = vi.fn<() => Promise<unknown>>()

vi.mock('@/api/auth', () => ({
  login: (params: unknown) => loginApi(params),
  logout: () => logoutApi(),
  getProfile: () => getProfile(),
  getCaptcha: vi.fn<() => Promise<never>>(),
  getRouters: vi.fn<() => Promise<never>>(),
}))

const { useUserStore } = await import('@/stores/user')
const { usePermissionStore } = await import('@/stores/permission')

const TOKEN_PAIR = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  expires_in: 1800,
  token_type: 'bearer',
}

const PROFILE = {
  user: {
    user_id: 1,
    user_name: 'admin',
    nick_name: '超级管理员',
    dept_id: 1,
    email: null,
    phonenumber: null,
    sex: '2',
    avatar: null,
    status: '0',
  },
  roles: ['admin'],
  permissions: ['*:*:*'],
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('user store', () => {
  it('login stores both tokens in state and in localStorage', async () => {
    loginApi.mockResolvedValue(TOKEN_PAIR)
    const user = useUserStore()

    await user.login({ username: 'admin', password: 'x', code: 'ABCD', uuid: 'u' })

    expect(user.accessToken).toBe('access-1')
    expect(user.refreshToken).toBe('refresh-1')
    expect(getAccessToken()).toBe('access-1')
    expect(getRefreshToken()).toBe('refresh-1')
  })

  it('fetchProfile fills roles and permissions', async () => {
    getProfile.mockResolvedValue(PROFILE)
    const user = useUserStore()

    await user.fetchProfile()

    expect(user.profile?.user_name).toBe('admin')
    expect(user.roles).toEqual(['admin'])
    expect(user.perms).toEqual(['*:*:*'])
  })

  it('isLoggedIn follows the access token', async () => {
    loginApi.mockResolvedValue(TOKEN_PAIR)
    const user = useUserStore()
    expect(user.isLoggedIn).toBe(false)

    await user.login({ username: 'a', password: 'b', code: 'c', uuid: 'd' })

    expect(user.isLoggedIn).toBe(true)
  })

  it('logout clears tokens, profile and dynamic routes', async () => {
    getProfile.mockResolvedValue(PROFILE)
    logoutApi.mockResolvedValue(null)
    setTokens('access-1', 'refresh-1', 1800)

    const user = useUserStore()
    const permission = usePermissionStore()
    await user.fetchProfile()
    permission.generateRoutes([
      {
        name: 'System',
        path: '/system',
        hidden: false,
        component: null,
        meta: { title: '系统管理', icon: null },
        children: [],
      },
    ])

    await user.logout()

    expect(user.accessToken).toBeNull()
    expect(user.profile).toBeNull()
    expect(user.roles).toEqual([])
    expect(user.perms).toEqual([])
    expect(getAccessToken()).toBeNull()
    expect(permission.dynamicRoutes).toEqual([])
  })

  it('still clears the local session when the logout call fails', async () => {
    logoutApi.mockRejectedValue(new Error('network down'))
    setTokens('access-1', 'refresh-1', 1800)
    const user = useUserStore()

    await user.logout()

    expect(user.accessToken).toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('resetAll is idempotent', () => {
    const user = useUserStore()

    user.resetAll()
    user.resetAll()

    expect(user.accessToken).toBeNull()
  })
})
