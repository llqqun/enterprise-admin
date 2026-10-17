# enterprise-admin 设计文档

- 文档日期：2026-10-17
- 状态：待用户评审
- 目标读者：项目所有者（刘群）、后续接手开发者

---

## 1. 背景与目标

### 1.1 背景

项目所有者是 8 年经验的前端工程师，求职方向为「AI 型全栈工程师 / 前端开发工程师」。需要一个**可现场演示、代码结构经得起追问**的企业级后台管理系统，作为作品集项目：候选人能在面试中打开浏览器实操，并逐层解释 RBAC、动态路由、数据权限等设计决策。

本机环境限制（见附录 A）：无 Docker、无 WSL、无独立 MySQL 实例，Python 3.12 与 Node 24 已就绪，磁盘需优先使用 D 盘。

### 1.2 目标

1. 交付一个**本机一条命令启动**的后台管理系统（MySQL + 后端 + 前端）。
2. 实现企业级后台的完整权限闭环：接口级、菜单/路由级、按钮级、数据级四层权限。
3. 后端提供符合 REST 规范、带交互式文档（Swagger）的 API。
4. 前端提供专业级交互：动态路由、多标签页、按钮级权限、自研业务组件。
5. 交付配套文档，特别是**面试讲解手册**——把技术点转成可讲述的内容。
6. 所有程序、数据、缓存均不落在 C 盘。

### 1.3 非目标（本期明确不做）

| 不做的事 | 原因 |
|---|---|
| 工作流引擎（审批流） | 需引入 Flowable/Activiti 或自研流程引擎，是独立子项目，列入 Roadmap |
| 代码生成器 / 低代码 | 工作量与本体相当，列入 Roadmap |
| 多租户 SaaS 隔离 | 会渗透进所有表的查询逻辑，与数据权限模型冲突，需独立设计 |
| 消息队列 / 定时任务调度 | 本机无中间件；引入后演示环境复杂度失控 |
| 生产级安全加固（HTTPS、密钥托管、等保合规） | 属部署阶段工作，仅在文档中列出清单，不谎称已具备 |

### 1.4 成功标准

| 编号 | 标准 | 验证方式 |
|---|---|---|
| S1 | 双击 `启动.ps1` 后，浏览器访问前端地址可登录进入后台 | 手动验证 |
| S2 | 创建「部门主管」与「普通员工」两个角色，分别登录后看到的菜单、按钮、数据行数均不同 | 手动 + 自动化测试 |
| S3 | `/docs` 可打开并直接调用接口完成一次完整的增删改查 | 手动验证 |
| S4 | 后端 pytest 全绿，前端 `vue-tsc` 与 ESLint 无错误 | 命令行验证 |
| S5 | 能对着文档复述任一权限层级的实现原理与取舍 | 面试演练 |
| S6 | 全程无文件写入 C 盘（除 pip/npm 显式重定向后的临时文件） | 路径审查 |

---

## 2. 约束与既定决策

### 2.1 用户已明确

- 前端：Vue3 + Element Plus + Vite + Pinia + Vue Router + **TypeScript**
- 后端：Python，提供 REST 接口
- 数据库：MySQL
- 用途：求职作品集 / 面试演示，本机一条命令跑起来
- 业务范围：通用企业后台底座（RBAC 为核心）+ 示例业务模块
- 程序尽量不装 C 盘
- 后端需要 pytest 自动化测试

### 2.2 数据库落地决策

