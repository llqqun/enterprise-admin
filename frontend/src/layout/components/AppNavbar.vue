<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores/app'
import { useTagsViewStore } from '@/stores/tagsView'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const user = useUserStore()
const tagsView = useTagsViewStore()

const breadcrumbs = computed(() =>
  route.matched
    .filter((record) => record.meta?.title && record.meta.hidden !== true)
    .map((record) => ({ path: record.path, title: String(record.meta.title) })),
)

const displayName = computed(() => user.profile?.nick_name ?? user.profile?.user_name ?? '未登录')

async function handleLogout(): Promise<void> {
  await user.logout()
  tagsView.reset()
  await router.push('/login')
}
</script>

<template>
  <div class="navbar">
    <div class="navbar__left">
      <el-icon class="navbar__toggle" @click="app.toggleSidebar()">
        <Fold v-if="app.sidebarOpened" />
        <Expand v-else />
      </el-icon>

      <el-breadcrumb separator="/">
        <el-breadcrumb-item v-for="crumb in breadcrumbs" :key="crumb.path">
          {{ crumb.title }}
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="navbar__right">
      <el-tooltip content="切换主题" placement="bottom">
        <el-icon class="navbar__action" @click="app.toggleDark()">
          <Moon v-if="!app.dark" />
          <Sunny v-else />
        </el-icon>
      </el-tooltip>

      <el-dropdown>
        <span class="navbar__user">
          <el-icon><UserFilled /></el-icon>
          <span class="navbar__user-name">{{ displayName }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              角色：{{ user.roles.join('、') || '无' }}
            </el-dropdown-item>
            <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--ea-header-height);
  padding: 0 16px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.navbar__left,
.navbar__right {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.navbar__toggle,
.navbar__action {
  font-size: 18px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}

.navbar__toggle:hover,
.navbar__action:hover {
  color: var(--el-color-primary);
}

.navbar__user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}

.navbar__user-name {
  font-size: 14px;
  color: var(--el-text-color-regular);
}
</style>
