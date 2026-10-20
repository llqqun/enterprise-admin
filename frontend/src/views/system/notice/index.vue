<script setup lang="ts">
/**
 * 通知公告。
 *
 * `status` 是**已发布 / 已撤回**，不是启用 / 停用：撤回一条公告的预期就是它从首页消失。
 *
 * 正文是富文本（管理员录入），列表里只显示纯文本预览；详情弹窗里用 `v-html` 渲染。
 * 这意味着**谁能编辑公告，谁就能在这个站点上执行脚本** —— 所以公告的编辑权限必须严格限制，
 * 这一点写进了 README 的已知取舍，不是可以忽略的细节。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { createNotice, deleteNotices, listNotices, updateNotice } from '@/api/system/notice'
import type { NoticeQuery, NoticeRow } from '@/api/system/notice'

const TYPE_LABELS: Record<string, string> = { '1': '通知', '2': '公告' }

const loading = ref(false)
const rows = ref<NoticeRow[]>([])
const total = ref(0)
const query = reactive<NoticeQuery>({ page_num: 1, page_size: 10, notice_title: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listNotices(query)
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
  query.notice_title = ''
  query.notice_type = undefined
  query.status = undefined
  handleSearch()
}

// --- 详情 -----------------------------------------------------------------

const detailVisible = ref(false)
const detail = ref<NoticeRow | null>(null)

function openDetail(row: unknown): void {
  detail.value = row as NoticeRow
  detailVisible.value = true
}

// --- 编辑 -----------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<Partial<NoticeRow>>({
  notice_title: '',
  notice_type: '1',
  notice_content: '',
  status: '0',
  remark: '',
})

const rules = {
  notice_title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, {
    notice_id: undefined,
    notice_title: '',
    notice_type: '1',
    notice_content: '',
    status: '0',
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const item = row as NoticeRow
  Object.assign(form, {
    notice_id: item.notice_id,
    notice_title: item.notice_title,
    notice_type: item.notice_type,
    notice_content: item.notice_content,
    status: item.status,
    remark: item.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  submitting.value = true
  try {
    if (form.notice_id) {
      await updateNotice({ ...form, notice_id: form.notice_id })
    } else {
      await createNotice(form)
    }
    ElMessage.success(form.notice_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: unknown): Promise<void> {
  const item = row as NoticeRow
  try {
    await ElMessageBox.confirm(`确认删除公告「${item.notice_title}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteNotices([item.notice_id])
  ElMessage.success('删除成功')
  await fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="标题">
        <el-input v-model="query.notice_title" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="query.notice_type" placeholder="全部" clearable style="width: 110px">
          <el-option label="通知" value="1" />
          <el-option label="公告" value="2" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="query.status" placeholder="全部" clearable style="width: 110px">
          <el-option label="已发布" value="0" />
          <el-option label="已撤回" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:notice:add']" type="primary" @click="openCreate">新增</el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="notice_title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.notice_type === '2' ? 'warning' : 'primary'" disable-transitions>
            {{ TYPE_LABELS[row.notice_type] ?? row.notice_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'info'" disable-transitions>
            {{ row.status === '0' ? '已发布' : '已撤回' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="正文预览" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ row.notice_content.replace(/<[^>]+>/g, '') }}</template>
      </el-table-column>
      <el-table-column prop="create_time" label="创建时间" min-width="165" />
      <el-table-column label="操作" width="190" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          <el-button v-hasPerm="['system:notice:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:notice:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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
      共 {{ total }} 条。只有「已发布」的公告会出现在首页的「最新公告」里。
    </div>

    <!-- 详情：正文是富文本，用 v-html 渲染。能编辑公告的人等于能在这个站点执行脚本，
         所以编辑权限必须严格限制。 -->
    <el-dialog v-model="detailVisible" :title="detail?.notice_title ?? '公告详情'" width="640px">
      <div v-if="detail" class="notice-detail">
        <div class="notice-detail__meta">
          {{ TYPE_LABELS[detail.notice_type] ?? detail.notice_type }} ·
          {{ detail.status === '0' ? '已发布' : '已撤回' }} ·
          {{ detail.create_time ?? '' }}
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -- 正文由管理员录入，见文件头的说明 -->
        <div class="notice-detail__body" v-html="detail.notice_content" />
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="form.notice_id ? '修改公告' : '新增公告'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="标题" prop="notice_title">
          <el-input v-model="form.notice_title" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.notice_type">
            <el-radio value="1">通知</el-radio>
            <el-radio value="2">公告</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="0">已发布</el-radio>
            <el-radio value="1">已撤回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="form.notice_content" type="textarea" :rows="6" placeholder="支持 HTML" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">确定</el-button>
      </template>
    </el-dialog>
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
.notice-detail__meta {
  margin-bottom: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.notice-detail__body {
  line-height: 1.8;
}
</style>
