<script setup lang="ts">
/**
 * 文件管理。
 *
 * 上传用 `http-request` 自己接管，关掉 `auto-upload` 之外的所有自动行为：默认的
 * `el-upload` 会自己发请求、自己判断成功，而我们要让**后端**决定接受与否，
 * 并把后端的错误原样显示出来（「不允许的文件类型：exe」比「上传失败」有用得多）。
 *
 * 前端的 `accept` 只是给文件选择框一个提示，**不是防线** —— 真正的白名单在后端。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import type { UploadRequestOptions } from 'element-plus'

import { deleteFiles, downloadFile, listFiles, uploadFile } from '@/api/monitor/file'
import type { FileQuery, FileRow } from '@/api/monitor/file'

/** 只是选择框的提示；后端白名单才是防线。 */
const ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.bmp,.pdf,.txt,.md,.csv,.doc,.docx,.xls,.xlsx,.zip'

const loading = ref(false)
const rows = ref<FileRow[]>([])
const total = ref(0)
const query = reactive<FileQuery>({ page_num: 1, page_size: 10, original_name: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listFiles(query)
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
  query.original_name = ''
  handleSearch()
}

/** 由 el-upload 调用；`auto-upload` 打开时每个选中的文件都会走一次。 */
async function handleUpload(options: UploadRequestOptions): Promise<void> {
  try {
    await uploadFile(options.file)
    ElMessage.success(`${options.file.name} 上传成功`)
    await fetchList()
  } catch {
    // 拦截器已经弹出后端的错误文案（例如「不允许的文件类型：exe」）
  }
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

async function handleDownload(row: unknown): Promise<void> {
  const item = row as FileRow
  await downloadFile(item.file_id, item.original_name)
}

async function handleDelete(row: unknown): Promise<void> {
  const item = row as FileRow
  try {
    await ElMessageBox.confirm(
      `确认删除「${item.original_name}」？存储中的文件会一并删除。`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await deleteFiles([item.file_id])
  ElMessage.success('删除成功')
  await fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="文件名">
        <el-input v-model="query.original_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-upload
        v-hasPerm="['monitor:file:upload']"
        :accept="ACCEPT"
        :show-file-list="false"
        :http-request="handleUpload"
        multiple
      >
        <el-button type="primary">上传文件</el-button>
      </el-upload>
    </el-row>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="original_name" label="文件名" min-width="240" show-overflow-tooltip />
      <el-table-column prop="extension" label="类型" width="80" align="center" />
      <el-table-column label="大小" width="100" align="right">
        <template #default="{ row }">{{ sizeLabel(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column prop="upload_by" label="上传人" width="110" />
      <el-table-column prop="create_time" label="上传时间" min-width="165" />
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleDownload(row)">下载</el-button>
          <el-button v-hasPerm="['monitor:file:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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
      共 {{ total }} 个文件。允许的类型：图片、PDF、文本/Markdown/CSV、Office 文档、ZIP；
      单文件上限 10 MB。存储名由服务端生成，客户端文件名只作展示。
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
