<script setup lang="ts">
/**
 * 菜单管理 —— 三种节点类型共处一棵树。
 *
 * `sys_menu` 用一张表装三种东西（M 目录 / C 菜单 / F 按钮），它们的必填项不一样：
 * 目录**不能**有组件（它只渲染子菜单）、菜单**必须**有组件（否则动态路由注册不出页面）、
 * 按钮**必须**有权限码（没有权限码的按钮对权限系统是不可见的）。
 *
 * 表单因此随类型切换字段，让约束在填写时就可见；真正的校验仍在后端 —— 前端的必填提示
 * 是为了少一次往返，不是为了替代后端。
 *
 * 菜单**没有逻辑删除**：删掉就是真的删掉，否则它的 `perms` 会残留在所有曾持有它的角色权限集里。
 * 所以删除前要确认，且后端会拒绝删除仍有子节点的菜单。
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createMenu, deleteMenu, listMenus, menuTreeSelect, updateMenu } from '@/api/system/menu'
import type { MenuItem, TreeSelectNode } from '@/types/api/system'

const loading = ref(false)
const rows = ref<MenuItem[]>([])
const total = ref(0)
const searchName = ref('')
const tree = ref<TreeSelectNode[]>([])

const TYPE_LABELS: Record<string, string> = { M: '目录', C: '菜单', F: '按钮' }
const TYPE_TAGS: Record<string, 'primary' | 'success' | 'info'> = { M: 'info', C: 'primary', F: 'success' }

async function fetchList(): Promise<void> {
  loading.value = true
  try {
    const data = await listMenus({ menu_name: searchName.value })
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
  tree.value = await menuTreeSelect()
}

// ---------------------------------------------------------------------------
// 表单
// ---------------------------------------------------------------------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref()
const form = reactive<Partial<MenuItem>>({
  parent_id: 0,
  menu_name: '',
  menu_type: 'C',
  path: '',
  component: '',
  route_name: '',
  perms: '',
  icon: '',
  order_num: 1,
  visible: '0',
  status: '0',
})

const isButton = computed(() => form.menu_type === 'F')
const needsComponent = computed(() => form.menu_type === 'C')

const rules = computed(() => ({
  menu_name: [{ required: true, message: '请输入菜单名称', trigger: 'blur' }],
  perms: isButton.value ? [{ required: true, message: '按钮必须填写权限标识', trigger: 'blur' }] : [],
  component: needsComponent.value ? [{ required: true, message: '菜单必须填写组件路径', trigger: 'blur' }] : [],
}))

function openCreate(row?: unknown): void {
  const parent = row as MenuItem | undefined
  Object.assign(form, {
    menu_id: undefined,
    parent_id: parent?.menu_id ?? 0,
    menu_name: '',
    menu_type: parent?.menu_type === 'C' ? 'F' : 'C',
    path: '',
    component: '',
    route_name: '',
    perms: '',
    icon: '',
    order_num: 1,
    visible: '0',
    status: '0',
  })
  dialogVisible.value = true
}

function openEdit(row: unknown): void {
  const menu = row as MenuItem
  Object.assign(form, {
    menu_id: menu.menu_id,
    parent_id: menu.parent_id,
    menu_name: menu.menu_name,
    menu_type: menu.menu_type,
    path: menu.path ?? '',
    component: menu.component ?? '',
    route_name: menu.route_name ?? '',
    perms: menu.perms ?? '',
    icon: menu.icon ?? '',
    order_num: menu.order_num,
    visible: menu.visible,
    status: menu.status,
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  // 按类型清掉不该存在的字段，避免把「目录带着组件」这种自相矛盾的数据发出去。
  const payload: Partial<MenuItem> = { ...form }
  if (isButton.value) {
    payload.path = null
    payload.component = null
  }

  submitting.value = true
  try {
    if (form.menu_id) {
      await updateMenu(payload)
    } else {
      await createMenu(payload)
    }
    ElMessage.success(form.menu_id ? '修改成功' : '新增成功')
    dialogVisible.value = false
    await Promise.all([fetchList(), refreshTree()])
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: unknown): Promise<void> {
  const menu = row as MenuItem
  try {
    await ElMessageBox.confirm(
      `确认删除「${menu.menu_name}」？菜单是物理删除，且删除后所有角色都不再拥有它的权限。`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteMenu(menu.menu_id)
    ElMessage.success('删除成功')
    await Promise.all([fetchList(), refreshTree()])
  } catch {
    // 「存在子菜单，不允许删除」由后端给出。
  }
}

onMounted(async () => {
  await Promise.all([fetchList(), refreshTree()])
})
</script>

<template>
  <div class="app-container">
    <el-form :inline="true" class="search-bar">
      <el-form-item label="菜单名称">
        <el-input v-model="searchName" placeholder="模糊匹配" clearable @keyup.enter="fetchList" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchList">搜索</el-button>
      </el-form-item>
    </el-form>

    <el-row class="toolbar" :gutter="8">
      <el-button v-hasPerm="['system:menu:add']" type="primary" @click="openCreate()">新增</el-button>
    </el-row>

    <el-table
      v-loading="loading"
      :data="rows"
      row-key="menu_id"
      :tree-props="{ children: 'children' }"
      default-expand-all
      border
    >
      <el-table-column prop="menu_name" label="菜单名称" min-width="180" />
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="TYPE_TAGS[row.menu_type]">{{ TYPE_LABELS[row.menu_type] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="order_num" label="排序" width="70" align="center" />
      <el-table-column prop="path" label="路由地址" min-width="110" />
      <el-table-column prop="component" label="组件路径" min-width="170" />
      <el-table-column prop="perms" label="权限标识" min-width="150" />
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '0' ? 'success' : 'info'">{{ row.status === '0' ? '正常' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['system:menu:add']" link type="primary" @click="openCreate(row)">新增下级</el-button>
          <el-button v-hasPerm="['system:menu:edit']" link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button v-hasPerm="['system:menu:remove']" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="count-hint">共 {{ total }} 个节点（含按钮，树形展示不分页）</div>

    <el-dialog v-model="dialogVisible" :title="form.menu_id ? '修改菜单' : '新增菜单'" width="580px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="上级菜单">
          <el-tree-select
            v-model="form.parent_id"
            :data="tree"
            check-strictly
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            placeholder="不选则为顶级"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="节点类型">
          <el-radio-group v-model="form.menu_type">
            <el-radio value="M">目录</el-radio>
            <el-radio value="C">菜单</el-radio>
            <el-radio value="F">按钮</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="菜单名称" prop="menu_name">
          <el-input v-model="form.menu_name" />
        </el-form-item>
        <el-form-item v-if="!isButton" label="路由地址">
          <el-input v-model="form.path" placeholder="如 /system 或 user" />
        </el-form-item>
        <el-form-item v-if="needsComponent" label="组件路径" prop="component">
          <el-input v-model="form.component" placeholder="如 system/user/index（对应 views/ 下的文件）" />
        </el-form-item>
        <el-form-item v-if="needsComponent" label="路由名称">
          <el-input v-model="form.route_name" placeholder="全局唯一，如 SystemUser" />
        </el-form-item>
        <el-form-item v-if="isButton" label="权限标识" prop="perms">
          <el-input v-model="form.perms" placeholder="如 system:user:add" />
        </el-form-item>
        <el-form-item v-else label="权限标识">
          <el-input v-model="form.perms" placeholder="菜单可不填；填了会作为该页面的权限码" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="Element Plus 图标名，如 User" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.order_num" :min="0" />
        </el-form-item>
        <el-form-item v-if="!isButton" label="显示状态">
          <el-radio-group v-model="form.visible">
            <el-radio value="0">显示</el-radio>
            <el-radio value="1">隐藏</el-radio>
          </el-radio-group>
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
.count-hint {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
