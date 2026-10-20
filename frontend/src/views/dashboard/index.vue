<script setup lang="ts">
/**
 * Landing page.
 *
 * It shows what the backend actually granted this session — roles and permission
 * codes — which makes the RBAC layer visible instead of taking it on faith, and is
 * the quickest way to confirm "this account sees what it should".
 */
import { computed, onMounted, ref } from 'vue'

import { latestNotices } from '@/api/system/notice'
import type { NoticeRow } from '@/api/system/notice'
import { useUserStore } from '@/stores/user'

const user = useUserStore()

const displayName = computed(() => user.profile?.nick_name ?? user.profile?.user_name ?? '未登录')
const isWildcard = computed(() => user.perms.includes('*:*:*'))

/**
 * 最新公告。`/system/notice/latest` 只要求登录（普通员工没有 `system:notice:list`），
 * 而且只返回**已发布**的 —— 撤回的公告出现在首页等于没撤回。
 * 拉取失败时静默留空：首页的主内容是账号信息，不该因为公告取不到就报错。
 */
const notices = ref<NoticeRow[]>([])
const noticeDialog = ref(false)
const activeNotice = ref<NoticeRow | null>(null)

function openNotice(row: unknown): void {
  activeNotice.value = row as NoticeRow
  noticeDialog.value = true
}

onMounted(async () => {
  notices.value = await latestNotices().catch(() => [])
})
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

    <el-card v-if="notices.length" class="dashboard__notices" shadow="never">
      <template #header>最新公告</template>
      <ul class="notice-list">
        <li v-for="item in notices" :key="item.notice_id">
          <el-tag :type="item.notice_type === '2' ? 'warning' : 'primary'" size="small" disable-transitions>
            {{ item.notice_type === '2' ? '公告' : '通知' }}
          </el-tag>
          <el-button link type="primary" class="notice-list__title" @click="openNotice(item)">
            {{ item.notice_title }}
          </el-button>
          <span class="notice-list__time">{{ item.create_time }}</span>
        </li>
      </ul>
    </el-card>

    <el-dialog v-model="noticeDialog" :title="activeNotice?.notice_title ?? '公告'" width="620px">
      <!-- 正文是管理员录入的富文本；能编辑公告的人等于能在这个站点执行脚本，见 README 已知取舍 -->
      <div v-if="activeNotice" class="notice-body" v-html="activeNotice.notice_content" />
      <template #footer>
        <el-button @click="noticeDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-alert
      class="dashboard__note"
      type="info"
      :closable="false"
      title="关于这个演示账号"
      description="左侧菜单与页面上的按钮都由你的角色权限码决定：换一个权限更小的账号登录，菜单会更少、按钮会消失、用户列表的可见行数也会变少 —— 这就是 RBAC 与数据权限。"
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
