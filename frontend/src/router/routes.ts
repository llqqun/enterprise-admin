/**
 * Static routes, available whether or not the user is authenticated.
 *
 * `/login` and `/404` only: the authenticated shell (layout + dashboard) is added
 * by the router module, and everything else is generated from the user's menus.
 */
import type { RouteRecordRaw } from 'vue-router'

export const LOGIN_ROUTE_PATH = '/login'
export const NOT_FOUND_ROUTE_PATH = '/404'

/**
 * Name of the authenticated shell route.
 *
 * Dynamic routes are registered as its **children**, not at the router root. That
 * is what keeps the sidebar, breadcrumb and tags visible: a top-level API menu route
 * has no component of its own, so at the root it would render its page outside the
 * layout, and the page would appear with the whole shell missing.
 */
export const LAYOUT_ROUTE_NAME = 'Layout'

export const constantRoutes: RouteRecordRaw[] = [
  {
    // The authenticated shell. Its children include the dashboard and, at runtime,
    // every route generated from the user's menus.
    path: '/',
    name: LAYOUT_ROUTE_NAME,
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'HomeFilled' },
      },
    ],
  },
  {
    path: LOGIN_ROUTE_PATH,
    name: 'Login',
    // Lazy so the login page is not in the initial bundle.
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', hidden: true },
  },
  {
    path: NOT_FOUND_ROUTE_PATH,
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', hidden: true },
  },
]