**决策**：使用 MySQL 8.0.29 便携版 ZIP，解压至 `D:\devtools\mysql-8.0.29\`，数据目录 `D:\devtools\mysql-data\`。

**理由**：
- 本机无 Docker、无 WSL，无法用容器方案；
- MySQL 官方 MSI 安装器默认写 C 盘且注册系统服务，违背「不装 C 盘」约束；
- 便携版 ZIP 无需安装、无需管理员权限，删除目录即可完全卸载；
- 8.0.29 是国内镜像（华为云）可得的最新便携版本，满足全部功能需求（utf8mb4、JSON、CTE、窗口函数、角色、**递归 CTE**——后者是实现「本部门及以下」数据权限的关键）。

**已否决的备选**：

| 方案 | 否决理由 |
|---|---|
| MariaDB 便携版 | 与 MySQL 存在行为差异，面试口径上不是 MySQL |
| SQLite | 与需求不符，JSON 字段、字符集、并发行为差异大 |
| MySQL MSI 安装器 | 强制 C 盘 + 注册系统服务 |
| Docker 容器 | 本机无 Docker |

**运行方式**：默认**不注册 Windows 服务**（服务注册会写入 C 盘注册表与 `C:\ProgramData`），由启动脚本按需拉起 `mysqld` 进程。另附可选的 `安装MySQL服务.ps1`，供以后需要开机自启时使用。

**遗留风险**：8.0.29 发布于 2022 年，非当前 LTS。`deploy/docker-compose.yml` 提供 MySQL 8.4 LTS 备选，便于在有容器环境时切换。

### 2.3 依赖版本策略

本机 Node 24 与 2026 年的前端生态版本较新（Vite 8 / Pinia 4 / Vue Router 5 / TypeScript 7）。**不凭记忆手写配置**，而采用：

1. 用官方脚手架 `create-vue@latest` 生成 TypeScript + Router + Pinia + ESLint + Prettier 基线（版本组合由生态自身保证兼容）；
2. 在基线之上叠加 Element Plus 与项目代码；
3. 后端同理：先用 pip 解析出一套可安装的版本组合，写入 `requirements.txt` 并锁定，再开发。

**原则**：任何版本组合都必须经「实际启动 + 实际调用」验证，不接受「理论上兼容」。

### 2.4 缓存决策

**不引入 Redis**。设计 `CacheBackend` 抽象接口 + `MemoryCache`（TTL 实现）。

- 用途：图形验证码、登录失败计数、字典缓存、在线用户辅助计数
- 切换成本：新增 `RedisCache` 实现类 + 改一行配置
- 面试价值：能解释「为什么不在单体演示项目里上来就引 Redis」（部署复杂度 vs 收益），以及为什么仍要留抽象层

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  浏览器                                                        │
│  Vue3 + TS + Element Plus SPA                                │
│  ├─ 路由守卫：token 校验 → 拉取用户信息 → 注入动态路由           │
│  ├─ Pinia：user / permission / tagsView / app / dict         │
│  └─ axios 封装：令牌注入、防重提交、401 自动刷新、错误统一处理      │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / JSON (Vite dev proxy)
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI (uvicorn)                                          │
│  ├─ 中间件：RequestId → CORS → 访问日志                        │
│  ├─ 操作日志：@oper_log 装饰器（中间件拿不到业务语义，故不用中间件） │
│  ├─ 认证层：JWT 解析 → 用户上下文（user_id / dept_id / perms）   │
│  ├─ 鉴权层：require_perm 依赖 → 接口级权限                       │
│  ├─ 业务层：service（数据权限注入、树构建、业务规则）               │
│  ├─ 数据层：SQLAlchemy 2.0 async + asyncmy                    │
│  └─ 异常层：业务异常体系 + 全局处理器 → 统一响应 {code,msg,data}   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  MySQL 8.0.29（便携版，D 盘）    CacheBackend（Memory 实现）      │
└─────────────────────────────────────────────────────────────┘
```

**分层规则**（强制，用于 code review）：

| 层 | 职责 | 禁止 |
|---|---|---|
| `api/` | 参数解析、权限声明、调用 service、组装响应 | 写 SQL、写业务规则 |
| `services/` | 业务逻辑、事务边界、数据权限注入 | 依赖 FastAPI 的 Request/Response |
| `models/` | ORM 映射、关系定义 | 业务判断 |
| `schemas/` | 入参校验、出参序列化 | 访问数据库 |
| `core/` | 配置、安全、缓存、异常、依赖 | 依赖具体业务模块 |

---

## 4. 目录结构

