<script setup lang="ts">
/**
 * The sidebar renders from the *route records* the permission store generated, not
 * from the raw menu payload. Both come from the same backend response, so the menu
 * and the router can never disagree about what exists.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import SidebarItem from './SidebarItem.vue'
import { useAppStore } from '@/stores/app'
import { usePermissionStore } from '@/stores/permission'

const route = useRoute()
const app = useAppStore()
const permission = usePermissionStore()

const collapsed = computed(() => !app.sidebarOpened)

// `meta.activeMenu` lets a detail page keep its list entry highlighted.
const activeMenu = computed(() => String(route.meta.activeMenu ?? route.path))
</script>

<template>
  <div class="sidebar">
    <div class="sidebar__brand">
      <span v-if="collapsed">EA</span>
      <span v-else>enterprise-admin</span>
    </div>

    <el-menu
      :default-active="activeMenu"
      :collapse="collapsed"
      :collapse-transition="false"
      unique-opened
      router
      background-color="#1f2a44"
      text-color="#c9d3e4"
      active-text-color="#ffd04b"
    >
      <SidebarItem
        v-for="item in permission.dynamicRoutes"
        :key="item.path"
        :item="item"
        base-path=""
      />
    </el-menu>

    <p v-if="!permission.dynamicRoutes.length && !collapsed" class="sidebar__empty">
      当前账号没有任何菜单权限
    </p>
  </div>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--ea-header-height);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #fff;
  white-space: nowrap;
  background-color: #18213a;
}

.sidebar__empty {
  margin: 24px 12px;
  font-size: 12px;
  color: #8b9bb4;
}

/* The Element Plus menu is dark here, so its own border is noise. */
.sidebar :deep(.el-menu) {
  border-right: none;
}
</style>
