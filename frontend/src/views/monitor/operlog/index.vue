<script setup lang="ts">
/**
 * 操作日志。
 *
 * 与「登录日志」的分工：那个回答「谁进来了」，这个回答「谁做了什么」。写入者是后端接口上的
 * `@oper_log` 装饰器，所以这一页能看到模块标题、请求方式、耗时与失败原因。
 *
 * 请求参数里**密码已经被后端脱敏**，页面不需要也不应该再做一次处理 —— 如果这里还得处理一次，
 * 说明后端漏了，那是要修后端而不是在展示层补救。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { cleanOperLogs, deleteOperLogs, listOperLogs } from '@/api/monitor/operlog'
import type { OperLog, OperLogQuery } from '@/api/monitor/operlog'

const BUSINESS_LABELS: Record<number, string> = {
  0: '其它',
  1: '新增',
  2: '修改',
  3: '删除',
  4: '授权',
  5: '导出',
  6: '导入',
  7: '强退',
  9: '清空',
}

const loading = ref(false)
const rows = ref<OperLog[]>([])
const total = ref(0)
const selection = ref<OperLog[]>([])

const query = reactive<OperLogQuery>({ page_num: 1, page_size: 10, title: '', oper_name: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listOperLogs(query)
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
  query.title = ''
  query.oper_name = ''
  query.status = undefined
  handleSearch()
}

function handleSelectionChange(val: unknown): void {
  selection.value = val as OperLog[]
}

async function handleDelete(row?: unknown): Promise<void> {
  const target = row as OperLog | undefined
  const targets = target ? [target] : selection.value
  if (targets.length === 0) {
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除 ${targets.length} 条操作日志？删除动作本身会留下一条记录。`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await deleteOperLogs(targets.map((item) => item.oper_id))
  ElMessage.success('删除成功')
  await fetchList()
}

async function handleClean(): Promise<void> {
  try {
    await ElMessageBox.confirm('确认清空全部操作日志？这会写一条「谁清空了审计」的记录。', '警告', {
      type: 'warning',
    })
  } catch {
    return
  }
  await cleanOperLogs()
  ElMessage.success('已清空')
  await fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="模块标题">
        <el-input v-model="query.title" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="操作人">
        <el-input v-model="query.oper_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="query.status" placeholder="全部" clearable style="width: 110px">
          <el-option label="正常" value="0" />
          <el-option label="异常" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button
        v-hasPerm="['monitor:operlog:remove']"
        type="danger"
        :disabled="selection.length === 0"
        @click="handleDelete()"
      >
        删除
      </el-button>
      <el-button v-hasPerm="['monitor:operlog:remove']" type="warning" @click="handleClean">清空</el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="title" label="模块" min-width="110" />
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">{{ BUSINESS_LABELS[row.business_type] ?? row.business_type }}</template>
      </el-table-column>
      <el-table-column prop="oper_name" label="操作人" width="110" />
      <el-table-column prop="request_method" label="方式" width="80" align="center" />
      <el-table-column prop="oper_url" label="URL" min-width="180" show-overflow-tooltip />
      <el-table-column prop="oper_ip" label="IP" width="120" />
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'danger'">
            {{ row.status === '0' ? '正常' : '异常' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="cost_ms" label="耗时(ms)" width="90" align="center" />
      <el-table-column prop="oper_time" label="时间" min-width="165" />
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['monitor:operlog:remove']" link type="danger" @click="handleDelete(row)">
            删除
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
      共 {{ total }} 条。请求参数由后端写入时脱敏（密码字段替换为 ***），页面不再做二次处理。
    </div>
  </div>
</template>

<style scoped>
.search-bar {
  padding: 4px 0 0;
}
.toolbar {
  margin-bottom: 12px;
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
