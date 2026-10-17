# enterprise-admin P1-A（数据权限 + 组织与权限 CRUD）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通「角色 → 部门范围 → 行级可见性」的数据权限闭环，并把部门/岗位/菜单/角色/用户五个模块的前后端 CRUD 做到可用，使规格定义的成功标准 S2 成为可现场演示的事实。

**Architecture:** 数据权限是**查询构造期**的注入，不是查询后的过滤：每个受控列表把 `apply_data_scope(stmt, entity, scope)` 包一层，由它按角色的 `data_scope` 追加 `WHERE`，业务代码不出现任何 `if is_admin` 分支。「本部门及以下」用 MySQL 8 递归 CTE 在库内求解子树。CRUD 走既有的 `api → services → models` 分层，唯一性校验集中在 service 层（这是 P0 遗留的、设计文档已承诺但未实现的缺口）。

**Tech Stack:** 与 P0 相同（FastAPI 0.143 / SQLAlchemy 2.1 async / asyncmy / MySQL 8.0.29 / Vue 3.5 / Element Plus 2.14 / Pinia 4）。

**Spec:** `docs/superpowers/specs/2026-10-17-enterprise-admin-design.md`（§5 数据模型、§6.4 数据权限、§8.3 接口清单）

**前置：** P0 已交付且通过评审（见 `docs/P0验收记录.md`）。本计划**不修改** P0 已验收的行为，只新增。

## Global Constraints

- **分页契约**：入参 `page_num`（默认 1）、`page_size`（默认 10，上限 100）；出参 `{"rows": [], "total": 0}`。每个列表接口都必须消费 `PageParams` —— P0 的 `PageParams` 目前是死代码，本计划的任务 7 会用 HTTP 层测试把它从「模型层已证明」变成「接口层已证明」。
- **统一响应**：`{"code", "msg", "data"}`；HTTP 状态码语义化；列表一律走 `page()`。
- **逻辑删除**：`del_flag`（`0` 存在 / `2` 删除）；由 `app/db/soft_delete.py` 的全局监听器自动过滤，业务代码不写 `WHERE del_flag='0'`。删除一律软删。
- **唯一性**：`user_name` / `role_key` / `post_code` / `dept_name`（同级）**不建数据库唯一索引**，唯一性由 service 层在事务内校验（P1 必须补上，见任务 4/5/6）。
- **权限**：每个写接口用 `Depends(require_perm("<module>:<entity>:<action>"))`；权限码沿用种子数据已有的命名（`system:user:add` 等），新增的按同规则命名并同步种子数据。
- **数据权限**：`data_scope` ∈ {1 全部, 2 自定义部门, 3 本部门, 4 本部门及以下, 5 仅本人}；多角色取**最宽松**者。管理员（`role_key='admin'`）不受限。
- **审计**：所有写操作记录操作日志（任务 8 引入装饰器后统一接入）。
- **前端**：TypeScript 严格模式；`vue-tsc`、oxlint、eslint 必须零错误；页面组件命名沿用 `views/<module>/<entity>/index.vue`（后端下发的组件字符串依赖这个约定）。
- **验证纪律**：每个任务的测试必须先看到失败；任务收尾前 `pytest` 与 `vitest` 全绿；**验收一律在干净工作区上进行**（P0 曾因 `git add` 漏文件导致 HEAD 跑不过自己的测试）。

## Review Focus

以下 5 类是本计划新增代码最可能伤到使用者的地方，按可能性排序。每条都已指定归属任务。

1. **越权可见（数据权限失效）**：用户能在列表里看到本部门之外的记录 —— 这是整个 P1 最严重的失败模式。归属：任务 1（机制本身，五种模式逐一断言）、任务 7（HTTP 层端到端断言）。
2. **层级结构被破坏**：删除有子节点或仍有用户的部门、删除有子菜单的菜单、把部门挂到自己的后代下（形成环）—— 都会让树查询或递归 CTE 无限循环或永久丢数据。归属：任务 2（部门）、任务 4（菜单）、任务 6（用户与部门引用）。
3. **唯一性校验缺失导致的脏数据**：新增同名用户/角色/岗位后，登录查询与角色解析会静默取第一条。这正是 P0 评审留下的遗留项 1。归属：任务 4、5、6。
4. **分页与查询参数边界**：`page_size=0/-1/100000`、`page_num` 超范围或非数字、`dept_id` 非数字 —— 必须是规范化或 422，不能 500；且要在**接口层**证明（P0 只在模型层证明过）。归属：任务 7。
5. **删除/停用后的残留权限**：停用角色后其菜单与数据范围应立即失效；删除角色后其与用户的关联行不应留下悬挂引用。归属：任务 5，并在任务 7 用 HTTP 断言复核。

