# enterprise-admin P0（底座 + 登录垂直切片）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通「MySQL 便携版 → FastAPI 后端 → Vue3 前端 → 浏览器登录进入后台空壳」的垂直切片，让后续每一期都有可运行的地基。

**Architecture:** 后端分层为 `api → services → models`，横切能力（配置、日志、异常、统一响应、缓存、安全、鉴权依赖）集中在 `core/`。令牌采用 access + refresh 双令牌且**落库**，以支持登出即失效与在线用户。前端由 `create-vue` 官方基线定版本（Vite 8 / Pinia 4 / Router 5 / TS 7），在其上叠加 Element Plus、axios 封装、Pinia 状态与动态路由守卫。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / asyncmy / Alembic / PyJWT / bcrypt / Pillow / loguru / pytest + httpx ｜ Vue 3.5 / TypeScript / Vite / Element Plus / Pinia / Vue Router / axios ｜ MySQL 8.0.29 便携版

**Spec:** `docs/superpowers/specs/2026-10-17-enterprise-admin-design.md`

## Global Constraints

- **落盘位置**：MySQL 程序 `D:\devtools\mysql-8.0.29`，数据 `D:\devtools\mysql-data`，项目 `D:\work\enterprise-admin`，venv `backend\.venv`，pip/npm 缓存 `D:\devtools\caches\{pip,npm,pnpm-store}`。任何新文件不得落在 C 盘。
- **脚本命名与编码**：所有 `.ps1` **文件名与内容一律纯 ASCII**（本机 pwsh 为 PowerShell 5.1、控制台代码页 GB2312，UTF-8 无 BOM 的中文脚本内容会被误码解析）。中文提示只出现在 README 与 docs 中。脚本名用 `init.ps1` / `start.ps1` / `stop.ps1`。
- **MySQL 运行方式**：默认**不注册 Windows 服务**，由 `tools/mysql-ctl.ps1` 拉起 `mysqld` 进程。
- **数据库**：库名 `enterprise_admin`（测试库 `enterprise_admin_test`），字符集 `utf8mb4`，排序规则 `utf8mb4_0900_ai_ci`。
- **统一响应**：`{"code": int, "msg": str, "data": any}`；HTTP 状态码语义化（200/400/401/403/404/422/500），不搞「全 200 + 业务码判错」。
- **分页契约**：入参 `page_num`（默认 1）、`page_size`（默认 10，**上限 100**），出参 `{"rows": [], "total": 0}`。
- **密码**：bcrypt cost 12；登录口令长度 6–32 字符（Pydantic 校验，规避 bcrypt 72 字节上限）。
- **令牌**：access 30 分钟、refresh 7 天，HS256；**每次请求校验 `jti` 在 `sys_user_token` 中存在且 `revoked=0`**。
- **逻辑删除**：`del_flag`，`0` 存在 / `2` 删除；**不建数据库唯一索引**（避免逻辑删除后同名重建冲突），唯一性由 service 层在事务内校验。
- **前端**：TypeScript 严格模式；`vue-tsc` 与 ESLint 必须零错误；Element Plus 按需自动导入（`unplugin-auto-import` + `unplugin-vue-components`）。
- **前端单测**：仅引入 vitest 覆盖 `src/utils/request.ts` 的刷新去重逻辑（全项目唯一高风险前端逻辑），不做界面单测。
- **验证纪律**：每个任务的「verification / run」步骤必须真实执行并看到预期输出，不接受「应该能跑」。

## Review Focus

以下 5 类输入/失败模式是设计文档暗示但不会自然被某个任务的正向测试覆盖的，按「最可能伤到使用者」排序。每条都已在下文指定任务中补上对应测试。

1. **信息泄漏**：401 响应不得区分「用户不存在」「密码错误」「令牌过期」；未捕获异常（含数据库连不上）的响应体不得出现堆栈、SQL 或连接串 → Task 3、Task 8、Task 9。
2. **逻辑删除与唯一性冲突**：删除用户后用同一 `user_name` 重建必须成功，且已删记录不得出现在列表查询与登录校验中 → Task 5、Task 8。
3. **令牌刷新竞态**：前端多个请求同时收到 401 时只能触发一次刷新；后端 refresh 轮换后旧 refresh 重放必须被拒 → Task 9、Task 12。
4. **分页与查询参数边界**：`page_size=0`、`-1`、`100000`，`page_num` 超范围或非数字，必须被规范化或返回 422，而不是 500 → Task 3、Task 7（含列表接口的边界断言）。
5. **空权限不白屏**：无任何菜单权限的角色登录成功，`/auth/routers` 返回空数组而非报错，前端进入后台不白屏 → Task 10、Task 17。

---

## 文件结构（本计划将创建的文件及其职责）

```
D:\work\enterprise-admin\
├─ tools\
│  ├─ install-mysql.ps1        # 解压 ZIP + 生成 my.ini + initialize-insecure
│  └─ mysql-ctl.ps1            # start | stop | status
├─ init.ps1                    # 一次性：建库 + alembic upgrade + 种子数据
├─ start.ps1                   # MySQL + uvicorn + vite（各起独立窗口）
├─ stop.ps1
├─ backend\
│  ├─ requirements.txt
│  ├─ pytest.ini
│  ├─ alembic.ini
│  ├─ .env.example / .env
│  ├─ alembic\
│  │  ├─ env.py                # 异步迁移环境
│  │  └─ versions\0001_core_auth_tables.py
│  ├─ app\
│  │  ├─ __init__.py
│  │  ├─ main.py               # create_app()：中间件、异常、路由、生命周期
│  │  ├─ core\
│  │  │  ├─ config.py          # Settings + get_settings()
│  │  │  ├─ constants.py       # 枚举
│  │  │  ├─ response.py        # success/page + PageParams/PageResult
│  │  │  ├─ exceptions.py      # 异常体系 + register_exception_handlers()
│  │  │  ├─ logging.py         # setup_logging()
│  │  │  ├─ cache.py           # CacheBackend 协议 + MemoryCache
│  │  │  ├─ security.py        # bcrypt / JWT / 验证码
│  │  │  └─ deps.py            # get_current_user / require_perm / CurrentUser
│  │  ├─ db\
│  │  │  ├─ base.py            # Base + 混入
│  │  │  ├─ session.py         # engine / AsyncSessionLocal / get_db
│  │  │  └─ soft_delete.py     # 全局逻辑删除过滤
│  │  ├─ middlewares\request_id.py
│  │  ├─ models\               # dept/user/post/role/menu/token/login_log + __init__
│  │  ├─ schemas\              # auth.py  common.py
│  │  ├─ services\             # auth_service.py  menu_service.py  log_service.py
│  │  ├─ utils\tree.py         # 通用树构建
│  │  └─ api\v1\
│  │     ├─ router.py          # 汇总路由
│  │     └─ auth.py
│  ├─ scripts\seed_data.py     # 超管/角色/部门/菜单播种
│  └─ tests\
│     ├─ conftest.py           # 测试库 + 事务回滚 fixture + AsyncClient
│     ├─ test_health.py
│     ├─ test_response_and_errors.py
│     ├─ test_cache.py
│     ├─ test_security.py
│     ├─ test_models_migration.py
│     └─ test_auth.py
└─ frontend\
   ├─ vite.config.ts           # 代理、别名、自动导入、按需组件
   ├─ .env.development
   ├─ vitest.config.ts
   └─ src\
      ├─ main.ts
      ├─ App.vue
      ├─ utils\{request.ts,auth.ts}
      ├─ utils\__tests__\request.spec.ts
      ├─ api\auth.ts
      ├─ types\api\auth.ts
      ├─ stores\{user.ts,app.ts,permission.ts,index.ts}
      ├─ router\{index.ts,guard.ts}
      ├─ layout\{index.vue,components\Sidebar\index.vue,Navbar.vue,AppMain.vue,TagsView.vue}
      └─ views\{login\index.vue,dashboard\index.vue,error\404.vue}
```

---

### Task 1: MySQL 便携版安装与启停

**Files:**
- Create: `tools/install-mysql.ps1`, `tools/mysql-ctl.ps1`
- Create (运行时生成): `D:\devtools\mysql-8.0.29\my.ini`