```
D:\work\enterprise-admin\
├─ backend\
│  ├─ app\
│  │  ├─ main.py                 # 应用装配、生命周期、路由挂载
│  │  ├─ core\
│  │  │  ├─ config.py            # Pydantic Settings，读 .env
│  │  │  ├─ security.py          # JWT 签发/校验、bcrypt、验证码生成
│  │  │  ├─ cache.py             # CacheBackend 抽象 + MemoryCache
│  │  │  ├─ exceptions.py        # BusinessException 及子类
│  │  │  ├─ response.py          # 统一响应封装、分页模型
│  │  │  ├─ constants.py         # 枚举：状态、菜单类型、数据范围、业务类型
│  │  │  └─ deps.py              # get_current_user、require_perm、数据权限上下文
│  │  ├─ models\                 # 按域拆分：user.py dept.py role.py menu.py ...
│  │  ├─ schemas\                # 与 models 同构拆分
│  │  ├─ services\               # auth_service user_service role_service ...
│  │  ├─ api\v1\
│  │  │  ├─ auth.py  system\  monitor\  file.py
│  │  ├─ middlewares\            # request_id.py  access_log.py  oper_log.py
│  │  └─ utils\                  # 树构建、IP 归属、浏览器解析、Excel 导出
│  ├─ alembic\                   # 迁移（异步 env.py）
│  ├─ scripts\                   # init_db.py  seed_data.py  reset_db.py
│  ├─ tests\                     # conftest.py  test_auth.py  test_rbac.py ...
│  ├─ requirements.txt
│  └─ .env / .env.example
├─ frontend\
│  ├─ src\
│  │  ├─ api\                    # 按模块封装的请求函数
│  │  ├─ components\             # ProTable / ProForm / DictTag / Pagination ...
│  │  ├─ directives\             # hasPerm.ts  hasRole.ts
│  │  ├─ layout\                 # index.vue  Sidebar  Navbar  TagsView  AppMain
│  │  ├─ router\                 # index.ts  routes.ts  guard.ts
│  │  ├─ stores\                 # user.ts  permission.ts  tagsView.ts  app.ts  dict.ts
│  │  ├─ styles\                 # 变量、混入、暗色主题
│  │  ├─ types\                  # API 类型、模型类型
│  │  ├─ utils\                  # request.ts  auth.ts  permission.ts  dict.ts
│  │  └─ views\                  # login dashboard system\ monitor\ profile error\
│  └─ vite.config.ts
├─ deploy\
│  ├─ mysql\my.ini.template
│  ├─ docker-compose.yml         # 备选（MySQL 8.4 LTS）
│  └─ nginx.conf                 # 备选（生产部署参考）
├─ tools\
│  ├─ download-mysql.ps1
│  ├─ install-mysql.ps1          # 解压 + 初始化 + 生成 my.ini
│  └─ mysql-ctl.ps1              # start / stop / status
├─ docs\
│  ├─ 架构设计.md
│  ├─ 数据库设计.md
│  ├─ 接口清单.md
│  ├─ 面试讲解手册.md
│  └─ superpowers\specs\         # 本设计文档
├─ init.ps1                       # 一次性：.env + 建库 + 迁移 + 种子数据
├─ start.ps1                      # MySQL + 后端 + 前端
├─ stop.ps1                       # 停止（-IncludeMysql 连库一起停）
└─ README.md
```

> **脚本命名与编码**：三个脚本的文件名与内容一律纯 ASCII。本机 PowerShell 5.1 的控制台代码页是
> GB2312，UTF-8（无 BOM）的中文脚本内容会被误码解析，而中文文件名在 cmd 逐层传参时容易丢失；
> 中文说明一律放在 README 与 docs 中。原设计里的 `初始化.ps1` / `启动.ps1` / `停止.ps1` 因此改名。

---

## 5. 数据模型

### 5.1 通用字段约定

所有业务表统一包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `create_by` | varchar(64) | 创建者 |
| `create_time` | datetime | 创建时间 |
| `update_by` | varchar(64) | 更新者 |
| `update_time` | datetime | 更新时间 |
| `remark` | varchar(500) | 备注 |
| `del_flag` | char(1) | 逻辑删除：`0` 存在 / `2` 删除（按需） |

**逻辑删除实现**：SQLAlchemy 层统一使用自定义 `SoftDeleteMixin`，配合 `with_loader_criteria` 全局过滤，业务代码无需手写 `WHERE del_flag='0'`。

**唯一性约束与逻辑删除的冲突**：`sys_user.user_name`、`sys_role.role_key` 等**不建数据库唯一索引**（逻辑删除后重建同名记录会冲突），改由 service 层在事务内校验 + 普通索引保证查询性能。此取舍写入《数据库设计.md》。

### 5.2 组织与用户

**sys_dept**（部门，树形）
`dept_id` PK / `parent_id`（顶级为 0）/ `ancestors`（祖级路径，如 `0,100,101`）/ `dept_name` / `order_num` / `leader` / `phone` / `email` / `status` / 通用字段

