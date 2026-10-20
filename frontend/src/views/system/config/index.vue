<script setup lang="ts">
/**
 * 参数设置。
 *
 * 「内置」这一列的语义是**不可删除**，不是「不可修改」—— 参数表存在的意义就是能改值。
 * 所以内置行照样能给编辑按钮，只是删除会被后端拒绝并说明是哪一个键。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { createConfig, deleteConfigs, listConfigs, updateConfig } from '@/api/system/config'
import type { ConfigQuery, ConfigRow } from '@/api/system/config'

const loading = ref(false)
const rows = ref<ConfigRow[]>([])
const total = ref(0)
const query = reactive<ConfigQuery>({ page_num: 1, page_size: 10, config_name: '', config_key: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listConfigs(query)
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
  query.config_name = ''
  query.config_key = ''
  handleSearch()
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<Partial<ConfigRow>>({
  config_name: '',
  config_key: '',
  config_value: '',
  is_builtin: false,
  remark: '',
})

const rules = {
  config_name: [{ required: true, message: '请输入参数名称', trigger: 'blur' }],
  config_key: [{ required: true, message: '请输入参数键名', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, {
    config_id: undefined,
    config_name: '',
    config_key: '',
    config_value: '',
    is_builtin: false,
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const item = row as ConfigRow
  Object.assign(form, {
    config_id: item.config_id,
    config_name: item.config_name,
    config_key: item.config_key,
    config_value: item.config_value,
    is_builtin: item.is_builtin,
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
    if (form.config_id) {
      await updateConfig({ ...form, config_id: form.config_id })
    } else {
      await createConfig(form)
    }
    ElMessage.success(form.config_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: unknown): Promise<void> {
  const item = row as ConfigRow
  try {
    await ElMessageBox.confirm(`确认删除参数「${item.config_name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteConfigs([item.config_id])
    ElMessage.success('删除成功')
    await fetchList()
  } catch {
    // 「系统内置参数不允许删除：xxx」由后端给出，并会点明是哪个键
  }
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="参数名称">
        <el-input v-model="query.config_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="参数键名">
        <el-input v-model="query.config_key" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:config:add']" type="primary" @click="openCreate">新增</el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="config_name" label="参数名称" min-width="150" />
      <el-table-column prop="config_key" label="参数键名" min-width="220" />
      <el-table-column prop="config_value" label="参数键值" min-width="150" />
      <el-table-column label="类型" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_builtin ? 'warning' : 'info'" disable-transitions>
            {{ row.is_builtin ? '内置' : '自定义' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:config:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:config:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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
      共 {{ total }} 条。「内置」表示不可删除（可以改值）—— 删掉一个内置键不会关闭任何功能，
      只会让读取方落到兜底值。
    </div>

    <el-dialog v-model="dialogVisible" :title="form.config_id ? '修改参数' : '新增参数'" width="540px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="参数名称" prop="config_name">
          <el-input v-model="form.config_name" placeholder="如 登录验证码开关" />
        </el-form-item>
        <el-form-item label="参数键名" prop="config_key">
          <el-input v-model="form.config_key" placeholder="如 sys.account.captchaEnabled" />
        </el-form-item>
        <el-form-item label="参数键值">
          <el-input v-model="form.config_value" placeholder="如 true" />
        </el-form-item>
        <el-form-item label="系统内置">
          <el-switch v-model="form.is_builtin" />
          <span class="field-hint">内置参数不可删除</span>
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
.field-hint {
  margin-left: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