**Interfaces:**
- Consumes: 已下载的 `tools/downloads/mysql-8.0.29-winx64.zip`（214MB，已完成）
- Produces: `tools\mysql-ctl.ps1 -Action start|stop|status`；MySQL 监听 `127.0.0.1:3306`，root 密码 `Admin@123456`；库 `enterprise_admin`、`enterprise_admin_test` 存在

- [ ] **Step 1: 校验下载完整性**

```powershell
Get-Item 'D:\work\enterprise-admin\tools\downloads\mysql-8.0.29-winx64.zip' | Select-Object Length
```
Expected: `224363773` 左右（214MB）；若明显偏小说明下载不完整，重新下载。

- [ ] **Step 2: 编写 `tools/install-mysql.ps1`**

脚本行为（内容纯 ASCII）：
1. 若 `D:\devtools\mysql-8.0.29\bin\mysqld.exe` 已存在则跳过解压；
2. `Expand-Archive` 解压 ZIP 到 `D:\devtools\`，把内层 `mysql-8.0.29-winx64` 重命名为 `mysql-8.0.29`；
3. 生成 `D:\devtools\mysql-8.0.29\my.ini`，内容（节选自 spec 第 2.2 节决策）：
   `[mysqld]` 段设 `basedir=D:/devtools/mysql-8.0.29`、`datadir=D:/devtools/mysql-data`、`port=3306`、`bind-address=127.0.0.1`、`character-set-server=utf8mb4`、`collation-server=utf8mb4_0900_ai_ci`、`default-storage-engine=INNODB`、`max_connections=200`、`log-error=D:/devtools/mysql-data/logs/error.log`、`slow_query_log=1`、`long_query_time=1`、`[client]` 段设 `default-character-set=utf8mb4`；
4. 创建 `D:\devtools\mysql-data\logs`；
5. 执行 `mysqld --defaults-file=... --initialize-insecure`（root 无密码初始化）；
6. 打印下一步提示（启动 mysqld 并设置 root 密码）。

- [ ] **Step 3: 编写 `tools/mysql-ctl.ps1`**

参数：`-Action start|stop|status`。
- `start`：若 3306 已被 `mysqld` 占用则直接返回；否则 `Start-Process mysqld.exe -ArgumentList "--defaults-file=..." -WindowStyle Hidden`，轮询 `mysqladmin ping` 最多 60 秒。
- `stop`：优先 `mysqladmin -uroot -p<password> shutdown`；失败则按端口找到 PID 后 `Stop-Process`。
- `status`：输出进程是否存在 + `mysqladmin ping` 结果 + `SELECT VERSION()`。

- [ ] **Step 4: 安装并首次启动 MySQL**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\tools\install-mysql.ps1
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\tools\mysql-ctl.ps1 -Action start
```
Expected: 打印 `MySQL is ready on 127.0.0.1:3306` 与版本 `8.0.29`。

- [ ] **Step 5: 设置 root 密码并建库**

Run（把 `mysql.exe` 加入本次会话 PATH 后执行）：
```powershell
& 'D:\devtools\mysql-8.0.29\bin\mysql.exe' -uroot --skip-password -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'Admin@123456'; CREATE DATABASE enterprise_admin DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; CREATE DATABASE enterprise_admin_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
& 'D:\devtools\mysql-8.0.29\bin\mysql.exe' -uroot -pAdmin@123456 -e "SELECT VERSION(); SHOW DATABASES;"
```
Expected: 输出 `8.0.29`，且 `enterprise_admin`、`enterprise_admin_test` 在库列表中。

- [ ] **Step 6: 验证启停闭环**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\tools\mysql-ctl.ps1 -Action stop
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\tools\mysql-ctl.ps1 -Action start
```
Expected: stop 后 `status` 报未运行；start 后 60 秒内 ping 通。

- [ ] **Step 7: Commit**

```bash
git add tools/install-mysql.ps1 tools/mysql-ctl.ps1
git commit -m "build: add portable MySQL 8.0.29 install and control scripts"
```

---

### Task 2: 后端工程骨架与健康检查

**Files:**
- Create: `backend/requirements.txt`, `backend/.env.example`, `backend/.env`, `backend/pytest.ini`
- Create: `backend/app/__init__.py`, `backend/app/main.py`
- Create: `backend/app/core/config.py`, `backend/app/core/logging.py`
- Create: `backend/app/middlewares/request_id.py`, `backend/app/middlewares/__init__.py`
- Test: `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`

**Interfaces:**
- Consumes: Task 1 的 MySQL 与两个库
- Produces:
  - `app/core/config.py`：`class Settings(BaseSettings)`，字段 `APP_NAME: str = "enterprise-admin"`、`APP_VERSION: str = "0.1.0"`、`DEBUG: bool = True`、`DOCS_ENABLED: bool = True`、`API_V1_PREFIX: str = "/api/v1"`、`SECRET_KEY: str`、`ACCESS_TOKEN_EXPIRE_MINUTES: int = 30`、`REFRESH_TOKEN_EXPIRE_DAYS: int = 7`、`MYSQL_HOST/PORT/USER/PASSWORD/DB: str|int`、`CORS_ORIGINS: list[str]`、`UPLOAD_DIR: Path`、`LOG_DIR: Path`；属性 `database_url -> str` 返回 `mysql+asyncmy://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4`；`@lru_cache def get_settings() -> Settings`
  - `app/core/logging.py`：`setup_logging() -> None`，loguru 输出到 `LOG_DIR/backend-{time:YYYY-MM-DD}.log`（rotation `00:00`、retention `30 days`、encoding `utf-8`），DEBUG 时同时输出到 stderr
  - `app/main.py`：`def create_app() -> FastAPI`，`app = create_app()`；挂载 `RequestIdMiddleware`；`GET /health` 返回 `{"status": "ok", "version": settings.APP_VERSION}`
  - `tests/conftest.py`：fixture `anyio_backend`、`client`（httpx `AsyncClient` + `ASGITransport`，`base_url="http://test"`）

- [ ] **Step 1: 建 venv 并重定向缓存到 D 盘**

Run:
```powershell
$env:PIP_CACHE_DIR='D:\devtools\caches\pip'
python -m venv D:\work\enterprise-admin\backend\.venv
& D:\work\enterprise-admin\backend\.venv\Scripts\python.exe -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
```
Expected: pip 升级成功，缓存写入 D 盘。

- [ ] **Step 2: 写 `requirements.txt` 并安装**

内容（不写死小版本，安装后 `pip freeze` 的结果另存 `requirements.lock.txt` 作为可复现基线）：
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncmy
alembic
pydantic-settings
pyjwt
bcrypt
pillow
loguru
python-multipart
psutil
httpx
pytest
pytest-asyncio
anyio
```
Run: `...\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
Expected: 全部安装成功。**若 `asyncmy` 安装失败**（无 cp312 win_amd64 wheel），改为 `aiomysql` 并把 `database_url` 的驱动前缀改为 `mysql+aiomysql`——此回退路径已在 spec 第 14 节备案。

- [ ] **Step 3: 写失败的测试**

`backend/tests/test_health.py`：
```python
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_health_sets_request_id_header(client):
    resp = await client.get("/health")
    assert resp.headers.get("X-Request-Id")
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app'` 或 collection error）

- [ ] **Step 5: 实现 config / logging / request_id / main**

要点：
- `pytest.ini` 设 `asyncio_mode = auto`、`testpaths = tests`、`pythonpath = .`，使 `app` 可导入且无需 `@pytest.mark.asyncio`。
- `.env` 用 Task 1 的凭据；`.env.example` 不含真实密码。
- `RequestIdMiddleware` 继承 `BaseHTTPMiddleware`，在 `request.state.request_id` 写入 `uuid4().hex`，响应头带 `X-Request-Id`。
- `create_app()` 中 `DOCS_ENABLED` 为假时不挂载 `/docs` 与 `/redoc`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: `2 passed`

- [ ] **Step 7: 手动验证真实服务可启动**

