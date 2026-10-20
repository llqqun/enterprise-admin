<script setup lang="ts">
/**
 * 用户管理 —— 数据权限的**效果展示面**。
 *
 * 同一份数据、同一个接口，用不同角色登录会看到不同的行数与不同的 `total`：
 * 管理员看全部，部门主管看本部门及以下，仅本人角色只看到自己。这是 S2 的验收点，所以这一页
 * 刻意不做任何前端过滤 —— 它显示的就是后端愿意给它的那些行。
 *
 * 另外两处守卫由后端执行、前端只负责显示失败原因：
 * - 不能删除或停用**自己**的账号；
 * - 不能移除**最后一个启用的超管**。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { deptTreeSelect } from '@/api/system/dept'
import { listRoles } from '@/api/system/role'
import {
  changeUserStatus,
  createUser,
  deleteUsers,
  listUsers,
  resetUserPassword,
  updateUser,
} from '@/api/system/user'
import type { Role, TreeSelectNode, UserForm, UserQuery, UserRow } from '@/types/api/system'
import { hasPermission } from '@/utils/permission'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const loading = ref(false)
const rows = ref<UserRow[]>([])
const total = ref(0)
const selection = ref<UserRow[]>([])

const query = reactive<UserQuery>({ page_num: 1, page_size: 10, user_name: '' })

const deptTree = ref<TreeSelectNode[]>([])
const roleOptions = ref<Role[]>([])

/** 把部门树摊平成 id → 名称，列表里显示名称而不是数字。 */
const deptNames = computed(() => {
  const map = new Map<number, string>()
  const walk = (nodes: TreeSelectNode[]): void => {
    for (const node of nodes) {
      map.set(node.id, node.label)
      walk(node.children)
    }
  }
  walk(deptTree.value)
  return map
})

function deptLabel(deptId: number | null): string {
  if (deptId === null) {
    return '—'
  }
  return deptNames.value.get(deptId) ?? String(deptId)
}

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listUsers(query)
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
  handleSearch()
}

function handleSelectionChange(val: unknown): void {
  selection.value = val as UserRow[]
}

// ---------------------------------------------------------------------------
// 新增 / 修改
// ---------------------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<UserForm>({
  user_name: '',
  nick_name: '',
  password: '',
  dept_id: null,
  email: '',
  phonenumber: '',
  status: '0',
  remark: '',
  role_ids: [],
})

const rules = {
  user_name: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  nick_name: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  password: [{ min: 6, message: '密码至少 6 位', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, {
    user_id: undefined,
    user_name: '',
    nick_name: '',
    password: '',
    dept_id: null,
    email: '',
    phonenumber: '',
    status: '0',
    remark: '',
    role_ids: [],
  })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const user = row as UserRow
  Object.assign(form, {
    user_id: user.user_id,
    user_name: user.user_name,
    nick_name: user.nick_name,
    password: undefined,
    dept_id: user.dept_id,
    email: '',
    phonenumber: '',
    status: user.status,
    remark: '',
    role_ids: [],
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
    if (form.user_id) {
      await updateUser({ ...form, user_id: form.user_id })
    } else {
      await createUser(form)
    }
    ElMessage.success(form.user_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

// ---------------------------------------------------------------------------
// 重置密码 / 状态 / 删除
// ---------------------------------------------------------------------------

async function handleResetPassword(row: unknown): Promise<void> {
  const user = row as UserRow
  let password: string | undefined
  try {
    const result = await ElMessageBox.prompt(`为「${user.nick_name}」设置新密码`, '重置密码', {
      inputType: 'password',
      inputValidator: (value: string) => (value && value.length >= 6) || '密码至少 6 位',
    })
    password = result.value
  } catch {
    return
  }
  await resetUserPassword(user.user_id, password)
  ElMessage.success('密码已重置')
}

async function toggleStatus(row: unknown): Promise<void> {
  const user = row as UserRow
  const next = user.status === '0' ? '1' : '0'
  try {
    await changeUserStatus(user.user_id, next)
    user.status = next
    ElMessage.success(next === '0' ? '已启用' : '已停用')
  } catch {
    // 停用自己会被后端拒绝（自锁保护）；重新拉取以显示真实状态。
    await fetchList()
  }
}

async function handleDelete(row?: unknown): Promise<void> {
  const target = row as UserRow | undefined
  const targets = target ? [target] : selection.value
  if (targets.length === 0) {
    return
  }
  const label = target ? `用户「${target.nick_name}」` : `选中的 ${targets.length} 个用户`
  try {
    await ElMessageBox.confirm(`确认删除${label}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteUsers(targets.map((item) => item.user_id))
    ElMessage.success('删除成功')
    await fetchList()
  } catch {
    // 「不能删除自己的账号」/「系统必须保留至少一个超级管理员」由后端给出。
  }
}

onMounted(async () => {
  // 辅助数据（部门树、角色列表）**不是**主列表的前置条件：只有 `system:user:list` 的账号拿不到
  // `system:dept:list` / `system:role:list`，那是正常情况而不是错误。
  //
  // 这里原本用 `Promise.all([...])` 再 `fetchList()`，后果是任何一个辅助请求 403 都会让整段
  // onMounted 抛错、主列表请求根本发不出去 —— 页面于是宣称「当前账号可见 0 个用户」，
  // 而这是假话。是浏览器验收发现的，单元测试与类型检查都抓不到这类顺序缺陷。
  if (hasPermission(userStore.perms, ['system:dept:list'])) {
    deptTree.value = await deptTreeSelect().catch(() => [])
  }
  if (hasPermission(userStore.perms, ['system:role:list'])) {
    roleOptions.value = await listRoles({ page_num: 1, page_size: 100 })
      .then((data) => data.rows)
      .catch(() => [])
  }
  await fetchList()
})
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" :model="query" class="search-bar">
      <el-form-item label="用户名">
        <el-input v-model="query.user_name" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:user:add']" type="primary" @click="openCreate">新增</el-button>
      <el-button
        v-hasPerm="['system:user:remove']"
        type="danger"
        :disabled="selection.length === 0"
        @click="handleDelete()"
      >
        删除
      </el-button>
    </el-row>

    <el-table v-loading="loading" :data="rows" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="user_name" label="登录名" min-width="130" />
      <el-table-column prop="nick_name" label="昵称" min-width="130" />
      <el-table-column label="所属部门" min-width="140">
        <template #default="{ row }">{{ deptLabel(row.dept_id) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.status === '0'" @change="toggleStatus(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:user:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:user:edit']" link type="primary" @click="handleResetPassword(row)">
            重置密码
          </el-button>
          <el-button v-hasPerm="['system:user:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
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
    <!-- total 也是按数据范围算的：换成权限更小的账号，这个数字会跟着变小 -->
    <div class="count-hint">当前账号可见 {{ total }} 个用户（总数随角色的数据范围变化）</div>

    <el-dialog v-model="dialogVisible" :title="form.user_id ? '修改用户' : '新增用户'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="登录名" prop="user_name">
          <el-input v-model="form.user_name" />
        </el-form-item>
        <el-form-item label="昵称" prop="nick_name">
          <el-input v-model="form.nick_name" />
        </el-form-item>
        <el-form-item v-if="!form.user_id" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-tree-select
            v-model="form.dept_id"
            :data="deptTree"
            check-strictly
            clearable
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_ids" multiple placeholder="不选则没有任何权限" style="width: 100%">
            <el-option v-for="role in roleOptions" :key="role.role_id" :label="role.role_name" :value="role.role_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phonenumber" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="0">正常</el-radio>
            <el-radio value="1">停用</el-radio>
          </el-radio-group>
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
</style>
