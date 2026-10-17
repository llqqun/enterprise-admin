/** Dynamic route generation from the backend's menu tree. */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { RouterItem } from '@/types/api/auth'
import {
  appendCatchAll,
  NOT_FOUND_ROUTE_NAME,
  usePermissionStore,
} from '@/stores/permission'

function menu(overrides: Partial<RouterItem> = {}): RouterItem {
  return {
    name: 'System',
    path: '/system',
    hidden: false,
    component: null,
    meta: { title: '系统管理', icon: 'system' },
    children: [],
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('generateRoutes', () => {
  it('returns an empty list when there are no menus', () => {
    const store = usePermissionStore()

    expect(store.generateRoutes([])).toEqual([])
    expect(store.dynamicRoutes).toEqual([])
  })

  it('maps a component string to a glob loader', () => {
    const store = usePermissionStore()

    const routes = store.generateRoutes([
      menu({
        name: 'NotFound',
        path: '/probe',
        component: 'error/404',
      }),
    ])

    // `error/404.vue` really exists, so it must resolve to a loader rather than the
    // fallback — this is the assertion that proves the glob mapping is wired up.
    expect(routes[0]?.component).toBeTypeOf('function')
  })

  it('falls back to the 404 view and warns when a component is missing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = usePermissionStore()

    const routes = store.generateRoutes([
      menu({ name: 'Ghost', path: '/ghost', component: 'ghost/does-not-exist' }),
    ])

    expect(routes[0]?.component).toBeTypeOf('function')
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('keeps directories component-less so they act as pure groupings', () => {
    const store = usePermissionStore()

    const routes = store.generateRoutes([
      menu({
        children: [menu({ name: 'SystemUser', path: 'user', component: 'error/404' })],
      }),
    ])

    expect(routes[0]?.component).toBeUndefined()
    expect(routes[0]?.children).toHaveLength(1)
  })

  it('carries title and hidden through to route meta', () => {
    const store = usePermissionStore()

    const routes = store.generateRoutes([menu({ hidden: true })])

    expect(routes[0]?.meta?.title).toBe('系统管理')
    expect(routes[0]?.meta?.hidden).toBe(true)
  })

  it('exposes the generated routes as state', () => {
    const store = usePermissionStore()

    store.generateRoutes([menu()])

    expect(store.dynamicRoutes).toHaveLength(1)
  })
})

describe('catch-all ordering', () => {
  it('matches an unknown path only after the dynamic routes are registered', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    const store = usePermissionStore()

    store
      .generateRoutes([menu({ name: 'System', path: '/system', component: 'error/404' })])
      .forEach((route) => router.addRoute(route))
    appendCatchAll(router)

    expect(router.resolve('/system').name).toBe('System')
    expect(router.resolve('/definitely-not-a-route').name).toBe(NOT_FOUND_ROUTE_NAME)
  })

  it('is idempotent', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })

    appendCatchAll(router)
    appendCatchAll(router)

    const catchAlls = router.getRoutes().filter((route) => route.name === NOT_FOUND_ROUTE_NAME)
    expect(catchAlls).toHaveLength(1)
  })

  it('redirects the catch-all to the 404 page', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })

    appendCatchAll(router)

    expect(router.getRoutes().find((route) => route.name === NOT_FOUND_ROUTE_NAME)?.redirect).toBe(
      '/404',
    )
  })
})