---

## 文件结构

```
backend/app/
├─ core/
│  ├─ constants.py            (修改) 补 DataScopeEnum 用法、审计业务类型
│  └─ deps.py                 (修改) CurrentUser 增加 data_scope: DataScope
├─ services/
│  ├─ data_scope.py           (新增) DataScope 解析 + apply_data_scope + 递归 CTE
│  ├─ dept_service.py         (新增) 部门树、ancestors 维护、删除守卫
│  ├─ post_service.py         (新增) 岗位 CRUD
│  ├─ menu_service.py         (修改) 补树形 CRUD 与 treeselect、roleMenuTreeselect
│  ├─ role_service.py         (新增) 角色 CRUD、菜单授权、数据范围、用户授权
│  ├─ user_service.py         (新增) 用户 CRUD、密码重置、角色授权、唯一性校验
│  └─ oper_log_service.py     (新增) 操作日志装饰器与落库
├─ schemas/
│  ├─ system.py               (新增) 五个模块的出入参
│  └─ common.py               (修改) 补 IdsRequest 等
└─ api/v1/
   ├─ system/__init__.py      (新增)
   ├─ system/dept.py          (新增)
   ├─ system/post.py          (新增)
   ├─ system/menu.py          (新增)
   ├─ system/role.py          (新增)
   ├─ system/user.py          (新增)
   └─ router.py               (修改) 挂载 system 路由

frontend/src/
├─ components/                (新增) ProTable / ProForm / Pagination / RightToolbar / TreeSelect / DictTag
├─ api/system/{dept,post,menu,role,user}.ts   (新增)
├─ types/api/system.ts        (新增)
└─ views/system/{dept,post,menu,role,user}/index.vue  (新增)

backend/tests/
├─ test_data_scope.py         (新增)
├─ test_dept.py test_post.py test_menu_crud.py test_role.py test_user.py  (新增)
└─ test_pagination_http.py    (新增) 补齐 P0 的接口层分页边界
```

---

### Task 1: 数据权限机制

**Files:**
- Create: `backend/app/services/data_scope.py`
- Modify: `backend/app/core/deps.py`（`CurrentUser` 增加 `data_scope`）
- Test: `backend/tests/test_data_scope.py`

**Interfaces:**
- Consumes: `app/core/constants.py::DataScopeEnum`、`app/models/associations.py::SysRoleDept`、`app/models/dept.py::SysDept`、`CurrentUser`
- Produces:
  - `@dataclass(frozen=True) class DataScope`：`mode: int`、`dept_id: int | None`、`user_id: int`、`custom_dept_ids: frozenset[int]`
  - `def resolve_data_scope(roles: Sequence[SysRole], *, user_id: int, dept_id: int | None, is_admin: bool) -> DataScope` —— 多角色取最宽松（`mode` 最小者胜出；`CUSTOM` 的部门集合取并集）
  - `async def dept_subtree_ids(db: AsyncSession, root_dept_id: int) -> set[int]` —— 递归 CTE
  - `def apply_data_scope(stmt, entity, scope: DataScope, *, dept_field: str = "dept_id", user_field: str = "user_id") -> Select` —— 返回追加了 `WHERE` 的语句；`ALL` 模式原样返回
  - `CurrentUser.data_scope: DataScope`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_data_scope.py`，纯函数部分与数据库部分分开：

```python
def test_admin_scope_is_all()                                    # is_admin=True 时 mode == ALL
def test_single_role_scope_is_its_own()                          # data_scope=3 → mode == DEPT
def test_most_permissive_role_wins()                             # 角色 {5, 3} → DEPT（3 更宽松）
def test_custom_scope_unions_dept_ids()                          # 两个 CUSTOM 角色 → 部门集合并集
def test_scope_without_dept_falls_back_to_self()                 # data_scope=3 但 dept_id 为 None → SELF