Run: `cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`
Expected: 打开 `http://127.0.0.1:8000/docs` 能看到 Swagger，`/health` 返回 JSON。验证后关闭。

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/requirements.lock.txt backend/pytest.ini backend/.env.example backend/app backend/tests
git commit -m "feat(backend): add app skeleton with settings, logging, request-id and health check"
```

---

### Task 3: 统一响应、异常体系与全局处理器

**Files:**
- Create: `backend/app/core/response.py`, `backend/app/core/exceptions.py`, `backend/app/core/constants.py`
- Modify: `backend/app/main.py`（注册异常处理器与路由前缀）
- Test: `backend/tests/test_response_and_errors.py`

**Interfaces:**
- Consumes: Task 2 的 `create_app()`
- Produces:
  - `app/core/response.py`：`def success(data: Any = None, msg: str = "操作成功") -> dict[str, Any]` 返回 `{"code": 200, "msg": msg, "data": data}`；`def page(rows: Sequence[Any], total: int) -> dict[str, Any]` 返回 `{"code": 200, "msg": "查询成功", "data": {"rows": list(rows), "total": total}}`
  - `PageParams`（Pydantic）：`page_num: int = 1`、`page_size: int = 10`，`field_validator` 把非法值钳制为 `1 ≤ page_num`、`1 ≤ page_size ≤ 100`；**非数字输入由 Pydantic 返回 422**
  - `app/core/exceptions.py`：`class AppException(Exception)` 构造签名 `(code: int, msg: str, http_status: int = 400)`；子类 `BusinessException(400)`、`UnauthorizedException(401)`、`ForbiddenException(403)`、`NotFoundException(404)`、`ValidationException(422)`（子类只固定 `http_status`，`code` 默认与 HTTP 同值）；`def register_exception_handlers(app: FastAPI) -> None`
  - `app/core/constants.py`：`StatusEnum`(`NORMAL="0"`,`DISABLED="1"`)、`DelFlagEnum`(`EXISTS="0"`,`DELETED="2"`)、`MenuTypeEnum`(`DIR="M"`,`MENU="C"`,`BUTTON="F"`)、`DataScopeEnum`(`ALL=1`,`CUSTOM=2`,`DEPT=3`,`DEPT_AND_CHILD=4`,`SELF=5`)、`BusinessType`(`OTHER=0`,`INSERT=1`,`UPDATE=2`,`DELETE=3`,`GRANT=4`,`EXPORT=5`,`IMPORT=6`,`FORCE_LOGOUT=7`,`CLEAN=9`)

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_response_and_errors.py` 至少包含：
```python
async def test_business_exception_maps_to_400_with_code_and_msg(client): ...
    # 触发 /__test__/boom-business（仅测试环境注册），断言 400 与 {"code":400,"msg":"库存不足","data":None}

async def test_forbidden_maps_to_403(client): ...
async def test_not_found_maps_to_404(client): ...

async def test_unhandled_exception_hides_internals(client):
    resp = await client.get("/__test__/boom-unhandled")
    assert resp.status_code == 500
    text = resp.text
    assert "Traceback" not in text
    assert "SELECT" not in text.upper()
    assert "Admin@123456" not in text      # 连接串/密码不得泄漏
    assert "mysql+asyncmy" not in text

def test_page_params_clamps_out_of_range(): ...
    # PageParams(page_num=0, page_size=99999) -> page_num==1, page_size==100
def test_page_params_rejects_non_numeric(): ...
    # PageParams(page_num="abc") raises ValidationError
def test_page_params_negative_size_clamped(): ...
def test_page_helper_shape(): ...
```

测试用的 `__test__` 路由只在 `DEBUG=True` 时注册于 `create_app()`，生产分支不暴露。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_response_and_errors.py -v`
Expected: FAIL（路由 404 / 导入错误）

- [ ] **Step 3: 实现 response / exceptions / constants 并在 main.py 注册处理器**

处理器覆盖：`AppException`、`RequestValidationError`（→422，`data` 带字段级错误数组）、`StarletteHTTPException`、`Exception`（记录 `logger.exception`，响应固定为 `{"code":500,"msg":"系统内部错误，请稍后重试","data":None}`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_response_and_errors.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/response.py backend/app/core/exceptions.py backend/app/core/constants.py backend/app/main.py backend/tests/test_response_and_errors.py
git commit -m "feat(backend): add unified response, exception hierarchy and global handlers"
```

---

### Task 4: 数据层接入与 Alembic 迁移环境

**Files:**
- Create: `backend/app/db/session.py`, `backend/app/db/base.py`, `backend/app/db/soft_delete.py`, `backend/app/db/__init__.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`
- Modify: `backend/tests/conftest.py`（加入数据库 fixture）
- Test: `backend/tests/test_models_migration.py`（本任务只放引擎连通用例）

**Interfaces:**
- Consumes: Task 2 的 `get_settings()`
- Produces:
  - `app/db/session.py`：`engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600, echo=False)`；`AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)`；`async def get_db() -> AsyncGenerator[AsyncSession, None]`（异常回滚、正常提交、finally 关闭）
  - `app/db/base.py`：`class Base(DeclarativeBase)`；`class TimestampMixin`（`create_by`、`create_time`、`update_by`、`update_time`）；`class SoftDeleteMixin`（`del_flag: Mapped[str]` 默认 `"0"`，服务端默认值）
  - `app/db/soft_delete.py`：`def install_soft_delete_filter(session: AsyncSession) -> None`，用 `sqlalchemy.orm.with_loader_criteria` 对带 `SoftDeleteMixin` 的实体自动附加 `del_flag == "0"`；提供 `def include_deleted(session)` 逃生口
  - `alembic/env.py`：异步实现（`run_async_migrations`，`target_metadata = Base.metadata`，URL 取自 `get_settings().database_url`）
  - `tests/conftest.py` 新增 fixture：`db_session`（每个用例一个连接 + 外层事务，`join_transaction_mode="create_savepoint"`，用例结束回滚）、`client`（覆写 `get_db` 依赖注入 `db_session`）
  - **测试库准备**：`conftest.py` 在 session 级 fixture 中对 `enterprise_admin_test` 执行一次 `alembic upgrade head`（通过 `alembic.command.upgrade` 编程式调用）

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_models_migration.py`：
```python
async def test_engine_can_connect(db_session):
    from sqlalchemy import text
    result = await db_session.execute(text("SELECT VERSION()"))
    assert result.scalar().startswith("8.0.")


async def test_soft_delete_filter_is_installed(db_session):
    # 断言 install_soft_delete_filter 可被调用且不抛异常（真正的行为断言在 Task 5）
    from app.db.soft_delete import install_soft_delete_filter
    install_soft_delete_filter(db_session)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_models_migration.py -v`
Expected: FAIL（`app.db.session` 不存在）

- [ ] **Step 3: 实现 db 层与 alembic 环境**

注意点：`alembic.ini` 的 `sqlalchemy.url` 留空（由 `env.py` 注入），避免凭据进版本库；`script_location = alembic`；`env.py` 需支持 `alembic revision --autogenerate` 与 `upgrade` 的异步路径。

- [ ] **Step 4: 初始化 alembic 并跑空迁移验证环境可用**

Run:
```powershell
cd D:\work\enterprise-admin\backend
.venv\Scripts\python.exe -m alembic upgrade head
```
Expected: 无迁移时命令成功结束（此时 `versions\` 为空），且 `alembic_version` 表在测试库中创建。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_models_migration.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/db backend/alembic.ini backend/alembic backend/tests/conftest.py backend/tests/test_models_migration.py
git commit -m "feat(backend): add async data layer with session, soft-delete filter and alembic env"
```

---

### Task 5: 核心 ORM 模型与初始迁移（11 张表）

**Files:**
- Create: `backend/app/models/__init__.py`, `dept.py`, `post.py`, `user.py`, `role.py`, `menu.py`, `token.py`, `login_log.py`
- Create: `backend/alembic/versions/0001_core_auth_tables.py`（由 autogenerate 起草后人工审查）
- Modify: `backend/tests/test_models_migration.py`

