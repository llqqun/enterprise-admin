/**
 * Navigation guard.
 *
 * The case worth guarding: an account that is authenticated but holds **no enabled
 * role** is a legal state (the backend returns `roles: []`), and it must still be
 * able to reach a page. Using "has roles" as the "already hydrated" sentinel makes
 * the guard re-hydrate and replay the same navigation forever.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router, type RouteRecordRaw } from 'vue-router'
import { defineComponent } from 'vue'

const getProfile = vi.fn<() => Promise<unknown>>()
const getRouters = vi.fn<() => Promise<unknown>>()

vi.mock('@/api/auth', () => ({
  getProfile: () => getProfile(),
  getRouters: () => getRouters(),
  login: vi.fn<(params: unknown) => Promise<never>>(),
  logout: vi.fn<() => Promise<null>>(),
  getCaptcha: vi.fn<() => Promise<never>>(),
}))

// `@/utils/auth` is deliberately NOT mocked. An earlier version mocked
// `getAccessToken` to always return a token, which made `resetAll()` unable to
// clear it and turned the "profile fetch fails" path into an infinite redirect that
// eventually killed the vitest worker. The real module plus jsdom's localStorage
// behaves the way the app does.
const { setupGuards } = await import('@/router/guard')
const { LAYOUT_ROUTE_NAME } = await import('@/router/routes')
const { setTokens } = await import('@/utils/auth')

const STUB = defineComponent({ render: () => null })

function emptyProfile(roles: string[], permissions: string[] = []) {
  return {
    user: {
      user_id: 9,
      user_name: 'roleless',
      nick_name: '无角色用户',
      dept_id: null,
      email: null,
      phonenumber: null,
      sex: null,
      avatar: null,
      status: '0',
    },
    roles,
    permissions,
  }
}

function buildRouter(): Router {
  const routes: RouteRecordRaw[] = [
    {
      path: '/',
      name: LAYOUT_ROUTE_NAME,
      component: STUB,
      children: [{ path: 'dashboard', name: 'Dashboard', component: STUB }],
    },
    { path: '/login', name: 'Login', component: STUB },
  ]
  const router = createRouter({ history: createMemoryHistory(), routes })
  setupGuards(router)
  return router
}

beforeEach(() => {
  localStorage.clear()
  // A token is present, so the guard takes the authenticated branch.
  setTokens('token-1', 'refresh-1', 1800)
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('setupGuards', () => {
  it('reaches the page for an account with no roles, hydrating exactly once', async () => {
    getProfile.mockResolvedValue(emptyProfile([]))
    getRouters.mockResolvedValue([])
    const router = buildRouter()

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(getProfile).toHaveBeenCalledTimes(1)
    expect(getRouters).toHaveBeenCalledTimes(1)
  })

  it('does not re-hydrate on a second navigation', async () => {
    getProfile.mockResolvedValue(emptyProfile([]))
    getRouters.mockResolvedValue([])
    const router = buildRouter()

    await router.push('/dashboard')
    await router.push('/login')

    expect(getProfile).toHaveBeenCalledTimes(1)
  })

  it('still hydrates and registers routes for an account with roles', async () => {
    getProfile.mockResolvedValue(emptyProfile(['staff'], ['system:test:view']))
    getRouters.mockResolvedValue([
      {
        name: 'System',
        path: '/system',
        hidden: false,
        component: null,
        meta: { title: '系统管理', icon: null },
        children: [],
      },
    ])
    const router = buildRouter()

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(router.hasRoute('System')).toBe(true)
  })

  it('ends the session when the profile fetch fails', async () => {
    getProfile.mockRejectedValue(new Error('backend restarting'))
    const router = buildRouter()

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/login')
    // The token was cleared, so the next visit is unauthenticated and cannot loop.
    expect(localStorage.getItem('ea_access_token')).toBeNull()
  })
})