**sys_user**
`user_id` PK / `dept_id` FK / `user_name`（唯一业务键）/ `nick_name` / `user_type` / `email` / `phonenumber` / `sex` / `avatar` / `password`（bcrypt）/ `status` / `login_ip` / `login_date` / `pwd_update_date` / 通用字段

**sys_post**（岗位）
`post_id` PK / `post_code` / `post_name` / `post_sort` / `status` / 通用字段

### 5.3 权限

**sys_role**
`role_id` PK / `role_name` / `role_key`（权限标识，如 `admin`）/ `role_sort` / `data_scope`（1 全部 / 2 自定义 / 3 本部门 / 4 本部门及以下 / 5 仅本人）/ `menu_check_strictly` / `dept_check_strictly` / `status` / 通用字段

**sys_menu**（目录/菜单/按钮 三型树）
`menu_id` PK / `menu_name` / `parent_id` / `order_num` / `path` / `component` / `query` / `route_name` / `is_frame` / `is_cache` / `menu_type`（M 目录 / C 菜单 / F 按钮）/ `visible` / `status` / `perms`（权限标识，如 `system:user:add`）/ `icon` / 通用字段

**关联表**
- `sys_user_role`(user_id, role_id) 复合主键
- `sys_role_menu`(role_id, menu_id) 复合主键
- `sys_user_post`(user_id, post_id) 复合主键
- `sys_role_dept`(role_id, dept_id) 复合主键 —— 支撑 `data_scope=2` 自定义数据权限

### 5.4 平台

- **sys_dict_type**：`dict_id` / `dict_name` / `dict_type`（唯一业务键）/ `status` / 通用字段
- **sys_dict_data**：`dict_code` / `dict_sort` / `dict_label` / `dict_value` / `dict_type` / `css_class` / `list_class` / `is_default` / `status` / 通用字段
- **sys_config**：`config_id` / `config_name` / `config_key`（唯一业务键）/ `config_value` / `config_type`（Y 内置不可删 / N 可删）/ 通用字段
- **sys_notice**：`notice_id` / `notice_title` / `notice_type`（1 通知 / 2 公告）/ `notice_content`（LONGTEXT，富文本）/ `status` / 通用字段

### 5.5 日志与会话

- **sys_oper_log**：`oper_id` / `title` / `business_type` / `method` / `request_method` / `operator_type` / `oper_name` / `dept_name` / `oper_url` / `oper_ip` / `oper_location` / `oper_param` / `json_result` / `status` / `error_msg` / `oper_time`（索引）/ `cost_time`
- **sys_login_log**：`info_id` / `user_name` / `ipaddr` / `login_location` / `browser` / `os` / `status` / `msg` / `login_time`（索引）
- **sys_user_token**：`token_id` / `user_id` / `access_jti`（唯一）/ `access_expire` / `refresh_jti`（唯一）/ `refresh_expire` / `login_ip` / `browser` / `os` / `login_time` / `revoked`

**为什么令牌要落库**：纯无状态 JWT 无法实现「登出立即失效」「强制下线」「在线用户列表」「单点登录限制」。落库后按 `jti` 校验即可，代价是每次请求一次主键查询——用缓存吸收。

### 5.6 文件

**sys_file**：`file_id` / `file_name`（存储名）/ `original_name` / `file_path` / `file_url` / `file_size` / `file_type` / `mime_type` / `biz_type`（业务分类）/ `biz_id` / `storage`（local / oss）/ 通用字段

