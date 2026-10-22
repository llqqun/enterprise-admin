<script setup lang="ts">
/**
 * Renders the current route, keeping visited pages alive so a tab switch does not
 * lose form state.
 *
 * keep-alive 有两个必须同时满足的条件，缺一个就会**静默**失效（页面不报错，只是每次
 * 都重建组件，输入内容随之丢失）：
 *
 *   1. `:include` 匹配的是**组件名**，不是路由名。所有页面文件都叫 `index.vue`，
 *      推断出的组件名是 `index`；`stores/permission.ts` 在加载组件时把路由名挂到
 *      组件上，两边的口径才一致。
 *   2. `include` 里**不能**排除当前路由。名字一旦不在 include 里，Vue 会立刻把该
 *      组件从缓存中剔除 —— 排除「当前页」等于在回到那一页的瞬间清掉它的缓存。
 *
 * 还有一条 dev-only 的陷阱：`<keep-alive>` 里**只允许一个子节点**，而开发模式下
 * 模板注释会被保留（生产构建才会剥掉），在 `<keep-alive>` 内部写注释会让 dev 编译
 * 直接报 `<KeepAlive> expects exactly one child component.`。所以说明只写在这里。
 *
 * `:key` 用 path 而不是 fullPath：同一页面换查询参数时复用同一个实例（配合
 * `onActivated` 刷新数据），否则每个查询组合都会留下一个缓存副本。
 */
import { computed } from 'vue'

import { useTagsViewStore } from '@/stores/tagsView'
import { buildKeepAliveInclude } from '@/utils/keepAlive'

const tagsView = useTagsViewStore()

/** 所有已打开标签页对应的组件名 —— 包含当前页，也包含固定标签（首页）。 */
const cachedViews = computed(() => buildKeepAliveInclude(tagsView.visitedViews))
</script>

<template>
  <router-view v-slot="{ Component, route: current }">
    <transition name="fade-transform" mode="out-in">
      <keep-alive :include="cachedViews">
        <component :is="Component" :key="current.path" />
      </keep-alive>
    </transition>
  </router-view>
</template>
