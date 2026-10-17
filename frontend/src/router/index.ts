import { createRouter, createWebHistory } from 'vue-router'

import { setupGuards } from './guard'
import { constantRoutes } from './routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: constantRoutes,
  scrollBehavior: () => ({ top: 0 }),
})

setupGuards(router)

export default router
