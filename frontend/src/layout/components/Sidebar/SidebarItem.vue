<script setup lang="ts">
/** One sidebar node: a submenu when it has visible children, otherwise a link. */
import { computed } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

const props = defineProps<{
  item: RouteRecordRaw
  basePath: string
}>()

const INVISIBLE = 'hidden'

/** Join a child's relative path onto its parent's absolute one. */
function resolvePath(routePath: string): string {
  if (routePath.startsWith('/')) {
    return routePath
  }
  return `${props.basePath}/${routePath}`.replace(/\/{2,}/g, '/')
}

const fullPath = computed(() => resolvePath(props.item.path))
const title = computed(() => String(props.item.meta?.title ?? ''))
const icon = computed(() => props.item.meta?.icon as string | undefined)

const visibleChildren = computed<RouteRecordRaw[]>(
  () => (props.item.children ?? []).filter((child) => child.meta?.[INVISIBLE] !== true),
)

const isLeaf = computed(() => visibleChildren.value.length === 0)
</script>

<template>
  <el-menu-item v-if="isLeaf" :index="fullPath">
    <el-icon v-if="icon"><component :is="icon" /></el-icon>
    <template #title>{{ title }}</template>
  </el-menu-item>

  <el-sub-menu v-else :index="fullPath">
    <template #title>
      <el-icon v-if="icon"><component :is="icon" /></el-icon>
      <span>{{ title }}</span>
    </template>
    <SidebarItem
      v-for="child in visibleChildren"
      :key="child.path"
      :item="child"
      :base-path="fullPath"
    />
  </el-sub-menu>
</template>