**Interfaces:**
- Consumes: Task 4 的 `Base`、混入、`db_session`
- Produces: 11 个 ORM 类，表名与列名严格按 spec 第 5 节：

| 类 | 表 | 关键列 |
|---|---|---|
| `SysDept` | `sys_dept` | `dept_id` PK、`parent_id`、`ancestors`、`dept_name`、`order_num`、`leader`、`phone`、`email`、`status`、混入 |
| `SysPost` | `sys_post` | `post_id` PK、`post_code`、`post_name`、`post_sort`、`status`、混入 |
| `SysUser` | `sys_user` | `user_id` PK、`dept_id` FK、`user_name`、`nick_name`、`user_type`、`email`、`phonenumber`、`sex`、`avatar`、`password`、`status`、`login_ip`、`login_date`、`pwd_update_date`、混入 |
| `SysRole` | `sys_role` | `role_id` PK、`role_name`、`role_key`、`role_sort`、`data_scope`、`menu_check_strictly`、`dept_check_strictly`、`status`、混入 |
| `SysMenu` | `sys_menu` | `menu_id` PK、`menu_name`、`parent_id`、`order_num`、`path`、`component`、`query`、`route_name`、`is_frame`、`is_cache`、`menu_type`、`visible`、`status`、`perms`、`icon`、混入 |
| `SysUserRole` | `sys_user_role` | 复合 PK `(user_id, role_id)` |
| `SysRoleMenu` | `sys_role_menu` | 复合 PK `(role_id, menu_id)` |
| `SysUserPost` | `sys_user_post` | 复合 PK `(user_id, post_id)` |
| `SysRoleDept` | `sys_role_dept` | 复合 PK `(role_id, dept_id)` |
| `SysUserToken` | `sys_user_token` | `token_id` PK、`user_id`、`access_jti`(索引)、`access_expire`、`refresh_jti`(索引)、`refresh_expire`、`login_ip`、`browser`、`os`、`login_time`、`revoked` |
| `SysLoginLog` | `sys_login_log` | `info_id` PK、`user_name`、`ipaddr`、`login_location`、`browser`、`os`、`status`、`msg`、`login_time`(索引) |

- [ ] **Step 1: 写失败的测试**

在 `test_models_migration.py` 追加：
```python
async def test_core_tables_exist(db_session):
    expected = {"sys_dept","sys_post","sys_user","sys_role","sys_menu","sys_user_role",
                "sys_role_menu","sys_user_post","sys_role_dept","sys_user_token","sys_login_log"}
    rows = await db_session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"))
    assert expected <= {r[0] for r in rows}

async def test_user_name_has_no_unique_index(db_session):
    # 逻辑删除要求：user_name 不能是数据库唯一索引，否则同名重建会失败
    rows = await db_session.execute(text(
        "SELECT index_name, non_unique FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = 'sys_user' AND column_name = 'user_name'"))
    assert all(r[1] == 1 for r in rows)      # 只有普通索引

async def test_soft_delete_hides_deleted_rows(db_session):
    db_session.add(SysDept(dept_id=9001, parent_id=0, ancestors="0", dept_name="T", order_num=1, del_flag="2"))
    await db_session.flush()
    found = await db_session.execute(select(SysDept).where(SysDept.dept_id == 9001))
    assert found.scalar_one_or_none() is None

async def test_deleted_user_name_can_be_reused(db_session):
    # 建两条同名 user_name：一条已删、一条存在 —— 不得违反任何约束
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_models_migration.py -v`
Expected: FAIL（表不存在）

- [ ] **Step 3: 实现 11 个模型**

约定：`Mapped[...]` + `mapped_column`；字符串列显式给 `String(n)` 长度；`create_time`/`update_time` 用 `server_default=func.now()` 与 `onupdate=func.now()`；`del_flag` 用 `server_default="0"`；`SysUser` 与 `SysRole`、`SysDept` 之间用 `relationship(..., lazy="selectin")` 挂 `roles`/`dept`，避免异步下的隐式懒加载（`MissingGreenlet`）。`sys_user.dept_id` 与 `sys_user_token.user_id` 建**普通索引**。

- [ ] **Step 4: 生成并审查迁移**

Run:
```powershell
cd D:\work\enterprise-admin\backend
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "core auth tables"
```
审查生成的 `versions\*.py`：表名/列长度/索引/`server_default` 是否正确；把文件名改为 `0001_core_auth_tables.py` 并设置 `revision = "0001"`、`down_revision = None`。**必须人工核对，autogenerate 会漏 `server_default` 的细节。**

- [ ] **Step 5: 对测试库与开发库执行迁移**

Run:
```powershell
.venv\Scripts\python.exe -m alembic upgrade head
& 'D:\devtools\mysql-8.0.29\bin\mysql.exe' -uroot -pAdmin@123456 enterprise_admin -e "SET NAMES utf8mb4; SOURCE alembic_upgrade_note.sql" 2>$null
```
简化做法：临时把 `.env` 的 `MYSQL_DB` 指向 `enterprise_admin` 执行一次 `alembic upgrade head`，再切回；或用 `alembic -x db=enterprise_admin upgrade head`（`env.py` 支持 `-x db=` 覆盖库名，需在 Step 3 实现）。
Expected: 两库各有 11 张表 + `alembic_version`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_models_migration.py -v`
Expected: 全部 PASS（含逻辑删除与同名重建两条风险用例）

- [ ] **Step 7: Commit**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_models_migration.py
git commit -m "feat(backend): add 11 core ORM models with initial alembic migration"
```

---

### Task 6: 安全模块（bcrypt / JWT / 图形验证码）

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Consumes: Task 2 的 `get_settings()`
- Produces（后续任务只依赖这些签名）：
  - `def hash_password(raw: str) -> str`
  - `def verify_password(raw: str, hashed: str) -> bool`
  - `def create_token(user_id: int, token_type: Literal["access","refresh"], expires_delta: timedelta) -> tuple[str, str]` → `(token, jti)`
  - `def decode_token(token: str, expected_type: Literal["access","refresh"]) -> dict[str, Any]`；类型不符或过期抛 `UnauthorizedException`
  - `def generate_captcha() -> tuple[str, str]` → `(code, base64_png_without_prefix)`；code 为 4 位数字/大写字母，排除易混字符 `0O1Il`

- [ ] **Step 1: 写失败的测试**

```python
def test_password_hash_is_not_plaintext(): ...
def test_verify_password_accepts_correct_and_rejects_wrong(): ...
def test_same_password_hashes_differently(): ...        # 盐随机
def test_access_token_roundtrip_carries_user_id_and_jti(): ...
def test_decode_token_rejects_wrong_type(): ...          # 用 access 当 refresh 必须 401
def test_decode_token_rejects_expired(): ...             # expires_delta = -1s
def test_decode_token_rejects_tampered_signature(): ...
def test_captcha_code_length_and_charset(): ...          # len==4，且不含 0O1Il
def test_captcha_image_is_decodable_png(): ...           # base64 解码后前 8 字节为 PNG 魔数
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_security.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 security.py**

要点：直接用 `bcrypt` 包（不用 passlib，避免其与 bcrypt 4.x 的弃用告警与兼容问题）；JWT 用 `jwt.encode/decode`，`algorithms=["HS256"]`，payload 含 `sub`(str)、`jti`、`type`、`exp`、`iat`；`decode` 捕获 `ExpiredSignatureError`/`InvalidTokenError` 统一转 `UnauthorizedException("登录状态已过期，请重新登录")`——**不回显具体失败原因**。验证码用 `PIL.Image` + `ImageDraw`，尺寸 120×40，画干扰线与噪点。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_security.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat(backend): add password hashing, JWT and captcha security primitives"
```

---

### Task 7: 缓存抽象与内存实现

**Files:**
- Create: `backend/app/core/cache.py`
- Test: `backend/tests/test_cache.py`

