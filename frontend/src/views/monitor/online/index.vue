<script setup lang="ts">
/**
 * 在线用户。
 *
 * 「在线」的判据是后端给的：refresh 令牌未过期且未撤销。页面不做自己的判断 ——
 * 用 access 令牌判断会把一个仍在用系统的人显示成离线（access 只有 30 分钟）。
 *
 * 强制下线是**真的把那个会话撤销掉**，所以被强退的人下一次请求会 401，
 * 而不是「页面上看不见了但还能操作」。不能强退自己：那等于用强制手段把自己踢出去，
 * 而退出登录就在右上角。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { forceLogout, listOnline } from '@/api/monitor/online'
import type { OnlineQuery, OnlineSession } from '@/api/monitor/online'

const loading = ref(false)
const rows = ref<OnlineSession[]>([])
const total = ref(0)

const query = reactive<OnlineQuery>({ page_num: 1, page_size: 10, user_name: '', login_ip: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listOnline(query)
    rows.value = data.rows
    total.value = data.total
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page_num = 1
  void fetchList()
}

function handleReset(): void {
  query.user_name = ''
  query.login_ip = ''
  handleSearch()
}

async function handleForceLogout(row: unknown): Promise<void> {
  const session = row as OnlineSession
  try {
    await ElMessageBox.confirm(
      `确认强制下线「${session.nick_name}」的这个会话？对方下一次操作会立即失效。`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await forceLogout(session.access_jti)
    ElMessage.success('已强制下线')
    await fetchList()
  } catch {
    // 「不能强制下线自己的会话」由后端给出，拦截器已经提示过。
  }
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="登录账号">
        <el-input v-model="query.user_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="登录IP">
        <el-input v-model="query.login_ip" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="user_name" label="登录账号" min-width="120" />
      <el-table-column prop="nick_name" label="昵称" min-width="120" />
      <el-table-column prop="login_ip" label="登录IP" min-width="130" />
      <el-table-column prop="browser" label="浏览器" min-width="110" />
      <el-table-column prop="os" label="操作系统" min-width="100" />
      <el-table-column prop="login_time" label="登录时间" min-width="165" />
      <el-table-column prop="refresh_expire" label="会话有效期至" min-width="165" />
      <el-table-column label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button
            v-hasPerm="['monitor:online:forceLogout']"
            link
            type="danger"
            @click="handleForceLogout(row)"
          >
            强制下线
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page_num"
      v-model:page-size="query.page_size"
      class="pagination"
      background
      layout="total, sizes, prev, pager, next"
      :page-sizes="[10, 20, 50]"
      :total="total"
      @size-change="handleSearch"
      @current-change="fetchList"
    />
    <div class="count-hint">
      共 {{ total }} 个活动会话。强制下线会真正撤销那个会话，对方下一次请求就会 401。
    </div>
  </div>
</template>

<style scoped>
.search-bar {
  padding: 4px 0 0;
}
.pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
.count-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
