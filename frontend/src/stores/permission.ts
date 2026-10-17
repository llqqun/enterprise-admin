/** Dynamic routes derived from the backend's menu tree. */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RouteRecordRaw, Router } from 'vue-router'

import type { RouterItem } from '@/types/api/auth'

/**
 * Every view component, resolved lazily.
 *
 * `import.meta.glob` is the only thing that turns the backend's component *string*
 * into a real component; the key format must match exactly (`../views/x/y.vue`).
 */
const viewModules = import.meta.glob('../views/**/*.vue')

export const NOT_FOUND_ROUTE_NAME = 'NotFoundCatchAll'

const FALLBACK_VIEW = () => import('@/views/error/404.vue')

function resolveComponent(component: string): RouteRecordRaw['component'] {
  const loader = viewModules[`../views/${component}.vue`]
  if (loader) {
    return loader as RouteRecordRaw['component']
  }
  // A menu pointing at a page that does not exist yet must not blank the screen or
  // throw; show the 404 view and say which component was missing.
  console.warn(`[permission] no view found for component "${component}"; falling back to 404`)
  return FALLBACK_VIEW
}

function toRoute(item: RouterItem): RouteRecordRaw {
  const children = item.children.map(toRoute)

  const route = {
    path: item.path,
    name: item.name,
    meta: {
      title: item.meta.title,
      icon: item.meta.icon ?? undefined,
      hidden: item.hidden,
    },
    children,
  } as RouteRecordRaw

  if (item.component) {
    route.component = resolveComponent(item.component)
  }
  // A directory keeps `component` undefined: it is a pure grouping node, and its
  // children render into the nearest ancestor's <router-view>.

  return route
}

/**
 * The catch-all, which must be registered **after** the dynamic routes.
 *
 * Registered before them it matches every path first, and every generated route
 * silently 404s. That is the single most common way this pattern breaks, so it is
 * a separate, explicitly-named step rather than a line buried in a loop.
 */
export function createCatchAllRoute(): RouteRecordRaw {
  return {
    path: '/:pathMatch(.*)*',
    name: NOT_FOUND_ROUTE_NAME,
    redirect: '/404',
    meta: { hidden: true },
  }
}

export function appendCatchAll(router: Router): void {
  if (!router.hasRoute(NOT_FOUND_ROUTE_NAME)) {
    router.addRoute(createCatchAllRoute())
  }
}

export const usePermissionStore = defineStore('permission', () => {
  const dynamicRoutes = ref<RouteRecordRaw[]>([])

  /**
   * Turn a menu tree into route records.
   *
   * An empty menu list is a valid answer (a user with no menu-bearing roles) and
   * yields `[]`, not an error.
   */
  function generateRoutes(menus: RouterItem[]): RouteRecordRaw[] {
    const routes = menus.map(toRoute)
    dynamicRoutes.value = routes
    return routes
  }

  function resetRoutes(): void {
    dynamicRoutes.value = []
  }

  return { dynamicRoutes, generateRoutes, resetRoutes }
})