**Interfaces:**
- Consumes: 无（纯内存，无外部依赖）
- Produces:
  - `class CacheBackend(Protocol)`：`async def get(self, key: str) -> Any | None`、`async def set(self, key: str, value: Any, ttl: int | None = None) -> None`、`async def delete(self, key: str) -> None`、`async def exists(self, key: str) -> bool`、`async def incr(self, key: str, ttl: int | None = None) -> int`、`async def clear(self) -> None`
  - `class MemoryCache(CacheBackend)`：基于 `dict[str, tuple[Any, float | None]]` + `asyncio.Lock`；惰性过期（读取时判定）+ 定期清理任务；`incr` 在键不存在时以 1 起并套用 ttl
  - 模块级单例 `cache: CacheBackend = MemoryCache()`，供各 service 直接引用（将来换 Redis 只改这一行）

- [ ] **Step 1: 写失败的测试**

```python
async def test_set_and_get(): ...
async def test_get_missing_returns_none(): ...
async def test_expires_after_ttl(): ...            # ttl=1，sleep 1.1 -> None
async def test_delete(): ...
async def test_incr_creates_and_increments(): ...  # 1,2,3
async def test_incr_respects_ttl(): ...
async def test_clear_empties_cache(): ...
async def test_ttl_none_never_expires(): ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_cache.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 cache.py**

`incr` 必须原子（持锁读改写），因为登录失败计数会并发命中。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_cache.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/cache.py backend/tests/test_cache.py
git commit -m "feat(backend): add pluggable cache backend with in-memory TTL implementation"
```

---

### Task 8: 登录链路（验证码 / 登录 / 锁定 / 令牌落库 / 登录日志）

**Files:**
- Create: `backend/app/schemas/common.py`, `backend/app/schemas/auth.py`
- Create: `backend/app/services/log_service.py`, `backend/app/services/auth_service.py`
- Create: `backend/app/api/v1/auth.py`, `backend/app/api/v1/router.py`
- Create: `backend/app/utils/request_info.py`（IP/浏览器/OS 解析）
- Modify: `backend/app/main.py`（挂载 `API_V1_PREFIX` 路由）
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: Task 3 响应/异常、Task 5 模型、Task 6 `security`、Task 7 `cache`
- Produces:
  - `app/schemas/auth.py`：`LoginRequest(username: str, password: str, code: str, uuid: str)`、`LoginResponse(access_token: str, refresh_token: str, expires_in: int, token_type: str = "bearer")`、`CaptchaResponse(uuid: str, img: str, captcha_enabled: bool = True)`
  - `app/services/log_service.py`：`async def record_login_log(db, *, user_name, status, msg, ipaddr, browser, os) -> None`
  - `app/services/auth_service.py`：
    - `async def build_captcha() -> CaptchaResponse`（生成后把 `code` 存 `cache`，key `captcha:{uuid}`，ttl 120）
    - `async def authenticate(db, req: LoginRequest, ip: str, ua: str) -> LoginResponse`
    - `async def revoke_by_access_jti(db, jti: str) -> None`
  - `app/utils/request_info.py`：`def client_ip(request: Request) -> str`、`def parse_user_agent(ua: str) -> tuple[str, str]`（返回 browser, os）
  - 路由：`GET /api/v1/auth/captchaImage` → `success(CaptchaResponse)`；`POST /api/v1/auth/login` → `success(LoginResponse)`

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_auth.py`（fixture 需先播种一个用户，见 Step 3 的 `seed_admin` fixture）：
```python
async def test_captcha_endpoint_returns_uuid_and_png(client): ...
async def test_login_success_returns_two_tokens(client, admin_user): ...
async def test_login_wrong_captcha_fails(client, admin_user): ...
async def test_captcha_is_single_use(client, admin_user):
    # 同一 uuid 第二次使用必须失败
async def test_login_wrong_password_same_message_as_unknown_user(client, admin_user):
    r1 = await client.post("/api/v1/auth/login", json={..., "username": "admin", "password": "wrong"})
    r2 = await client.post("/api/v1/auth/login", json={..., "username": "ghost", "password": "wrong"})
    assert r1.json()["msg"] == r2.json()["msg"] == "用户名或密码错误"   # 不泄漏用户是否存在
async def test_login_locks_after_five_failures(client, admin_user): ...
async def test_successful_login_resets_failure_counter(client, admin_user): ...
async def test_login_of_soft_deleted_user_is_rejected(client, deleted_admin_user): ...
async def test_login_response_does_not_leak_password_hash(client, admin_user): ...
async def test_login_writes_login_log(client, admin_user, db_session): ...
async def test_login_creates_user_token_row(client, admin_user, db_session): ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL（404 / 导入错误）

- [ ] **Step 3: 实现 schemas / services / 路由**

关键规则（不可省略）：
- 验证码：取用即删（`cache.delete`），大小写不敏感比较；缺失/过期 → `BusinessException(400, "验证码已失效，请刷新后重试")`
- 锁定：`cache` 键 `login_fail:{user_name}`，失败自增并设 ttl 600；`incr` 返回值 ≥5 时直接拒绝，消息 `"密码错误次数过多，账号已锁定 10 分钟"`
- 用户查询：`select(SysUser).where(SysUser.user_name == ..., SysUser.del_flag == DelFlagEnum.EXISTS)`（逻辑删除过滤在 Task 5 已全局安装，此处显式再写一次以防过滤未生效）
- 状态校验：`status != '0'` → `BusinessException(400, "账号已停用，请联系管理员")`
- 密码校验失败时，对**不存在用户**也要执行一次 `hash_password` 的等价耗时操作（防时序侧信道）；简单做法：预置一个常量假 hash，对不存在用户用 `verify_password(password, DUMMY_HASH)`
- 成功后：写入 `sys_user_token`（access/refresh 两个 jti）、清零失败计数、更新 `login_ip/login_date`、写成功登录日志
- **响应体绝不含 `password` 字段**（`LoginResponse` 结构天然保证）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas backend/app/services backend/app/api backend/app/utils backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(backend): implement captcha and login with lockout, token persistence and login log"
```

---

### Task 9: 鉴权依赖、令牌刷新与登出

**Files:**
- Create: `backend/app/core/deps.py`
- Modify: `backend/app/api/v1/auth.py`（新增 `profile` / `logout` / `refresh` / `routers` 占位）、`backend/app/services/auth_service.py`
- Test: `backend/tests/test_auth.py`（追加）

**Interfaces:**
- Consumes: Task 8 的 `authenticate`、`create_token`、`decode_token`
- Produces:
  - `app/core/deps.py`：
    - `class CurrentUser`（dataclass）：`user_id: int`、`user_name: str`、`dept_id: int | None`、`is_admin: bool`、`perms: set[str]`
    - `async def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> CurrentUser`
    - `def require_perm(perm: str) -> Callable[..., Awaitable[CurrentUser]]`（返回依赖函数；`is_admin` 直接放行）
    - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)`
  - `auth_service`：`async def refresh_tokens(db, refresh_token: str) -> LoginResponse`（校验 refresh jti 有效 → **把旧记录 `revoked=1`** → 签发新对）；`async def logout(db, current: CurrentUser, access_jti: str) -> None`
  - 路由：`GET /api/v1/auth/profile`、`POST /api/v1/auth/logout`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/routers`

- [ ] **Step 1: 写失败的测试**

```python
async def test_profile_requires_token(client): ...                      # 401
async def test_profile_rejects_garbage_token(client): ...               # 401，且 msg 不区分原因
async def test_profile_returns_user_roles_permissions(client, admin_token): ...
async def test_profile_never_returns_password(client, admin_token): ...
async def test_logout_invalidates_token_immediately(client, admin_token):
    # 登出后同一 token 再访问 profile 必须 401（jti 已撤销）
async def test_refresh_rotates_and_old_refresh_is_rejected(client, admin_user):
    # 第一次刷新成功；用同一个旧 refresh_token 再刷一次必须 401（防重放）
async def test_access_token_cannot_be_used_as_refresh(client, admin_token): ...   # 401
async def test_non_admin_without_perm_gets_403(client, normal_user_token, protected_route): ...
async def test_admin_bypasses_perm_check(client, admin_token, protected_route): ...
```

`protected_route` 用只在 `DEBUG` 下注册的 `GET /__test__/need-perm`，声明 `Depends(require_perm("system:test:view"))`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_auth.py -k "profile or logout or refresh or perm" -v`
Expected: FAIL

