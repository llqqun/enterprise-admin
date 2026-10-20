<script setup lang="ts">
/**
 * 登录日志（只读）。
 *
 * 这一页存在的理由是**失败行**：锁定与撞库只能靠事后翻这些记录发现，所以「状态」筛选
 * 与「失败」的视觉区分比什么都重要。也因此它**没有删除按钮** —— 审计日志能被页面删掉，
 * 就等于审计可被抹除。
 */
import { onMounted, reactive, ref } from 'vue'

import { listLoginLogs } from '@/api/monitor/loginlog'
import type { LoginLog, LoginLogQuery } from '@/types/api/monitor'

const loading = ref(false)
const rows = ref<LoginLog[]>([])
const total = ref(0)

const query = reactive<LoginLogQuery>({
  page_num: 1,
  page_size: 10,
  user_name: '',
  status: undefined,
  begin_date: undefined,
  end_date: undefined,
})

/** `el-date-picker` 用数组表示区间，后端要的是两个独立的日期字符串。 */
const dateRange = ref<[string, string] | null>(null)

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    query.begin_date = dateRange.value?.[0]
    query.end_date = dateRange.value?.[1]
    const data = await listLoginLogs(query)
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
  query.status = undefined
  dateRange.value = null
  handleSearch()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="登录账号">
        <el-input v-model="query.user_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="query.status" placeholder="全部" clearable style="width: 110px">
          <el-option label="成功" value="0" />
          <el-option label="失败" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="登录时间">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="user_name" label="登录账号" min-width="120" />
      <el-table-column label="状态" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'danger'">
            {{ row.status === '0' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ipaddr" label="IP" min-width="130" />
      <el-table-column prop="login_location" label="地点" min-width="100" />
      <el-table-column prop="browser" label="浏览器" min-width="110" />
      <el-table-column prop="os" label="操作系统" min-width="100" />
      <el-table-column prop="msg" label="消息" min-width="180" show-overflow-tooltip />
      <el-table-column prop="login_time" label="登录时间" min-width="170" />
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
      共 {{ total }} 条。这是只读的审计视图 —— 日志可以被查询，但不能从页面上删除。
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
