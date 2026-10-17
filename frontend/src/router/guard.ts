/**
 * Navigation guard.
 *
 * The two things worth knowing:
 *   1. Dynamic routes are registered here, on first authenticated navigation, and
 *      the catch-all goes in **after** them.
 *   2. After registering, the navigation is replayed. Without that, vue-router has
 *      already decided the target is unknown and renders the 404 — a bug that looks
 *      like "the menu works but the page is always blank".
 */
import NProgress from 'nprogress'
import type { Router } from 'vue-router'

import { getRouters } from '@/api/auth'
import { appendCatchAll, usePermissionStore } from '@/stores/permission'
import { useUserStore } from '@/stores/user'
import { getAccessToken } from '@/utils/auth'
import { LAYOUT_ROUTE_NAME, LOGIN_ROUTE_PATH, NOT_FOUND_ROUTE_PATH } from './routes'

import 'nprogress/nprogress.css'

NProgress.configure({ showSpinner: false })

/** Reachable without a session. */
const WHITE_LIST: string[] = [LOGIN_ROUTE_PATH, NOT_FOUND_ROUTE_PATH]

export function setupGuards(router: Router): void {
  router.beforeEach(async (to) => {
    NProgress.start()

    const token = getAccessToken()

    if (!token) {
      if (WHITE_LIST.includes(to.path)) {
        return true
      }
      // Remember where they were headed so login can send them back.
      return { path: LOGIN_ROUTE_PATH, query: { redirect: to.fullPath } }
    }

    if (to.path === LOGIN_ROUTE_PATH) {
      return { path: '/' }
    }

    const user = useUserStore()
    // `hydrated`, not "has roles": an account with no enabled role has `roles: []`
    // and is still fully hydrated, so testing for roles here re-hydrated and
    // replayed the navigation on every pass — an infinite redirect that never
    // reaches a page.
    if (user.hydrated) {
      return true
    }

    // First authenticated navigation in this page's lifetime: hydrate the session.
    try {
      await user.fetchProfile()
      const menus = await getRouters()
      const permission = usePermissionStore()
      // Registered as children of the layout, not at the router root — otherwise the
      // generated pages render outside the shell (no sidebar, no breadcrumb).
      permission
        .generateRoutes(menus)
        .forEach((route) => router.addRoute(LAYOUT_ROUTE_NAME, route))
      appendCatchAll(router)
      // Replay the navigation now that the route exists.
      return { path: to.path, query: to.query, hash: to.hash, replace: true }
    } catch {
      // Profile or menu fetch failed: the session is unusable, so end it locally.
      user.resetAll()
      return { path: LOGIN_ROUTE_PATH, query: { redirect: to.fullPath } }
    }
  })

  router.afterEach(() => {
    NProgress.done()
  })

  router.onError(() => {
    NProgress.done()
  })
}
