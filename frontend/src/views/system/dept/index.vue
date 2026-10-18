<script setup lang="ts">
/**
 * 部门管理 —— 树形表格。
 *
 * 这一页演示的是**层级约束**，不是普通 CRUD：
 * - 部门是树，所以用 `row-key` + `tree-props` 渲染，并且不分页（被截断的树不是树）。
 * - 删除有下级或有用户的部门会被后端拒绝；这里把拒绝原因原样呈现，而不是自己先猜——
 *   前端猜一套规则、后端执行另一套，是这类页面最常见的漂移。
 * - 移动部门会重写整棵子树的 `ancestors`（后端保证），所以改完必须重新拉取整棵树。
 *
 * 行处理沿用既有约定：Element Plus 的表格插槽把行标成内部类型，因此消费行的函数收 `unknown`
 * 并在入口转型一次。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { createDept, deleteDept, deptTreeSelect, listDepts, updateDept } from '@/api/system/dept'
import type { Dept, DeptForm, TreeSelectNode } from '@/types/api/system'

const loading = ref(false)
const rows = ref<Dept[]>([])
const total = ref(0)
const searchName = ref('')

const tree = ref<TreeSelectNode[]>([])

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listDepts({ dept_name: searchName.value })
    rows.value = data.rows
    total.value = data.total
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function refreshTree(): Promise<void> {
  tree.value = await deptTreeSelect()
}

function handleSearch(): void {
  void fetchList()
}

function handleReset(): void {
  searchName.value = ''
  handleSearch()
}

// ---------------------------------------------------------------------------
// 新增 / 修改
// ---------------------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<DeptForm>({
  parent_id: 0,
  dept_name: '',
  order_num: 1,
  leader: '',
  phone: '',
  email: '',
  status: '0',
  remark: '',
})

const rules = {
  dept_name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
}

function openCreate(row?: unknown): void {
  const parent = row as Dept | undefined
  Object.assign(form, {
    dept_id: undefined,
    parent_id: parent?.dept_id ?? 0,
    dept_name: '',
    order_num: 1,
    leader: '',
    phone: '',
    email: '',
    status: '0',
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const dept = row as Dept
  Object.assign(form, {
    dept_id: dept.dept_id,
    parent_id: dept.parent_id,
    dept_name: dept.dept_name,
    order_num: dept.order_num,
    leader: dept.leader ?? '',
    phone: dept.phone ?? '',
    email: dept.email ?? '',
    status: dept.status,
    remark: dept.remark ?? '',
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
    if (form.dept_id) {
      await updateDept({ ...form, dept_id: form.dept_id })
    } else {
      await createDept(form)
    }
    ElMessage.success(form.dept_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    // 整棵树都要重拉：改名或移动会连带影响下级节点的展示。
    await Promise.all([fetchList(), refreshTree()])
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: unknown): Promise<void> {
  const dept = row as Dept
  try {
    await ElMessageBox.confirm(`确认删除部门「${dept.dept_name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDept(dept.dept_id)
    ElMessage.success('删除成功')
    await Promise.all([fetchList(), refreshTree()])
  } catch {
    // 后端会说明「存在下级部门」或「部门下存在用户」；拦截器已经提示过了。
  }
}

onMounted(async () => {
  await Promise.all([fetchList(), refreshTree()])
})
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" class="search-bar">
      <el-form-item label="部门名称">
        <el-input v-model="searchName" placeholder="模糊匹配" clearable @keyup.enter="handleSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:dept:add']" type="primary" @click="openCreate()">新增</el-button>
    </el-row>

    <el-table
      v-loading="loading"
      :data="rows"
      row-key="dept_id"
      :tree-props="{ children: 'children' }"
      default-expand-all
      border
    >
      <el-table-column prop="dept_name" label="部门名称" min-width="200" />
      <el-table-column prop="order_num" label="排序" width="80" align="center" />
      <el-table-column prop="leader" label="负责人" width="120" />
      <el-table-column prop="phone" label="联系电话" width="140" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'info'">
            {{ row.status === '0' ? '正常' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- ancestors 是物化路径：把它显示出来，层级维护是否正确的证据就在这一列 -->
      <el-table-column prop="ancestors" label="层级路径" min-width="140" />
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:dept:add']" link type="primary" @click="openCreate(row)">新增下级</el-button>
          <el-button v-hasPerm="['system:dept:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:dept:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="count-hint">共 {{ total }} 个部门（树形展示，不按分页切分）</div>

    <el-dialog v-model="dialogVisible" :title="form.dept_id ? '修改部门' : '新增部门'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="上级部门">
          <el-tree-select
            v-model="form.parent_id"
            :data="tree"
            check-strictly
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            placeholder="不选则为顶级部门"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="部门名称" prop="dept_name">
          <el-input v-model="form.dept_name" placeholder="同级下不可重名" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.order_num" :min="0" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="form.leader" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" />
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
.count-hint {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