async def test_dept_subtree_includes_descendants(db_session) ...  # 三层树取中间节点 → 含其子、不含其父
async def test_dept_subtree_of_leaf_is_itself(db_session) ...
async def test_dept_subtree_ignores_soft_deleted_depts(db_session) ...  # 已删部门从子树中消失

async def test_apply_data_scope_all_does_not_filter(db_session) ...      # ALL → 行数不变
async def test_apply_data_scope_dept_filters(db_session) ...             # DEPT → 只有本部门行
async def test_apply_data_scope_dept_and_child_filters(db_session) ...   # DEPT_AND_CHILD → 含子树
async def test_apply_data_scope_self_filters(db_session) ...             # SELF → 只有自己的行
async def test_apply_data_scope_custom_filters(db_session) ...           # CUSTOM → 只有指定部门
```

测试需要一个「带 `dept_id`/`user_id` 的实体」来施加范围。**不要为此新建业务表**：用一个映射到既有 `sys_user` 的轻量断言（`apply_data_scope` 接受任意带 `dept_id` 字段的实体），配合 `db_session` 里插入的几个用户即可。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_data_scope.py -q`
Expected: FAIL（`app.services.data_scope` 不存在）

- [ ] **Step 3: 实现 `data_scope.py`**

要点：
- 递归 CTE 用 `sqlalchemy.select(...).cte(recursive=True)`，锚点为 `SysDept.dept_id == root_dept_id`，递归项 join `parent_id == cte.dept_id`；`SysDept` 的软删除过滤由全局监听器自动生效（不要手写 `del_flag`）。
- `apply_data_scope` 只处理 `DEPT`/`DEPT_AND_CHILD`/`SELF`/`CUSTOM` 四种，`ALL` 直接返回原语句；`DEPT_AND_CHILD` 需要 `await`（子树查询），所以签名是 `async def`。
- 多角色「最宽松」的判据是 `DataScopeEnum` 的**数值最小**（1 最宽松）；这一点必须写进 docstring，否则后人会以为越大越宽松。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_data_scope.py -q`
Expected: 全 PASS

- [ ] **Step 5: 把 `data_scope` 接进 `CurrentUser`**

在 `deps.get_current_user` 里，用已经查出的 `user.roles` 调 `resolve_data_scope(...)`。注意 `SysUser.roles` 是 `selectin` 加载的，`SysRole.depts`（自定义范围）也是 —— 无需额外查询。

新增测试：`tests/test_authz.py::test_profile_department_manager_reports_scope`（断言 4 号角色的 `data_scope.mode == 4`）。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(backend): add data-scope resolution and query-time row filtering"
```

---

### Task 2: 部门 CRUD

**Files:**
- Create: `backend/app/services/dept_service.py`、`backend/app/api/v1/system/dept.py`
- Modify: `backend/app/schemas/system.py`、`backend/app/api/v1/router.py`
- Test: `backend/tests/test_dept.py`

