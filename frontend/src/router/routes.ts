/**
 * Static routes, available whether or not the user is authenticated.
 *
 * `/login` and `/404` only: the authenticated shell (layout + dashboard) is added
 * by the router module, and everything else is generated from the user's menus.
 */
import type { RouteRecordRaw } from 'vue-router'

export const LOGIN_ROUTE_PATH = '/login'
export const NOT_FOUND_ROUTE_PATH = '/404'

export const constantRoutes: RouteRecordRaw[] = [
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
