/** Open page tabs, kept in sync with navigation. */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

export interface VisitedView {
  name: string
  path: string
  title: string
  closable: boolean
}

/** The dashboard tab is always open and never closable. */
const AFFIXED: VisitedView = {
  name: 'Dashboard',
  path: '/dashboard',
  title: '首页',
  closable: false,
}

export const useTagsViewStore = defineStore('tagsView', () => {
  const visitedViews = ref<VisitedView[]>([{ ...AFFIXED }])

  function addView(route: RouteLocationNormalized): void {
    if (!route.name || route.meta.hidden === true) {
      return
    }
    if (visitedViews.value.some((view) => view.path === route.fullPath)) {
      return
    }
    visitedViews.value.push({
      name: String(route.name),
      path: route.fullPath,
      title: String(route.meta.title ?? '未命名'),
      closable: route.name !== AFFIXED.name,
    })
  }

  function removeView(path: string): void {
    visitedViews.value = visitedViews.value.filter(
      (view) => view.path !== path || !view.closable,
    )
  }

  function removeOthers(path: string): void {
    visitedViews.value = visitedViews.value.filter(
      (view) => !view.closable || view.path === path,
    )
  }

  function reset(): void {
    visitedViews.value = [{ ...AFFIXED }]
  }

  return { visitedViews, addView, removeView, removeOthers, reset }
})