- [ ] **Step 3: 实现 deps.py 与刷新/登出逻辑**

要点：`get_current_user` 校验顺序为 ① 无 token → 401 `"未提供身份凭证"`；② 解码失败 → 401；③ `sys_user_token` 中 `access_jti` 不存在或 `revoked=1` 或 `access_expire < now` → 401 `"登录状态已失效，请重新登录"`（**三种失败共用同一消息**）；④ 查用户（含 `del_flag='0'`）与状态；⑤ 装配 `CurrentUser`（`is_admin = any(role.role_key == "admin")`，`perms` 为该用户全部角色菜单 `perms` 去掉空串的集合）。`perms` 查询用一次性 join，避免 N+1。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/deps.py backend/app/api/v1/auth.py backend/app/services/auth_service.py backend/tests/test_auth.py
git commit -m "feat(backend): add auth dependencies with token rotation, logout and permission checks"
```

---

### Task 10: 树构建、路由下发与种子数据

**Files:**
- Create: `backend/app/utils/tree.py`, `backend/app/services/menu_service.py`
- Create: `backend/scripts/seed_data.py`
- Modify: `backend/app/api/v1/auth.py`（实现 `routers`）
- Test: `backend/tests/test_menu.py`

**Interfaces:**
- Consumes: Task 5 的 `SysMenu`、Task 9 的 `CurrentUser`
- Produces:
  - `app/utils/tree.py`：`def build_tree(items: Sequence[T], *, id_field: str, parent_field: str, children_field: str = "children", root_parent: int | None = 0) -> list[dict]`
  - `app/services/menu_service.py`：`async def get_routers(db, user: CurrentUser) -> list[dict]`，返回元素结构 `{"name": str, "path": str, "hidden": bool, "component": str | None, "meta": {"title": str, "icon": str | None}, "children": [...]}`
  - `backend/scripts/seed_data.py`：`async def main() -> None`；可用 `python -m scripts.seed_data` 运行；**幂等**（按业务键 `user_name`/`role_key`/`menu.perms` 判存在则跳过）
  - 种子内容：部门树（总公司 → 研发部/市场部/财务部）；角色 `admin`(超管, data_scope=1)、`dept_manager`(部门主管, data_scope=4)、`staff`(普通员工, data_scope=5)；用户 `admin/Admin@123456`、`manager/Manager@123`、`staff/Staff@123`；菜单树覆盖「系统管理(用户/角色/菜单/部门/岗位)」「监控中心(操作日志/登录日志/在线用户)」及其按钮权限；**另外播种一个 `no_menu` 角色与 `nobody` 用户（无任何菜单）用于 Review Focus 第 5 条验证**

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_menu.py`：
```python
def test_build_tree_nests_children(): ...
def test_build_tree_handles_multiple_roots(): ...
def test_build_tree_ignores_orphans(): ...                 # parent 不存在时归为根或丢弃，行为需固定
async def test_routers_for_admin_is_not_empty(db_session, admin_current_user): ...
async def test_routers_for_role_without_menus_returns_empty_list(db_session, no_menu_current_user):
    assert await get_routers(db_session, no_menu_current_user) == []      # 不是异常、不是 None
async def test_routers_excludes_button_type(db_session, admin_current_user):
    # menu_type == 'F' 的节点不得出现在路由树中
async def test_routers_node_shape(db_session, admin_current_user): ...    # 断言 name/path/component/meta.title 键存在
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_menu.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 tree / menu_service / seed_data**

`build_tree` 的孤儿策略固定为「归入根层级」，并在 docstring 写明（避免实现者自由发挥导致测试与行为不一致）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_menu.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 执行种子数据并验证真实数据**

Run:
```powershell
cd D:\work\enterprise-admin\backend
.venv\Scripts\python.exe -m scripts.seed_data
.venv\Scripts\python.exe -m scripts.seed_data      # 再跑一次验证幂等
```
Expected: 两次都成功；第二次打印 `skipped (already exists)` 类信息，且表中行数不翻倍。

- [ ] **Step 6: 用真实 HTTP 串通登录 → 路由**

Run: 启动 uvicorn，按顺序调用 `captchaImage` → `login` → `routers`（带 access token），`nobody` 用户的 `routers` 应返回 `data: []`。
Expected: admin 拿到非空菜单树；nobody 拿到空数组且 HTTP 200。

- [ ] **Step 7: Commit**

```bash
git add backend/app/utils/tree.py backend/app/services/menu_service.py backend/scripts/seed_data.py backend/app/api/v1/auth.py backend/tests/test_menu.py
git commit -m "feat(backend): add tree builder, dynamic routers endpoint and idempotent seed data"
```

---

### Task 11: 前端脚手架、依赖与工程配置

**Files:**
- Create: `frontend/`（由 `create-vue` 生成后改造）
- Modify: `frontend/vite.config.ts`, `frontend/package.json`, `frontend/tsconfig*.json`
- Create: `frontend/.env.development`, `frontend/.env.production`, `frontend/vitest.config.ts`

**Interfaces:**
- Consumes: Task 2 的后端服务（`http://127.0.0.1:8000`）
- Produces: 可 `npm run dev` 启动的空壳应用；`@` 别名指向 `src`；`/api` 代理到后端；Element Plus 自动导入生效

- [ ] **Step 1: 生成官方基线**

Run（在 `D:\work\enterprise-admin` 下）：
```powershell
$env:npm_config_cache='D:\devtools\caches\npm'
npm config set cache D:\devtools\caches\npm --location=user
npm create vue@latest frontend -- --typescript --router --pinia --eslint --prettier --vitest --force
cd frontend; npm install
```
**注意**：`create-vue` 的交互式提示若无法用 flag 全部跳过，则按其提示选择：TypeScript 是、JSX 否、Router 是、Pinia 是、Vitest 是、E2E 否、ESLint 是、Prettier 是。
Expected: `npm run dev` 可启动并显示欢迎页；`npm run type-check` 通过。

- [ ] **Step 2: 装 Element Plus 与工具链**

Run:
```powershell
npm install element-plus @element-plus/icons-vue axios nprogress pinia-plugin-persistedstate sass -D unplugin-auto-import unplugin-vue-components
```
Expected: 安装成功，`package.json` 出现依赖。

- [ ] **Step 3: 配置 vite.config.ts（写失败的验证方式）**

先确认自动导入尚未生效：在 `src/App.vue` 里直接写 `<el-button>测试</el-button>` 与 `ElMessage.success('hi')`，Run `npm run type-check` → Expected: FAIL（找不到 ElMessage / 组件类型）。

- [ ] **Step 4: 配置并验证**

`vite.config.ts` 要点：`resolve.alias` 的 `@` → `src`；`server.port = 5173`、`server.proxy['/api'] = { target: 'http://127.0.0.1:8000', changeOrigin: true }`；`AutoImport({ imports: ['vue','vue-router','pinia'], resolvers: [ElementPlusResolver()], dts: 'src/types/auto-imports.d.ts' })`；`Components({ resolvers: [ElementPlusResolver()], dts: 'src/types/components.d.ts' })`；`css.preprocessorOptions.scss.additionalData` 注入 Element Plus 变量（若需暗色主题）。
Run: `npm run type-check` → Expected: PASS

- [ ] **Step 5: 验证代理与自动导入连通**

