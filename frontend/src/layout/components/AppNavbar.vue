<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores/app'
import { useTagsViewStore } from '@/stores/tagsView'
import { useUserStore } from '@/stores/user'
import ProfileDialog from './ProfileDialog.vue'

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

const profileVisible = ref(false)

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
            <el-dropdown-item divided @click="profileVisible = true">个人中心</el-dropdown-item>
            <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <ProfileDialog v-model="profileVisible" />
  </div>
</template>

<style scoped lang="scss">
// 这个块用到了 variables.scss 与 mixins.scss 里的一切，但**没有一行 @use** ——
// 它们由 vite.config.ts 的 additionalData 自动注入。这就是 SCSS 工具链接通的证据。
.navbar {
  @include flex-between;

  height: var(--ea-header-height);
  padding: 0 $space-4;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);

  &__left,
  &__right {
    @include flex($align: center, $gap: $space-4);

    min-width: 0;
  }

  &__toggle,
  &__action {
    font-size: 18px;
    color: var(--el-text-color-regular);
    cursor: pointer;

    &:hover {
      color: var(--el-color-primary);
    }
  }

  &__user {
    @include flex($align: center, $gap: 6px);

    cursor: pointer;
    outline: none;
  }

  &__user-name {
    @include text-ellipsis;

    font-size: $font-size-base;
    color: var(--el-text-color-regular);
  }
}
</style>