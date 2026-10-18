<script setup lang="ts">
/**
 * 角色管理 —— 含**数据范围设置**弹窗。
 *
 * 这是「数据权限」在界面上的入口：角色页设定 `data_scope` 与自定义部门，用户列表据此
 * 决定谁能看到哪些行。两者是配套的，所以页面里把范围的中文含义直接展示在表格上，
 * 避免使用者要去后端常量里查 `4` 是什么意思。
 *
 * 行数据的处理沿用岗位页的约定：Element Plus 把表格插槽的行标成内部类型 `DefaultRow`，
 * 因此所有消费行的函数都收 `unknown` 并在函数入口转型一次。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { deptTreeSelect } from '@/api/system/dept'
import {
  changeRoleStatus,
  createRole,
  deleteRoles,
  listRoles,
  setRoleDataScope,
  updateRole,
} from '@/api/system/role'
import type { Role, RoleForm, RoleQuery, TreeSelectNode } from '@/types/api/system'

const DATA_SCOPE_LABELS: Record<string, string> = {
  '1': '全部数据',
  '2': '自定义部门',
  '3': '本部门',
  '4': '本部门及以下',
  '5': '仅本人',
}

const loading = ref(false)
const rows = ref<Role[]>([])
const total = ref(0)
const selection = ref<Role[]>([])

const query = reactive<RoleQuery>({ page_num: 1, page_size: 10, role_name: '', role_key: '' })

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listRoles(query)
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
  query.role_name = ''
  query.role_key = ''
  handleSearch()
}

function handleSelectionChange(val: unknown): void {
  selection.value = val as Role[]
}

// ---------------------------------------------------------------------------
// 新增 / 修改
// ---------------------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<RoleForm>({
  role_name: '',
  role_key: '',
  role_sort: 0,
  status: '0',
  remark: '',
})

const rules = {
  role_name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  role_key: [{ required: true, message: '请输入权限字符串', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, { role_id: undefined, role_name: '', role_key: '', role_sort: 0, status: '0', remark: '' })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const role = row as Role
  Object.assign(form, {
    role_id: role.role_id,
    role_name: role.role_name,
    role_key: role.role_key,
    role_sort: role.role_sort,
    status: role.status,
    remark: role.remark ?? '',
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
    if (form.role_id) {
      await updateRole({ ...form, role_id: form.role_id })
    } else {
      await createRole(form)
    }
    ElMessage.success(form.role_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

// ---------------------------------------------------------------------------
// 数据范围
// ---------------------------------------------------------------------------

const scopeVisible = ref(false)
const scopeSubmitting = ref(false)
const scopeForm = reactive({ role_id: 0, role_name: '', data_scope: '1', dept_ids: [] as number[] })
const deptTree = ref<TreeSelectNode[]>([])

async function openScope(row: unknown): Promise<void> {
  const role = row as Role
  deptTree.value = await deptTreeSelect()
  Object.assign(scopeForm, {
    role_id: role.role_id,
    role_name: role.role_name,
    data_scope: role.data_scope,
    dept_ids: [] as number[],
  })
  scopeVisible.value = true
}

async function submitScope(): Promise<void> {
  scopeSubmitting.value = true
  try {
    // 非「自定义部门」时不提交部门 ID：后端在切换范围时会无条件清空旧关联，
    // 但把无关的 ID 传过去只会让意图含糊。
    const deptIds = scopeForm.data_scope === '2' ? scopeForm.dept_ids : []
    await setRoleDataScope({ role_id: scopeForm.role_id, data_scope: scopeForm.data_scope, dept_ids: deptIds })
    ElMessage.success('数据范围已更新')
    scopeVisible.value = false
    await fetchList()
  } finally {
    scopeSubmitting.value = false
  }
}

// ---------------------------------------------------------------------------
// 状态与删除
// ---------------------------------------------------------------------------

async function toggleStatus(row: unknown): Promise<void> {
  const role = row as Role
  const next = role.status === '0' ? '1' : '0'
  try {
    await changeRoleStatus(role.role_id, next)
    role.status = next
    ElMessage.success(next === '0' ? '已启用' : '已停用')
  } catch {
    // 超管角色会被后端拒绝（自锁保护），保持原状态、由拦截器提示。
    await fetchList()
  }
}

async function handleDelete(row?: unknown): Promise<void> {
  const target = row as Role | undefined
  const targets = target ? [target] : selection.value
  if (targets.length === 0) {
    return
  }
  const label = target ? `角色「${target.role_name}」` : `选中的 ${targets.length} 个角色`
  try {
    await ElMessageBox.confirm(`确认删除${label}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteRoles(targets.map((item) => item.role_id))
  ElMessage.success('删除成功')
  await fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="角色名称">
        <el-input v-model="query.role_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item label="权限字符串">
        <el-input v-model="query.role_key" placeholder="精确匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:role:add']" type="primary" @click="openCreate">新增</el-button>
      <el-button
        v-hasPerm="['system:role:remove']"
        type="danger"
        :disabled="selection.length === 0"
        @click="handleDelete()"
      >
        删除
      </el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="role_name" label="角色名称" min-width="140" />
      <el-table-column prop="role_key" label="权限字符串" min-width="150" />
      <el-table-column prop="role_sort" label="排序" width="80" align="center" />
      <el-table-column label="数据范围" min-width="130">
        <template #default="{ row }">
          {{ DATA_SCOPE_LABELS[row.data_scope] ?? row.data_scope }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <!--
            不在前端判断能不能改：真正的拦截是后端接口上的 require_perm。
            没有权限的人点下去会拿到 403，toggleStatus 的 catch 会把状态刷回来。
          -->
          <el-switch :model-value="row.status === '0'" @change="toggleStatus(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:role:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:role:edit']" link type="primary" @click="openScope(row)">数据范围</el-button>
          <el-button v-hasPerm="['system:role:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="form.role_id ? '修改角色' : '新增角色'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="角色名称" prop="role_name">
          <el-input v-model="form.role_name" placeholder="如 部门主管" />
        </el-form-item>
        <el-form-item label="权限字符串" prop="role_key">
          <el-input v-model="form.role_key" placeholder="如 dept_manager（代码里用它判断）" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.role_sort" :min="0" />
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

    <el-dialog v-model="scopeVisible" :title="`数据范围 —— ${scopeForm.role_name}`" width="560px">
      <el-form label-width="100px">
        <el-form-item label="范围">
          <el-radio-group v-model="scopeForm.data_scope">
            <el-radio value="1">全部数据</el-radio>
            <el-radio value="2">自定义部门</el-radio>
            <el-radio value="3">本部门</el-radio>
            <el-radio value="4">本部门及以下</el-radio>
            <el-radio value="5">仅本人</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scopeForm.data_scope === '2'" label="部门">
          <el-tree-select
            v-model="scopeForm.dept_ids"
            :data="deptTree"
            multiple
            show-checkbox
            check-strictly
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            placeholder="选择可见部门"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scopeVisible = false">取消</el-button>
        <el-button type="primary" :loading="scopeSubmitting" @click="submitScope">确定</el-button>
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