**存储抽象**：`StorageBackend` 接口 + `LocalStorage` 实现，落盘到 `D:\work\enterprise-admin\backend\uploads\`（可配置），预留 OSS 扩展点。

---

## 6. 权限模型（四层）

### 6.1 第一层：接口级权限

路由声明式鉴权：

```python
@router.post("", dependencies=[Depends(require_perm("system:user:add"))])
async def create_user(...): ...
```

`require_perm` 依赖：取出当前用户 → 判断是否超级管理员（`role_key='admin'` 直接放行）→ 否则比对权限码集合 → 不匹配抛 `ForbiddenException`（HTTP 403，业务码 403）。

**超级管理员特例**：`admin` 角色不走权限码比对，拥有全部权限。这不是偷懒——它避免了新加功能后管理员被自己的权限系统锁死，是行业惯例。此设计点写入面试手册。

### 6.2 第二层：菜单/路由级权限

登录后前端调用 `GET /api/v1/auth/routers`：

1. 后端按用户角色查出可见的 `menu_type in (M, C)` 菜单；
2. 组装成树（`utils/tree.py` 通用构建函数，部门树/菜单树复用）；
3. 前端 `permissionStore` 将后端返回的扁平组件字符串（如 `system/user/index`）通过 `import.meta.glob('./views/**/*.vue')` 映射为真实组件；
4. `router.addRoute()` 动态注册，侧边栏由同一份数据渲染。

**兜底路由必须在动态路由注册后添加**，否则 404 页面会先匹配、动态路由失效——这是 Vue Router 经典坑，写入面试手册。

### 6.3 第三层：按钮级权限

`menu_type='F'` 的按钮记录，其 `perms` 一并下发。前端自定义指令：

```vue
<el-button v-hasPerm="['system:user:add']">新增</el-button>
```

指令在 `mounted` 阶段检查权限，不匹配则 `el.parentNode.removeChild(el)`。

**职责边界**：前端隐藏按钮只是体验优化，**真正的拦截在后端接口级权限**。二者是「藏起来」与「拦得住」的关系——面试高频追问点。

### 6.4 第四层：数据权限

角色 `data_scope` 决定查询可见范围：

| 值 | 含义 | SQL 条件 |
|---|---|---|
| 1 | 全部数据 | 无附加条件 |
| 2 | 自定义部门 | `dept_id IN (SELECT dept_id FROM sys_role_dept WHERE role_id=?)` |
| 3 | 本部门 | `dept_id = :current_dept_id` |
| 4 | 本部门及以下 | `dept_id IN (递归 CTE 取 dept 子树)` |
| 5 | 仅本人 | `user_id = :current_user_id`（或按 `create_by`） |

**实现方式**：`DataScope` 上下文对象 + service 层统一入口 `apply_data_scope(stmt, model, user)`，在构造 SQLAlchemy 语句时注入过滤条件。业务代码零侵入。

「本部门及以下」用 MySQL 8 递归 CTE：

```sql
WITH RECURSIVE dept_tree AS (
  SELECT dept_id FROM sys_dept WHERE dept_id = :root AND del_flag = '0'
  UNION ALL
  SELECT d.dept_id FROM sys_dept d JOIN dept_tree t ON d.parent_id = t.dept_id
  WHERE d.del_flag = '0'
)
SELECT dept_id FROM dept_tree
```

**多角色合并规则**：用户有多个角色时取**并集**（权限最大化）。同时提供「菜单树父子联动」开关 `menu_check_strictly`，处理半选父节点是否授权子节点的歧义。

---

## 7. 认证与会话

### 7.1 登录流程

```
1. GET  /auth/captchaImage        → { uuid, img(base64) }，答案存缓存 TTL 2min
2. POST /auth/login               → { username, password, code, uuid }
   ├─ 校验验证码（一次性，校验后立即删除）
   ├─ 查用户 → bcrypt 校验密码
   ├─ 失败：登录失败计数 +1（TTL 10min），达 5 次锁定；写 sys_login_log
   ├─ 成功：清零计数；签发 access(30min) + refresh(7d)
   ├─ 写 sys_user_token；写 sys_login_log；更新 login_ip/login_date
   └─ 返回 { access_token, refresh_token, expires_in }