Run: `npm run dev`，浏览器访问 `http://127.0.0.1:5173`，页面出现 Element Plus 按钮；控制台执行 `fetch('/api/v1/auth/captchaImage').then(r=>r.json())` → Expected: 返回后端 JSON（证明代理生效）。

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold Vue3 + TS + Element Plus with vite proxy and auto-import"
```

---

### Task 12: 请求层封装与令牌刷新竞态处理

**Files:**
- Create: `frontend/src/utils/auth.ts`, `frontend/src/utils/request.ts`
- Create: `frontend/src/types/api/common.ts`, `frontend/src/types/api/auth.ts`
- Create: `frontend/src/api/auth.ts`
- Test: `frontend/src/utils/__tests__/request.spec.ts`
- Modify: `frontend/vitest.config.ts`

**Interfaces:**
- Consumes: Task 11 的 axios 与 vite 环境
- Produces:
  - `src/utils/auth.ts`：`getToken() / setToken(t) / removeToken()`、`getRefreshToken() / setRefreshToken(t) / removeRefreshToken()`（`localStorage`，key 前缀 `ea_`）
  - `src/types/api/common.ts`：`interface ApiResult<T> { code: number; msg: string; data: T }`、`interface PageQuery { page_num?: number; page_size?: number }`、`interface PageData<T> { rows: T[]; total: number }`
  - `src/types/api/auth.ts`：`LoginParams`、`LoginResult`、`CaptchaResult`、`UserProfile`、`RouterItem`
  - `src/utils/request.ts`：默认导出 `service`（axios 实例）+ 命名导出 `request`（`get/post/put/del` 泛型方法，返回 `Promise<T>`，已剥离外层 `ApiResult`）；**刷新去重**：模块级 `let refreshing: Promise<string> | null`，401 时若已在刷新则 await 同一个 Promise，否则创建
  - `src/api/auth.ts`：`getCaptcha()`、`login(data)`、`logout()`、`refreshToken(token)`、`getProfile()`、`getRouters()`

- [ ] **Step 1: 写失败的测试**

`src/utils/__tests__/request.spec.ts`：
```ts
it('attaches bearer token to requests', ...)
it('unwraps ApiResult.data on success', ...)
it('throws on business code != 200', ...)
it('refreshes once when three requests get 401 concurrently', async () => {
  // mock adapter：3 个请求都先返回 401，refresh 接口返回新 token，
  // 断言 refreshTokens 被调用次数 === 1，且 3 个请求最终都成功
})
it('clears tokens and redirects when refresh fails', ...)
it('does not attempt refresh for the refresh endpoint itself', ...)   # 防无限递归
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/request.spec.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 auth.ts / request.ts / types / api**

要点：响应拦截器中 `code === 200` 才 resolve `data`；`401` 走刷新分支；刷新失败 `removeToken()` + `router.push('/login')`（用懒 import 打破循环依赖）；非 401 的业务错误统一 `ElMessage.error(msg)` 后 reject；请求拦截器做**防重复提交**（同 method+url+body 的 pending 请求存在时直接 reject 并提示）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/request.spec.ts`
Expected: 全部 PASS（特别是并发刷新只触发一次）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils frontend/src/types frontend/src/api frontend/vitest.config.ts
git commit -m "feat(frontend): add typed axios layer with single-flight token refresh"
```

---

### Task 13: Pinia 状态与路由守卫

**Files:**
- Create: `frontend/src/stores/user.ts`, `app.ts`, `permission.ts`, `index.ts`
- Create: `frontend/src/router/index.ts`, `guard.ts`, `routes.ts`
- Create: `frontend/src/directives/hasPerm.ts`, `hasRole.ts`, `index.ts`（为 P1 预留，本任务先建空实现并注册）
- Modify: `frontend/src/main.ts`
- Test: `frontend/src/stores/__tests__/user.spec.ts`（登录/登出/权限码集合）

**Interfaces:**
- Consumes: Task 12 的 `request`、`api/auth.ts`
- Produces:
  - `useUserStore`：state `token`、`refreshToken`、`profile: UserProfile | null`、`roles: string[]`、`perms: string[]`；actions `login(params)`、`fetchProfile()`、`logout()`、`resetAll()`
  - `useAppStore`：state `sidebarOpened`、`device`；actions `toggleSidebar()`
  - `usePermissionStore`：state `dynamicRoutes: RouteRecordRaw[]`；action `generateRoutes(menus: RouterItem[])`，用 `import.meta.glob('../views/**/*.vue')` 映射 `component` 字符串
  - `router/guard.ts`：白名单 `['/login']`；无 token 且非白名单 → `/login?redirect=`；有 token 访问 `/login` → `/`；有 token 但未加载 profile → `fetchProfile()` + `generateRoutes()` + `addRoute` 循环 + **最后追加 `/:pathMatch(.*)*` 兜底路由**
  - `src/directives/hasPerm.ts`：`v-hasPerm="['system:user:add']"`，不匹配则移除元素

- [ ] **Step 1: 写失败的测试**

```ts
it('login stores access and refresh tokens', ...)
it('fetchProfile fills roles and perms', ...)
it('logout clears tokens, profile and dynamic routes', ...)
it('generateRoutes maps component string to a glob loader', ...)
it('generateRoutes appends catch-all route only after dynamic routes', ...)
it('generateRoutes returns empty list for empty menu input', ...)     // Review Focus 第 5 条
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/stores`
Expected: FAIL

- [ ] **Step 3: 实现 stores / router / guard / directives**

`generateRoutes` 必须能处理：`component` 为空（目录节点，用 `Layout` 或 `RouterView` 占位）、`component === 'Layout'`、以及 `.vue` 路径缺失时降级到 404 组件并 `console.warn`（不得抛异常导致白屏）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run` → Expected: 全部 PASS
Run: `cd frontend && npm run type-check` → Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores frontend/src/router frontend/src/directives frontend/src/main.ts
git commit -m "feat(frontend): add pinia stores, dynamic route generation and navigation guard"
```

---

### Task 14: 后台布局

**Files:**
- Create: `frontend/src/layout/index.vue`, `layout/components/Sidebar/index.vue`, `Sidebar/SidebarItem.vue`, `Navbar.vue`, `AppMain.vue`, `TagsView.vue`
- Create: `frontend/src/styles/index.scss`, `variables.scss`, `transition.scss`
- Create: `frontend/src/views/dashboard/index.vue`, `views/error/404.vue`

**Interfaces:**
- Consumes: Task 13 的 `useAppStore`、`usePermissionStore`、`useUserStore`
- Produces: 可复用的后台壳：左侧菜单（递归渲染多级、可折叠）、顶部导航（面包屑、全屏、用户下拉、退出登录）、多标签页（点击切换、关闭、右键菜单可延后）、内容区 `<router-view>` + `keep-alive`

- [ ] **Step 1: 定义验收标准（本任务无单测，用可观察行为替代）**

验收清单：
1. 登录后进入 `/`，左侧显示后端下发的菜单树，层级正确；
2. 点击菜单可切换页面，URL 与高亮同步；
3. 折叠按钮生效，折叠后仅显示图标；
4. 顶栏用户下拉可退出登录，退出后跳回登录页且**再访问 `/` 会被守卫拦回登录页**；
5. 直接访问不存在的路径显示 404 页而非空白。

- [ ] **Step 2: 实现布局与样式**

要点：侧边栏用 `el-menu` 的 `router` 模式或 `router-link` 包裹；`min-width: 0` 必须加在 flex 子项上，否则长菜单名会把布局撑破（这是同类项目高频布局 bug）；暗色模式用 Element Plus 的 `html.dark` 类切换。

- [ ] **Step 3: 逐条手工验证验收清单**

Run: `npm run dev`，按验收清单 1–5 逐条操作。
Expected: 5 条全部通过；特别确认第 5 条（兜底路由在动态路由之后追加）生效。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layout frontend/src/styles frontend/src/views
git commit -m "feat(frontend): add admin layout with sidebar, navbar, tags-view and 404 fallback"
```

---

### Task 15: 登录页

**Files:**
- Create: `frontend/src/views/login/index.vue`, `views/login/components/CaptchaImage.vue`
- Modify: `frontend/src/router/routes.ts`（确认 `/login` 为静态路由）

**Interfaces:**
- Consumes: Task 12 的 `api/auth.ts`、Task 13 的 `useUserStore`
- Produces: 登录页——用户名/密码/验证码三项 + 表单校验 + 回车提交 + loading 态 + 登录成功跳转 `redirect` 参数指定的路径

- [ ] **Step 1: 定义验收标准**

1. 进入 `/login` 自动请求并展示验证码图片；
2. 点击验证码图片可刷新（重新拉取 uuid）；
3. 空提交触发字段级校验提示，不发请求；
4. 错误验证码/错误密码显示后端返回的 `msg`（如「用户名或密码错误」），且不泄漏账号是否存在；
5. 正确凭据登录后跳转到 `/`（或 `redirect` 指定页），并在 `localStorage` 中能看到 token；
6. 连续输错 5 次后提示账号锁定。

- [ ] **Step 2: 实现登录页**

要点：验证码图片用后端返回的 base64（`data:image/png;base64,...`）；登录成功后先 `userStore.login()` 再 `router.push(redirect || '/')`，**不要用 `window.location.href`**（会丢失 SPA 状态）；错误提示用 `ElMessage.error`，与请求层统一处理互不重复弹窗。

- [ ] **Step 3: 逐条手工验证验收标准 1–6**

Run: `npm run dev`。第 6 条需要真的连错 5 次（可临时把锁定阈值调小验证后再改回，或直接用 `staff` 账号试）。
Expected: 6 条全部通过。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/login frontend/src/router/routes.ts
git commit -m "feat(frontend): add login page with captcha, validation and lockout feedback"
```

