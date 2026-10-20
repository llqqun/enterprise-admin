<script setup lang="ts">
/**
 * 字典管理。
 *
 * 两个层级共处一页：左边是「一组选项的名字」（类型），抽屉里是这一组的具体选项（数据）。
 * 这样做的原因是它们的使用方式就是这样 —— 你总是先想到「性别」，再改里面的男/女。
 *
 * 一个语义细节：**改类型的 `dict_type` 会让后端把数据行一起迁移**（`sys_dict_data` 是按
 * 字符串关联的，没有外键）。所以改完之后必须 `invalidateDict()`，否则别的页面还在用旧缓存。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import {
  createDictData,
  createDictType,
  deleteDictData,
  deleteDictTypes,
  listDictData,
  listDictTypes,
  updateDictData,
  updateDictType,
} from '@/api/system/dict'
import type { DictDataRow, DictTypeQuery, DictTypeRow } from '@/api/system/dict'
import DictTag from '@/components/DictTag.vue'
import { invalidateDict } from '@/composables/useDict'

const TAG_TYPES = ['primary', 'success', 'info', 'warning', 'danger'] as const

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

const loading = ref(false)
const rows = ref<DictTypeRow[]>([])
const total = ref(0)
const query = reactive<DictTypeQuery>({ page_num: 1, page_size: 10, dict_name: '', dict_type: '' })

async function fetchTypes(): Promise<void> {
  loading.value = true
  try {
    const data = await listDictTypes(query)
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
  void fetchTypes()
}

function handleReset(): void {
  query.dict_name = ''
  query.dict_type = ''
  handleSearch()
}

const typeDialog = ref(false)
const typeSubmitting = ref(false)
const typeFormRef = ref()
const typeForm = reactive<Partial<DictTypeRow>>({ dict_name: '', dict_type: '', status: '0', remark: '' })
const typeRules = {
  dict_name: [{ required: true, message: '请输入字典名称', trigger: 'blur' }],
  dict_type: [{ required: true, message: '请输入字典类型', trigger: 'blur' }],
}

function openTypeCreate(): void {
  Object.assign(typeForm, { dict_id: undefined, dict_name: '', dict_type: '', status: '0', remark: '' })
  typeDialog.value = true
}

function openTypeEdit(row: unknown): void {
  const item = row as DictTypeRow
  Object.assign(typeForm, {
    dict_id: item.dict_id,
    dict_name: item.dict_name,
    dict_type: item.dict_type,
    status: item.status,
    remark: item.remark ?? '',
  })
  typeDialog.value = true
}

async function submitType(): Promise<void> {
  const valid = await typeFormRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  typeSubmitting.value = true
  try {
    if (typeForm.dict_id) {
      await updateDictType({ ...typeForm, dict_id: typeForm.dict_id })
    } else {
      await createDictType(typeForm)
    }
    ElMessage.success(typeForm.dict_id ? '修改成功' : '新增成功')
    typeDialog.value = false
    // 类型名可能改了，缓存必须失效
    invalidateDict()
    await fetchTypes()
  } finally {
    typeSubmitting.value = false
  }
}

async function removeType(row: unknown): Promise<void> {
  const item = row as DictTypeRow
  try {
    await ElMessageBox.confirm(`确认删除字典「${item.dict_name}」？其下还有数据时会被拒绝。`, '提示', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteDictTypes([item.dict_id])
    ElMessage.success('删除成功')
    invalidateDict(item.dict_type)
    await fetchTypes()
  } catch {
    // 「字典下还有数据，不允许删除」由后端给出
  }
}

// ---------------------------------------------------------------------------
// 数据抽屉
// ---------------------------------------------------------------------------

const drawer = ref(false)
const currentType = ref('')
const currentTypeName = ref('')
const dataLoading = ref(false)
const dataRows = ref<DictDataRow[]>([])

const dataDialog = ref(false)
const dataSubmitting = ref(false)
const dataFormRef = ref()
const dataForm = reactive<Partial<DictDataRow>>({
  dict_type: '',
  dict_label: '',
  dict_value: '',
  dict_sort: 0,
  tag_type: 'info',
  status: '0',
  is_default: false,
  remark: '',
})
const dataRules = {
  dict_label: [{ required: true, message: '请输入标签', trigger: 'blur' }],
  dict_value: [{ required: true, message: '请输入键值', trigger: 'blur' }],
}

async function openData(row: unknown): Promise<void> {
  const item = row as DictTypeRow
  currentType.value = item.dict_type
  currentTypeName.value = item.dict_name
  drawer.value = true
  await fetchData()
}

async function fetchData(): Promise<void> {
  dataLoading.value = true
  try {
    // 这里用管理端的接口（含停用项），因为维护页面需要看到全部并可以改状态
    const data = await listDictData({ dict_type: currentType.value, page_size: 100 })
    dataRows.value = data.rows
  } catch {
    dataRows.value = []
  } finally {
    dataLoading.value = false
  }
}

function openDataCreate(): void {
  Object.assign(dataForm, {
    dict_code: undefined,
    dict_type: currentType.value,
    dict_label: '',
    dict_value: '',
    dict_sort: 0,
    tag_type: 'info',
    status: '0',
    is_default: false,
    remark: '',
  })
  dataDialog.value = true
}

function openDataEdit(row: unknown): void {
  const item = row as DictDataRow
  Object.assign(dataForm, {
    dict_code: item.dict_code,
    dict_type: item.dict_type,
    dict_label: item.dict_label,
    dict_value: item.dict_value,
    dict_sort: item.dict_sort,
    tag_type: item.tag_type || 'info',
    status: item.status,
    is_default: item.is_default,
    remark: item.remark ?? '',
  })
  dataDialog.value = true
}

async function submitData(): Promise<void> {
  const valid = await dataFormRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  dataSubmitting.value = true
  try {
    if (dataForm.dict_code) {
      await updateDictData({ ...dataForm, dict_code: dataForm.dict_code })
    } else {
      await createDictData(dataForm)
    }
    ElMessage.success(dataForm.dict_code ? '修改成功' : '新增成功')
    dataDialog.value = false
    invalidateDict(currentType.value)
    await fetchData()
  } finally {
    dataSubmitting.value = false
  }
}

async function removeData(row: unknown): Promise<void> {
  const item = row as DictDataRow
  try {
    await ElMessageBox.confirm(`确认删除「${item.dict_label}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteDictData([item.dict_code])
  ElMessage.success('删除成功')
  invalidateDict(currentType.value)
  await fetchData()
}

onMounted(fetchTypes)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="字典名称">
        <el-input v-model="query.dict_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="字典类型">
        <el-input v-model="query.dict_type" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:dict:add']" type="primary" @click="openTypeCreate">新增</el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="dict_name" label="字典名称" min-width="150" />
      <el-table-column prop="dict_type" label="字典类型" min-width="180" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <DictTag dict-type="sys_normal_disable" :value="row.status" />
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openData(row)">数据</el-button>
          <el-button v-hasPerm="['system:dict:edit']" link type="primary" @click="openTypeEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:dict:remove']" link type="danger" @click="removeType(row)">删除</el-button>
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
      @current-change="fetchTypes"
    />

    <!-- 类型表单 -->
    <el-dialog v-model="typeDialog" :title="typeForm.dict_id ? '修改字典类型' : '新增字典类型'" width="520px">
      <el-form ref="typeFormRef" :model="typeForm" :rules="typeRules" label-width="90px">
        <el-form-item label="字典名称" prop="dict_name">
          <el-input v-model="typeForm.dict_name" placeholder="如 用户性别" />
        </el-form-item>
        <el-form-item label="字典类型" prop="dict_type">
          <el-input v-model="typeForm.dict_type" placeholder="如 sys_user_sex（业务键，唯一）" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="typeForm.status">
            <el-radio value="0">正常</el-radio>
            <el-radio value="1">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="typeForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="typeDialog = false">取消</el-button>
        <el-button type="primary" :loading="typeSubmitting" @click="submitType">确定</el-button>
      </template>
    </el-dialog>

    <!-- 数据抽屉 -->
    <el-drawer v-model="drawer" :title="`字典数据 —— ${currentTypeName}（${currentType}）`" size="70%">
      <el-row class="toolbar" :gutter="8">
        <el-button v-hasPerm="['system:dict:add']" type="primary" @click="openDataCreate">新增</el-button>
      </el-row>
      <el-table v-loading="dataLoading" :data="dataRows" border>
        <el-table-column prop="dict_label" label="标签" min-width="120" />
        <el-table-column prop="dict_value" label="键值" min-width="100" />
        <el-table-column prop="dict_sort" label="排序" width="80" align="center" />
        <el-table-column label="预览" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.tag_type || undefined" disable-transitions>{{ row.dict_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <DictTag dict-type="sys_normal_disable" :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button v-hasPerm="['system:dict:edit']" link type="primary" @click="openDataEdit(row)">修改</el-button>
            <el-button v-hasPerm="['system:dict:remove']" link type="danger" @click="removeData(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="count-hint">
        这一页列的是全部选项（含停用）。前端渲染标签时只会拿到启用的那些 —— 停用一个字典的意图就是「别再用了」。
      </div>
    </el-drawer>

    <!-- 数据表单 -->
    <el-dialog v-model="dataDialog" :title="dataForm.dict_code ? '修改字典数据' : '新增字典数据'" width="520px">
      <el-form ref="dataFormRef" :model="dataForm" :rules="dataRules" label-width="90px">
        <el-form-item label="字典类型">
          <el-input v-model="dataForm.dict_type" disabled />
        </el-form-item>
        <el-form-item label="标签" prop="dict_label">
          <el-input v-model="dataForm.dict_label" placeholder="如 正常" />
        </el-form-item>
        <el-form-item label="键值" prop="dict_value">
          <el-input v-model="dataForm.dict_value" placeholder="如 0" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="dataForm.dict_sort" :min="0" />
        </el-form-item>
        <el-form-item label="标签颜色">
          <el-select v-model="dataForm.tag_type" clearable placeholder="默认" style="width: 100%">
            <el-option v-for="tag in TAG_TYPES" :key="tag" :label="tag" :value="tag" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="dataForm.status">
            <el-radio value="0">正常</el-radio>
            <el-radio value="1">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dataForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dataDialog = false">取消</el-button>
        <el-button type="primary" :loading="dataSubmitting" @click="submitData">确定</el-button>
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
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