3. GET  /auth/profile             → 用户信息 + roles + permissions
4. GET  /auth/routers             → 动态菜单树
```

### 7.2 令牌设计

- JWT HS256，payload：`{ sub: user_id, jti, type: 'access'|'refresh', exp, iat }`
- **每次请求都校验 `jti` 在 `sys_user_token` 中存在且未撤销** —— 这是「登出即可失效」的关键
- `POST /auth/refresh`：用 refresh_token 换取新的 access（并轮换 refresh，防重放）
- 前端 axios 拦截器：遇 401 自动刷新并重放原请求，**并做并发去重**（多个请求同时 401 只触发一次刷新）

### 7.3 其他

- **密码策略**：bcrypt（cost 12）；支持 `sys_config` 配置密码有效期与强度
- **在线用户**：查 `sys_user_token` 有效记录，解析 IP 归属地与浏览器/OS
- **务必注意**：Pinia 中的 token 用 `localStorage` 持久化；生产环境应改用 httpOnly Cookie（写入安全清单）

---

## 8. 接口规范

### 8.1 统一响应

```json
{ "code": 200, "msg": "操作成功", "data": { } }
```

| HTTP | 业务码 | 场景 |
|---|---|---|
| 200 | 200 | 成功 |
| 400 | 400 / 422 | 参数校验失败（附字段级错误） |
| 401 | 401 | 未认证 / 令牌失效 → 前端跳登录 |
| 403 | 403 | 已认证但无权限 |
| 404 | 404 | 资源不存在 |
| 500 | 500 | 服务端异常（对外隐藏堆栈，对内记日志） |

**设计说明**：HTTP 状态码语义化（不搞「全部返回 200 再在业务码里判错」），REST 规范正确，面试时可讲清与国内常见做法的差异与取舍。

### 8.2 分页

入参：`page_num`（默认 1）、`page_size`（默认 10，上限 100）
出参：`{ "rows": [], "total": 0 }`

### 8.3 接口清单（按模块）

| 模块 | 接口 |
|---|---|
| **认证** | `GET /auth/captchaImage`、`POST /auth/login`、`POST /auth/logout`、`POST /auth/refresh`、`GET /auth/profile`、`PUT /auth/profile`、`PUT /auth/password`、`GET /auth/routers` |
| **用户** | `GET /system/user`、`GET /system/user/{id}`、`POST /system/user`、`PUT /system/user`、`DELETE /system/user/{ids}`、`PUT /system/user/resetPwd`、`PUT /system/user/changeStatus`、`GET /system/user/deptTree`、`GET /system/user/authRole/{id}`、`PUT /system/user/authRole` |
| **角色** | 全 CRUD、`PUT /system/role/changeStatus`、`PUT /system/role/dataScope`、用户授权（已分配/未分配/批量授权/取消授权） |
| **菜单** | 全 CRUD、`GET /system/menu/treeselect`、`GET /system/menu/roleMenuTreeselect/{roleId}` |
| **部门** | 全 CRUD、`GET /system/dept/treeselect` |
| **岗位** | 全 CRUD、`GET /system/post/optionselect` |
| **字典** | 字典类型 + 字典数据 全 CRUD、`GET /system/dict/data/type/{dictType}` |
| **参数** | 全 CRUD、`GET /system/config/configKey/{key}` |
| **公告** | 全 CRUD |
| **操作日志** | `GET /monitor/operlog`、`DELETE /monitor/operlog/{ids}`、`DELETE /monitor/operlog/clean`、`GET /monitor/operlog/export` |
| **登录日志** | `GET /monitor/loginlog`、`DELETE /monitor/loginlog/{ids}`、`DELETE /monitor/loginlog/clean` |
| **在线用户** | `GET /monitor/online`、`DELETE /monitor/online/{tokenId}`（强退） |
| **服务监控** | `GET /monitor/server`（CPU/内存/磁盘/Python 与依赖版本） |
| **文件** | `POST /file/upload`、`GET /file`、`DELETE /file/{ids}`、`GET /file/download/{id}` |

`/docs`（Swagger UI）与 `/redoc` 默认开启（演示利器），可通过 `.env` 的 `DOCS_ENABLED` 关闭。

---

## 9. 前端设计

### 9.1 状态划分（Pinia）

| Store | 职责 |
|---|---|
| `user` | token、用户信息、角色、权限码集合；login / getInfo / logout |
| `permission` | 静态路由、动态路由生成、`addRoute` 副作用 |
| `tagsView` | 已访问页面标签、缓存页面名列表（keep-alive） |
| `app` | 侧边栏折叠、主题色、暗色模式、设备类型 |
| `dict` | 字典数据缓存（按 `dict_type` 懒加载） |

### 9.2 请求层

`utils/request.ts` 封装 axios：

- **请求拦截**：注入 `Authorization: Bearer`；防重复提交（记录 pending 请求，同 key 拒绝）
- **响应拦截**：`code !== 200` 统一 `ElMessage.error`；401 → 刷新令牌 → 重放；刷新失败 → 清空状态跳登录
- **类型**：泛型 `request<T>()`，与后端 schema 对齐的 `types/api/*.ts`

### 9.3 自研业务组件

| 组件 | 价值 |
|---|---|
| `ProTable` | 搜索表单 + 表格 + 分页 + 工具栏一体化，业务页面只需声明列与查询项 |
| `ProForm` | 表单 + 校验规则 + 字典自动渲染下拉/单选 |
| `DictTag` | 字典值 → 带色标签，避免每个页面写映射 |
| `Pagination` | 统一分页交互 |
| `RightToolbar` | 列显隐、刷新、搜索区折叠 |
| `TreeSelect` | 部门/菜单树选择器 |
| `FileUpload` | 上传 + 回显 + 删除，对接后端文件接口 |

### 9.4 布局

经典企业后台布局：左侧菜单（可折叠、支持多级）+ 顶部导航（面包屑、全屏、主题、用户菜单）+ 多标签页 + 内容区（keep-alive 缓存）。

### 9.5 示例业务模块

1. **通知公告**：富文本编辑、发布/关闭、列表检索
2. **文件管理**：上传、分类、预览、下载、删除

两者覆盖「列表-新增-编辑-删除-权限-日志」完整闭环，作为后续业务的复制模板。

---

## 10. 错误处理与日志

### 10.1 后端异常体系

```
AppException (基类，带 code/msg)
├─ BusinessException      业务规则不满足（400）
├─ UnauthorizedException  未认证（401）
├─ ForbiddenException     无权限（403）
├─ NotFoundException      资源不存在（404）
└─ ValidationException    参数校验失败（422）
```

全局处理器统一转成 `{code,msg,data}`；未捕获异常记 `logger.exception` 并对外返回通用错误（不泄漏堆栈）。

### 10.2 日志

- **访问日志**：中间件记录 method / path / status / 耗时 / request_id
- **操作日志**：`@oper_log(title="用户管理", business_type=INSERT)` 装饰器，自动记录操作人、参数、结果、耗时、异常信息
- **日志落盘**：`loguru`，按天切割，目录 `backend\logs\`（D 盘）
- **request_id**：入口生成并注入日志上下文与响应头，便于问题追踪

---

## 11. 测试策略

后端 pytest（用户明确要求）：

| 测试文件 | 覆盖内容 |
|---|---|
| `test_auth.py` | 验证码、登录成功/失败、锁定、登出、令牌刷新、失效令牌 |
| `test_rbac.py` | 权限矩阵：有权限通过 / 无权限 403 / 超级管理员全通 |
| `test_data_scope.py` | 五种数据范围各自的可见行数断言（核心） |
| `test_user.py` 等 | 各模块 CRUD 正常路径 + 边界（重复名、必填、越权） |
| `test_menu.py` | 菜单树构建、动态路由数据正确性 |

**测试基础设施**：独立测试库 `enterprise_admin_test`，每用例事务回滚保证隔离；`httpx.AsyncClient` + `ASGITransport` 直连应用，无需起真实服务。

前端：`vue-tsc` 类型检查 + ESLint 通过（不引入前端单测，除非后续要求）。

**验收方式**：每期结束必须实际运行 `pytest` 与前端构建，不接受「应该能跑」。

---

## 12. 交付物

1. 可运行系统（`init.ps1` → `start.ps1` 冷启动即可用）
2. `README.md`：环境要求、安装、启动、常见问题、目录说明
3. 文档集：
   - `docs/架构设计.md`
   - `docs/数据库设计.md`（含表结构、ER 关系、索引说明、设计取舍）
   - `docs/接口清单.md`
   - `docs/面试讲解手册.md`（**重点**：技术点讲解稿 + 高频追问 + 应答要点）
4. 种子数据：超管、演示角色（部门主管/普通员工）、部门树、菜单树、字典、参数、公告
5. 备选部署配置：`docker-compose.yml`、`nginx.conf`

---

## 13. 分期计划

| 期 | 内容 | 验收标准 |
|---|---|---|
| **P0 底座** | MySQL 便携版就位（下载/解压/初始化/启停脚本）；后端骨架（配置/日志/异常/统一响应/健康检查/迁移）；前端骨架（create-vue 基线 + Element Plus + 布局雏形）；`启动.ps1`；登录接口打通 | 双击 `启动.ps1` → 打开浏览器能**登录进后台空壳**（垂直切片跑通） |
| **P1 RBAC** | 用户/角色/菜单/部门/岗位 全 CRUD；四层权限；数据权限；动态路由；按钮权限指令 | 两个不同角色登录 → 菜单不同、按钮不同、可见数据行数不同 |
| **P2 平台能力** | 字典/参数/公告/文件/操作日志/登录日志/在线用户/服务监控 | 各页面可用，操作自动入日志 |
| **P3 质量交付** | 种子数据完善；pytest 全绿；ESLint + vue-tsc 通过；README 与三份文档；面试讲解手册；备选部署配置 | 冷启动一条命令可用，文档齐备可演练 |

**分期理由**：P0 刻意打通**垂直切片**（数据库 → 后端 → 前端 → 界面）而非逐层横向铺开，好处是风险最早暴露（版本兼容、编码、跨域、驱动），且你从 P0 起就能看到界面。

---

## 14. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 前端生态版本过新（Vite 8 / Pinia 4 / Router 5 / TS 7），与我既有知识存在差异 | 配置写错、跑不起来 | 用 `create-vue` 官方基线定版本；每一步实际启动验证；遇 API 变更即时查官方文档 |
| asyncmy 驱动在 Windows 的构建问题 | 后端连不上库 | 已确认存在 cp312 win_amd64 wheel；若失败回落 `aiomysql`（纯 Python） |
| MySQL 8.0.29 无管理员权限初始化失败 | 无法建库 | 便携版初始化不需要管理员；数据目录放 D 盘避免权限继承问题 |
| 214MB 下载中断 | 环境不就绪 | 支持断点续传重试；记录校验值 |
| 数据权限实现漏洞（越权可见） | 作品集致命伤 | `test_data_scope.py` 强制覆盖五种范围 + 边界用户 |
| 端口冲突（3306/8000/5173） | 启动失败 | 启动脚本预检端口并给出明确提示；端口可经 `.env` 配置 |

---

## 15. 后续 Roadmap（不在本期）

1. 代码生成器（读表 → 生成前后端 CRUD）
2. 工作流引擎（审批流）
3. 多租户隔离
4. Redis 缓存实现 + 消息队列
5. 单元测试覆盖率门禁 + CI/CD（GitHub Actions）
6. 监控告警（Prometheus + Grafana）

---

## 附录 A：本机环境事实（2026-10-17 实测）

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11 专业版 |
| Python | 3.12.0（`C:\Python312\python.exe`，已有，不重装） |
| Node | v24.14.0（`D:\code tool\nodejs`，D 盘，不动） |
| npm | 11.9.0 |
| Docker | **未安装** |
| WSL | **不可用** |
| MySQL / MariaDB | **未安装** |
| 端口 3306 / 8000 / 5173 | 当前空闲 |
| 磁盘可用 | C 51GB / D 88GB |

**镜像源可用性实测**：

| 源 | 结果 |
|---|---|
| `mirrors.huaweicloud.com/mysql` | 可用，MySQL 8.0.24~8.0.29 winx64.zip（8.0.29 = 214MB） |
| `mirrors.aliyun.com/mysql` | 可用，仅 8.0.27/8.0.28 |
| `pypi.tuna.tsinghua.edu.cn` | 可用（458ms） |
| `registry.npmmirror.com` | 可用（843ms） |
| `dev.mysql.com` 官方源 | 403（不可用） |

**前端依赖最新版本（实测）**：vue 3.5.44 / vite 8.3.4（要求 Node ≥20.19 或 ≥22.12，本机 24.14 满足）/ element-plus 2.14.7 / pinia 4.1.0 / vue-router 5.4.0 / typescript 7.0.2 / vue-tsc 3.3.13 / axios 1.20.0 / sass 1.105.2

## 附录 B：D 盘落位清单

| 内容 | 路径 |
|---|---|
| 项目根 | `D:\work\enterprise-admin` |
| MySQL 程序 | `D:\devtools\mysql-8.0.29` |
| MySQL 数据/日志 | `D:\devtools\mysql-data` |
| pip 缓存 | `D:\devtools\caches\pip` |
| npm 缓存 | `D:\devtools\caches\npm` |
| pnpm store | `D:\devtools\caches\pnpm-store` |
| Python 虚拟环境 | `D:\work\enterprise-admin\backend\.venv` |
| 上传文件 | `D:\work\enterprise-admin\backend\uploads` |
| 运行日志 | `D:\work\enterprise-admin\backend\logs` |

**唯一无法避免的 C 盘写入**：Python 解释器与 Node 自身已存在（不重装）；若选择注册 Windows 服务，会写 C 盘注册表（故默认不注册）。
