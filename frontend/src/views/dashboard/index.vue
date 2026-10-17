<script setup lang="ts">
/**
 * Landing page.
 *
 * It shows what the backend actually granted this session — roles and permission
 * codes — which makes the RBAC layer visible instead of taking it on faith, and is
 * the quickest way to confirm "this account sees what it should".
 */
import { computed } from 'vue'

import { useUserStore } from '@/stores/user'

const user = useUserStore()

const displayName = computed(() => user.profile?.nick_name ?? user.profile?.user_name ?? '未登录')
const isWildcard = computed(() => user.perms.includes('*:*:*'))
</script>

<template>
  <div class="dashboard">
    <el-card shadow="never">
      <template #header>
        <div class="dashboard__header">
          <span>欢迎回来，{{ displayName }}</span>
          <el-tag v-if="user.roles.includes('admin')" type="danger" size="small">超级管理员</el-tag>
        </div>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="账号">{{ user.profile?.user_name }}</el-descriptions-item>
        <el-descriptions-item label="部门 ID">
          {{ user.profile?.dept_id ?? '未分配' }}
        </el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag v-for="role in user.roles" :key="role" class="dashboard__tag" size="small">
            {{ role }}
          </el-tag>
          <span v-if="!user.roles.length">无</span>
        </el-descriptions-item>
        <el-descriptions-item label="权限数量">
          {{ isWildcard ? '全部（*:*:*）' : user.perms.length }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="dashboard__perms">
        <p class="dashboard__perms-title">权限标识</p>
        <el-tag
          v-for="code in user.perms"
          :key="code"
          class="dashboard__tag"
          type="info"
          size="small"
        >
          {{ code }}
        </el-tag>
        <span v-if="!user.perms.length" class="dashboard__empty">
          该账号没有任何权限标识，左侧菜单为空是预期行为。
        </span>
      </div>
    </el-card>

    <el-alert
      class="dashboard__note"
      type="info"
      :closable="false"
      title="本页为 P0 交付范围"
      description="动态路由、按钮级权限与登录闭环已完成；用户/角色/菜单/部门/岗位等业务页面属于 P1，因此这些菜单项目前会落到 404 页。"
    />
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dashboard__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dashboard__perms {
  margin-top: 16px;
}

.dashboard__perms-title {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.dashboard__tag {
  margin: 0 6px 6px 0;
}

.dashboard__empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.dashboard__note {
  flex: 0 0 auto;
}
</style>
