<script setup lang="ts">
/**
 * 岗位管理。
 *
 * 这是第一个真正能点开的业务页面，因此它同时是后续四个模块（部门/菜单/角色/用户）的模板：
 * 搜索栏 → 工具栏（按权限码显隐）→ 表格 → 分页 → 新增/修改弹窗。
 *
 * 按钮的显隐交给 `v-hasPerm`，但**拦截在后端**：隐藏只是体验，真正的防线是接口上的
 * `require_perm`。这个页面自己不做任何权限判断。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { createPost, deletePosts, listPosts, updatePost } from '@/api/system/post'
import type { Post, PostForm, PostQuery } from '@/types/api/system'

const loading = ref(false)
const rows = ref<Post[]>([])
const total = ref(0)
const selection = ref<Post[]>([])

const query = reactive<PostQuery>({ page_num: 1, page_size: 10, post_name: '', post_code: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listPosts(query)
    rows.value = data.rows
    total.value = data.total
  } catch {
    // 拦截器已经弹过提示；这里保持表格为空，页面不崩。
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
  query.post_name = ''
  query.post_code = ''
  handleSearch()
}

// ---------------------------------------------------------------------------
// 新增 / 修改
// ---------------------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<PostForm>({
  post_code: '',
  post_name: '',
  post_sort: 0,
  status: '0',
  remark: '',
})

const rules = {
  post_code: [{ required: true, message: '请输入岗位编码', trigger: 'blur' }],
  post_name: [{ required: true, message: '请输入岗位名称', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, { post_id: undefined, post_code: '', post_name: '', post_sort: 0, status: '0', remark: '' })
  dialogVisible.value = true
}

function openEdit(row: Post): void {
  Object.assign(form, {
    post_id: row.post_id,
    post_code: row.post_code,
    post_name: row.post_name,
    post_sort: row.post_sort,
    status: row.status,
    remark: row.remark ?? '',
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
    if (form.post_id) {
      await updatePost({ ...form, post_id: form.post_id })
    } else {
      await createPost(form)
    }
    ElMessage.success(form.post_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

// ---------------------------------------------------------------------------
// 删除
// ---------------------------------------------------------------------------

async function handleDelete(row?: Post): Promise<void> {
  const targets = row ? [row] : selection.value
  if (targets.length === 0) {
    return
  }
  const label = row ? `岗位「${row.post_name}」` : `选中的 ${targets.length} 个岗位`
  try {
    await ElMessageBox.confirm(`确认删除${label}？`, '提示', { type: 'warning' })
  } catch {
    return // 用户取消
  }
  await deletePosts(targets.map((item) => item.post_id))
  ElMessage.success('删除成功')
  await fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="岗位名称">
        <el-input v-model="query.post_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="岗位编码">
        <el-input v-model="query.post_code" placeholder="精确匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:post:add']" type="primary" @click="openCreate">新增</el-button>
      <el-button
        v-hasPerm="['system:post:remove']"
        type="danger"
        :disabled="selection.length === 0"
        @click="handleDelete()"
      >
        删除
      </el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border @selection-change="(val: Post[]) => (selection = val)">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="post_code" label="岗位编码" min-width="140" />
      <el-table-column prop="post_name" label="岗位名称" min-width="160" />
      <el-table-column prop="post_sort" label="排序" width="80" align="center" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'info'">
            {{ row.status === '0' ? '正常' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:post:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:post:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.post_id ? '修改岗位' : '新增岗位'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="岗位编码" prop="post_code">
          <el-input v-model="form.post_code" placeholder="如 dev" />
        </el-form-item>
        <el-form-item label="岗位名称" prop="post_name">
          <el-input v-model="form.post_name" placeholder="如 研发岗" />
        </el-form-item>
        <el-form-item label="排序" prop="post_sort">
          <el-input-number v-model="form.post_sort" :min="0" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="0">正常</el-radio>
            <el-radio value="1">停用</el-radio>
          </el-radio-group>
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
</style>