---

### Task 16: 一键启停脚本与 README

**Files:**
- Create: `init.ps1`, `start.ps1`, `stop.ps1`, `README.md`
- Modify: `docs/superpowers/specs/2026-10-17-enterprise-admin-design.md`（把 §4 与 §12 的 `初始化.ps1/启动.ps1/停止.ps1` 更正为 ASCII 名，并补一句原因）

**Interfaces:**
- Consumes: Task 1 的 `mysql-ctl.ps1`、Task 2 的 venv、Task 11 的前端、Task 10 的 `seed_data`
- Produces:
  - `init.ps1`：检查 MySQL 在跑 → 建库（若不存在）→ `alembic upgrade head`（开发库与测试库）→ `python -m scripts.seed_data`
  - `start.ps1`：MySQL 未跑则拉起 → 新窗口起 uvicorn（`--host 127.0.0.1 --port 8000`）→ 新窗口起 `npm run dev` → 打印两个 URL 与默认账号
  - `stop.ps1`：停止 uvicorn 与 vite 进程（按端口找 PID）→ 可选 `-IncludeMysql` 一并停 MySQL

- [ ] **Step 1: 实现三个脚本（内容纯 ASCII）**

每个脚本必须有：`$ErrorActionPreference='Stop'`、前置依赖检查（文件/端口/进程）、失败时打印明确英文错误与修复提示、成功时打印下一步该做什么。

- [ ] **Step 2: 冷启动验收（端到端）**

Run（先确保 MySQL 与两个 node/uvicorn 进程都已停止）：
```powershell
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\init.ps1
powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\start.ps1
```
Expected: 打开 `http://127.0.0.1:5173` → 用 `admin / Admin@123456` 登录 → 进入后台看到「系统管理」「监控中心」菜单。这是 **S1 成功标准**。

- [ ] **Step 3: 验证停止脚本**

Run: `powershell -ExecutionPolicy Bypass -File D:\work\enterprise-admin\stop.ps1`
Expected: 8000 与 5173 不再监听；`start.ps1` 能再次成功启动。

- [ ] **Step 4: 写 README.md**

必须包含：项目简介、技术栈、目录结构、环境要求、**首次安装步骤（含 MySQL 便携版下载命令）**、`init.ps1` / `start.ps1` 用法、默认账号表、端口说明、常见问题（端口占用、MySQL 起不来、验证码不显示、npm 缓存位置）、D 盘落位清单。

- [ ] **Step 5: Commit**

```bash
git add init.ps1 start.ps1 stop.ps1 README.md docs/superpowers/specs/2026-10-17-enterprise-admin-design.md
git commit -m "build: add one-command init/start/stop scripts and README"
```

---

### Task 17: P0 验收回归

**Files:**
- Create: `docs/P0验收记录.md`

- [ ] **Step 1: 全量跑自动化测试**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: 全部 PASS，无 warning 导致的失败。
Run: `cd frontend && npx vitest run && npm run type-check && npm run lint`
Expected: 全部通过，零错误。

- [ ] **Step 2: 核对 Review Focus 五条是否都有测试覆盖**

逐条对照：信息泄漏（Task 3/8/9）、逻辑删除与唯一性（Task 5/8）、刷新竞态（Task 9/12）、分页边界（Task 3）、空权限不白屏（Task 10/13）。
Expected: 每条都能指出具体测试名；缺哪条就回到对应任务补测试。

- [ ] **Step 3: 跑通 S1 成功标准并记录**

冷启动 → 登录 → 看到菜单 → 退出登录。把实际输出（pytest 统计、URL、截图路径）写进 `docs/P0验收记录.md`。

- [ ] **Step 4: 核对 D 盘约束**

Run:
```powershell
Get-ChildItem -Path 'D:\work\enterprise-admin' -Recurse -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch 'node_modules|\.venv|\.git\\' } |
  Group-Object { $_.FullName.Split('\')[1] } | Select-Object Name, Count
```
Expected: 无项目文件落在 C 盘；确认 pip/npm 缓存位于 `D:\devtools\caches`。

- [ ] **Step 5: Commit**

```bash
git add docs/P0验收记录.md
git commit -m "docs: record P0 acceptance evidence (tests, cold start, review focus coverage)"
```

---

## 计划自查（Self-Review）

**1. Spec 覆盖**

| Spec 章节 | 覆盖任务 |
|---|---|
| §2.2 MySQL 便携版与运行方式 | Task 1、Task 16 |
| §2.3 版本策略（官方基线定版本） | Task 11 |
| §2.4 缓存抽象 | Task 7 |
| §4 目录结构 | 各任务 Files 块，逐文件对应 |
| §5.2 组织与用户表 | Task 5 |
| §5.3 权限表 | Task 5 |
| §5.5 日志与会话表 | Task 5、Task 8 |
| §6.1 接口级权限 | Task 9 |
| §6.2 菜单/路由级 | Task 10、Task 13、Task 14 |
| §6.3 按钮级权限 | Task 13（指令注册）、P1 实装 |
| §6.4 数据权限 | **P1 计划**（P0 无业务列表查询，无法验证） |
| §7.1 登录流程 | Task 8 |
| §7.2 令牌设计 | Task 8、Task 9、Task 12 |
| §8.1 统一响应与状态码 | Task 3 |
| §8.2 分页 | Task 3 |
| §8.3 接口清单中的 auth 部分 | Task 8、Task 9、Task 10 |
| §9.1–9.2 状态与请求层 | Task 12、Task 13 |
| §9.4 布局 | Task 14 |
| §10 错误处理与日志 | Task 2、Task 3 |
| §11 测试策略 | 各任务的测试步骤；测试库与事务回滚在 Task 4 |
| §12 交付物（README/脚本） | Task 16；docs 三件套在后续期 |
| §13 P0 验收 | Task 17 |

**缺口说明**：§6.4 数据权限、§8.3 的业务接口（用户/角色/菜单/部门/岗位 CRUD）、§9.3 自研组件、§9.5 示例业务模块均属 **P1/P2**，不在本计划范围——这是刻意的分期，不是遗漏。

**2. 步骤扫描**：所有步骤均为单一动作（写测试 / 跑测试看失败 / 实现 / 跑测试看通过 / 手动验证 / 提交）。无「TBD」「处理边界情况」这类空步骤。Task 14、15 无单测，改用可观察的验收清单，避免「写测试覆盖界面」这种含混要求。

**3. 类型一致性**：`success()` / `page()` / `PageParams` / `AppException` 家族 / `CurrentUser`（`user_id, user_name, dept_id, is_admin, perms`）/ `create_token → (token, jti)` / `decode_token(token, expected_type)` / `get_routers(db, user)` / 前端 `request.get<T>` 全计划同名同签名。`build_tree` 的 `id_field/parent_field/children_field` 参数名在 Task 10 内自洽。

**4. Review Focus 覆盖**：五条均已在 Task 3 / 5 / 8 / 9 / 10 / 12 / 13 中落成具体测试（含并发刷新、同名重建、500 不泄漏连接串、空权限返回空数组）。

**5. 篇幅比例**：本计划以签名与断言为主，代码块仅出现在「签名与测试不足以确定实现」处，未逐行转写实现。
