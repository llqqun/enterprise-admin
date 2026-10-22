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

/**
 * 让加载出来的组件带上**路由名**。
 *
 * `<keep-alive :include>` 匹配的是**组件名**，不是路由名。这里的每个页面文件都叫
 * `index.vue`，SFC 编译器据此推断出的组件名是 `index` —— 于是：
 *
 *   - `include: ['SystemUser']` 永远匹配不上（名字对不上）；
 *   - 改成 `include: ['index']` 更糟：所有页面共用一个名字。
 *
 * 在加载时就挂上路由名，可以让两者自动保持一致，包括后端以后新增的菜单。
 * 这个包装是 keep-alive 能生效的前提，去掉它缓存会静默失效（页面不会报错，只是每次都重建）。
 */
function withRouteName(loader: () => Promise<unknown>, routeName: string) {
  return async () => {
    const mod = (await loader()) as Record<string, unknown> | undefined
    const component = (mod?.default ?? mod) as { name?: string } | undefined
    if (component && typeof component === 'object' && !component.name) {
      component.name = routeName
    }
    return mod
  }
}

function resolveComponent(component: string, routeName: string): RouteRecordRaw['component'] {
  const loader = viewModules[`../views/${component}.vue`]
  if (loader) {
    return withRouteName(loader, routeName) as RouteRecordRaw['component']
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
    route.component = resolveComponent(item.component, item.name)
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