**Interfaces:**
- Consumes: `PageParams`、`success/page`、`require_perm`、`SysDept`
- Produces（路由，全部挂 `/api/v1/system/dept`）：
  - `GET ""` → `page(rows, total)`，行内含 `children`（树形返回）
  - `GET "/{dept_id}"`、`POST ""`、`PUT ""`、`DELETE "/{dept_id}"`
  - `GET "/treeselect"` → `success([{id, label, children}])`（给 TreeSelect 用）
  - 权限码：`system:dept:list` / `:query` / `:add` / `:edit` / `:remove`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_dept.py`：

```python
async def test_create_dept_computes_ancestors(client, admin_token) ...
async def test_create_child_dept_appends_to_ancestors(client, admin_token) ...
async def test_rename_dept_updates_descendant_ancestors(client, admin_token) ...  # 关键：改父名要重写子树路径
async def test_move_dept_rejects_moving_into_its_own_descendant(client, admin_token) ...  # Review Focus #2
async def test_delete_dept_with_children_is_rejected(client, admin_token) ...
async def test_delete_dept_with_users_is_rejected(client, admin_token) ...
async def test_delete_dept_is_soft(client, admin_token, db_session) ...   # del_flag == '2'
async def test_duplicate_sibling_name_is_rejected(client, admin_token) ...
async def test_list_returns_a_tree(client, admin_token) ...
async def test_treeselect_shape(client, admin_token) ...
async def test_dept_write_requires_permission(client, normal_user_token) ...   # 403
async def test_dept_list_is_filtered_by_data_scope(client, scoped_tokens) ...  # 与任务 1 联动
```

- [ ] **Step 2: 运行测试确认失败** → FAIL（路由 404）

- [ ] **Step 3: 实现 service 与路由**

要点：`ancestors` 是物化路径（`"0,100,101"`）。**移动或重命名父节点时必须重写整棵子树的 `ancestors`**，否则「本部门及以下」的递归 CTE 与基于 `ancestors` 的快速判断会长期给出错误答案 —— 这是本任务最容易做漏的一步，测试里单独有一条。

删除守卫：有子部门 → 400；有用户引用（`SysUser.dept_id`）→ 400。

- [ ] **Step 4: 运行测试确认通过** → 全 PASS
- [ ] **Step 5: Commit**（`feat(backend): add department CRUD with tree path maintenance`）

---

### Task 3: 岗位 CRUD

**Files:** Create `backend/app/services/post_service.py`、`backend/app/api/v1/system/post.py`；Modify schemas/router；Test `backend/tests/test_post.py`

**Interfaces:** `GET ""`（分页）、`GET "/{post_id}"`、`POST ""`、`PUT ""`、`DELETE "/{ids}"`（逗号分隔批量）、`GET "/optionselect"`；权限码 `system:post:*`。

- [ ] **Step 1: 写失败的测试**：分页形状、`post_code` 重复被拒（Review Focus #3）、批量删除、`optionselect` 形状、无权限 403、**停用岗位不出现在 `optionselect`**
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**（唯一性校验放在 service 内的事务里；批量删除逐条软删）
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 4: 菜单 CRUD

**Files:** Modify `backend/app/services/menu_service.py`、新建 `backend/app/api/v1/system/menu.py`；Test `backend/tests/test_menu_crud.py`

**Interfaces:** `GET "/list"`（树）、`GET "/{menu_id}"`、`POST ""`、`PUT ""`、`DELETE "/{menu_id}"`、`GET "/treeselect"`、`GET "/roleMenuTreeselect/{role_id}"`；权限码 `system:menu:*`。

- [ ] **Step 1: 写失败的测试**：新增按钮节点（`menu_type='F'` 且 `perms` 必填）、新增菜单节点（`component` 必填且必须是 `a/b/index` 形状）、`route_name` 重复被拒、**有子菜单时删除被拒**（Review Focus #2）、删除菜单后该权限码从所有角色消失、`roleMenuTreeselect` 返回 `{menus, checkedKeys}`、`perms` 为空字符串的按钮被拒
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**：注意菜单**没有 `del_flag`**（P0 的裁定：残留的 `perms` 比不可逆删除更糟），因此删除是物理删除，且必须先删 `sys_role_menu` 关联行 —— 外键是 `ON DELETE CASCADE`，但显式删除更清楚
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 5: 角色 CRUD、菜单授权与数据范围

**Files:** Create `backend/app/services/role_service.py`、`backend/app/api/v1/system/role.py`；Test `backend/tests/test_role.py`

**Interfaces:** `GET ""`（分页）、`GET "/{role_id}"`、`POST ""`、`PUT ""`、`DELETE "/{ids}"`、`PUT "/changeStatus"`、`PUT "/dataScope"`、`GET "/authUser/allocatedList"`、`GET "/authUser/unallocatedList"`、`PUT "/authUser/selectAll"`、`PUT "/authUser/cancelAll"`、`PUT "/authUser/cancel"`；权限码 `system:role:*`。

- [ ] **Step 1: 写失败的测试**：`role_key` 重复被拒、**不允许删除或停用 `admin` 角色**（自锁保护）、`changeStatus` 后**该角色用户的 `/auth/routers` 立即少掉对应菜单**（Review Focus #5）、`dataScope` 写入 `sys_role_dept` 且旧关联被清空、角色删除时 `sys_user_role` / `sys_role_menu` / `sys_role_dept` 关联一并清理、用户授权增删
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 6: 用户 CRUD

**Files:** Create `backend/app/services/user_service.py`、`backend/app/api/v1/system/user.py`；Test `backend/tests/test_user.py`

**Interfaces:** `GET ""`（分页，**受数据权限约束**）、`GET "/{user_id}"`、`POST ""`、`PUT ""`、`DELETE "/{ids}"`、`PUT "/resetPwd"`、`PUT "/changeStatus"`、`GET "/authRole/{user_id}"`、`PUT "/authRole"`、`GET "/deptTree"`；权限码 `system:user:*`。

- [ ] **Step 1: 写失败的测试**：新建用户必经 bcrypt、新建时 `user_name` 重复被拒（含**与已逻辑删除的同名用户可共存**这条边界）、**不允许删除或停用自己**、**不允许删除或停用最后一个超管**、`resetPwd` 后旧密码失效、`changeStatus` 后该用户的在线令牌立即失效（P0 已支持，这里复核）、`authRole` 覆盖式授权、新建用户的密码不满足策略时 422
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 7: 把数据权限接进列表接口，并补齐接口层分页边界

**Files:** Modify `user_service`、`role_service`、`post_service`；Create `backend/tests/test_pagination_http.py`

**Interfaces:** 所有列表接口消费 `PageParams`；`GET /system/user` 与 `GET /system/role` 的结果受 `apply_data_scope` 约束。

- [ ] **Step 1: 写失败的测试**

`test_pagination_http.py`（补齐 P0 评审留下的 Review Focus #4 缺口 —— P0 只在模型层证明过）：

```python
async def test_page_size_zero_is_clamped_over_http(client, admin_token) ...
async def test_page_size_huge_is_clamped_over_http(client, admin_token) ...
async def test_page_num_non_numeric_is_422(client, admin_token) ...
async def test_page_size_non_numeric_is_422(client, admin_token) ...
async def test_out_of_range_page_num_returns_empty_rows_not_500(client, admin_token) ...
```

并在 `test_user.py` 补：`test_user_list_respects_dept_scope`、`test_user_list_admin_sees_everything`、`test_user_list_self_scope_sees_only_self` —— 三条都用同一个数据集、只换登录角色，断言**行数不同**（这就是 S2 的「可见数据行数不同」）。

- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**：`apply_data_scope` 在 service 的查询构造处调用；**不要**在 `api/` 层出现任何范围判断
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 8: 操作日志装饰器

**Files:** Create `backend/app/services/oper_log_service.py`、`backend/app/models/oper_log.py`、迁移 `0002_oper_log.py`；Test `backend/tests/test_oper_log.py`

**Interfaces:** `@oper_log(title: str, business_type: BusinessType)` 装饰器；`sys_oper_log` 表。

- [ ] **Step 1: 写失败的测试**：装饰的接口被调用后落一行、记录操作人/URL/方法/参数/耗时/状态、抛异常时记录 `status=1` 与 `error_msg`、**参数里的 `password` 字段必须被脱敏**（这是最容易被忽略的安全细节）
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**（中间件拿不到业务语义，所以用装饰器；这与 P0 的裁定一致）
- [ ] **Step 4: 确认通过** → 全 PASS
- [ ] **Step 5: Commit**

---

### Task 9: 前端通用组件

**Files:** Create `frontend/src/components/{ProTable,ProForm,Pagination,RightToolbar,TreeSelect,DictTag}/index.vue`、`frontend/src/types/api/system.ts`、`frontend/src/api/system/*.ts`

**Interfaces:** `ProTable` 接受 `columns` + `fetch` 函数，内部处理分页/加载态/刷新；`ProForm` 接受字段声明与校验规则；`TreeSelect` 对接后端 `treeselect` 形状（`{id, label, children}`）。

- [ ] **Step 1: 写失败的测试**：`ProTable` 在 `fetch` 返回空行时渲染空态且不报错、`Pagination` 把 `page_size` 变化回传、`TreeSelect` 能把扁平树扁平化后回显选中值
- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**：注意 P0 踩过的布局坑 —— 横向 flex 链必须补 `minWidth: 0`，否则长文本会把固定宽列撑破
- [ ] **Step 4: 确认通过** → `npx vitest run` 全 PASS 且 `npm run type-check` 通过
- [ ] **Step 5: Commit**

---

### Task 10: 前端 部门 / 岗位 / 菜单 页面

**Files:** Create `frontend/src/views/system/{dept,post,menu}/index.vue`

- [ ] **Step 1: 逐条定义验收标准**：列表可检索、新增/编辑弹窗校验生效、删除有二次确认、菜单页能按类型（目录/菜单/按钮）显示不同字段、**树形表格的父子层级正确**、按钮受 `v-hasPerm` 控制
- [ ] **Step 2: 实现**
- [ ] **Step 3: 逐条手工验证**（浏览器），确认无控制台错误
- [ ] **Step 4: Commit**

---

### Task 11: 前端 角色 / 用户 页面

**Files:** Create `frontend/src/views/system/{role,user}/index.vue`（含角色的数据范围弹窗、用户的角色授权弹窗）

- [ ] **Step 1: 逐条定义验收标准**：角色页能设置数据范围并选择自定义部门、用户页能分配角色、用户页能重置密码、列表按钮按权限码显隐、**用户列表能看出数据范围造成的行数差异**
- [ ] **Step 2: 实现**
- [ ] **Step 3: 逐条手工验证**（浏览器）
- [ ] **Step 4: Commit**

---

### Task 12: S2 验收与文档

**Files:** Create `docs/P1验收记录.md`；Modify `README.md`、`docs/数据库设计.md`、`docs/接口清单.md`

- [ ] **Step 1: 干净工作区全量验证**

Run: `git status --porcelain`（必须为空）→ 后端 `pytest` → 前端 `vitest run` + `type-check` + `lint` + `build` → `alembic check`（两个库）

- [ ] **Step 2: 跑 S2 并记录证据**

用 seed 的四个账号分别登录，记录：菜单项数、可见按钮数、同一列表的可见行数。预期：`admin` 全部；`manager` 只见本部门及以下的数据；`staff` 零菜单且列表权限受限。截图存入 `docs/images/`。

- [ ] **Step 3: 核对 Review Focus 五条是否都有测试**

逐条指出测试名；缺哪条回对应任务补。

- [ ] **Step 4: 更新文档**：README 的「已知取舍」去掉已实现的条目；数据库设计补 `sys_oper_log`；接口清单把 P1 落的接口从「未实现」移到「已实现」
- [ ] **Step 5: Commit**

---

## 计划自查

**1. Spec 覆盖**

| Spec 章节 | 覆盖任务 |
|---|---|
| §5.3 权限表（含 `sys_role_dept`） | 任务 1、5 |
| §5.4 平台表（字典/参数/公告） | **不在本计划**（P1-B） |
| §5.5 日志表 | 任务 8 |
| §6.1 接口级权限 | P0 已完成，本计划复用 |
| §6.2 菜单/路由级 | P0 已完成 |
| §6.3 按钮级 | 任务 10、11（页面接入） |
| §6.4 数据权限 | **任务 1、7（本计划的核心）** |
| §8.3 system/* 接口 | 任务 2–7 |
| §8.3 monitor/* 与 file/* | **不在本计划**（P1-B） |
| §13 P1 验收（S2） | 任务 12 |

**缺口说明**：字典、参数、公告、操作日志查询页、登录日志、在线用户、服务监控、文件管理属于 **P1-B**；本计划刻意只做到「S2 可演示」为止，因为一个计划应当自身即可交付可运行的软件。

**2. 步骤扫描**：每一步都是单一动作。任务 9–11 没有单元测试，改用可观察的验收清单（界面行为不适合断言式测试，也不该假装可以）。

**3. 类型一致性**：`DataScope`（`mode/dept_id/user_id/custom_dept_ids`）、`apply_data_scope(stmt, entity, scope, *, dept_field, user_field)`、`dept_subtree_ids(db, root)` 全计划同名同签名。

**4. Review Focus 覆盖**：五条均落到任务 1（机制）+ 2/4/5/6（结构守卫与唯一性）+ 7（接口层分页与行数差异）。

**5. 篇幅比例**：本计划以接口签名、测试名与断言为主，未逐行转写实现。
