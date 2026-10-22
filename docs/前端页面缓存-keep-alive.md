# 页面缓存（keep-alive）方案与踩坑记录

> 本文对应 `frontend/src/layout/components/AppMain.vue`、`stores/permission.ts`、
> `utils/keepAlive.ts`。所有结论都在浏览器里实测过（Chrome + Vue DevTools 可见的
> `__v_cache` 内部状态）。

## 一、想解决什么问题

后台管理系统的典型诉求：**在 A 页填了一半表单，切到 B 页看一眼，再切回 A 时内容还在。**

`<keep-alive>` 做的是「不销毁组件实例，只把它从 DOM 上摘下来」。组件实例还在，`v-model`
绑定的响应式数据就还在，所以回来时表单自然保留了。

## 二、本项目的最终实现

```vue
<!-- AppMain.vue -->
<router-view v-slot="{ Component, route: current }">
  <transition name="fade-transform" mode="out-in">
    <keep-alive :include="cachedViews">
      <component :is="Component" :key="current.path" />
    </keep-alive>
  </transition>
</router-view>
```

```ts
// cachedViews 来自标签页列表，包含当前页
const cachedViews = computed(() => buildKeepAliveInclude(tagsView.visitedViews))
```

三个条件缺一不可，而且**缺任何一个都不会报错**，只会静默地每次都重建组件：

| 条件 | 不满足时的现象 |
|---|---|
| `include` 里的名字 = **组件名** | 缓存永远不命中，页面每次重建 |
| `include` 包含**当前页** | 切回该页时缓存被剔除，输入丢失 |
| `<keep-alive>` 里只有**一个**子节点 | 开发模式直接 500：`<KeepAlive> expects exactly one child component.` |

## 三、这个项目实际踩到的三个坑

### 坑 1：`include` 里放的是路由名，组件名却是 `index`

`<keep-alive include>` 匹配的是**组件名**（`component.name`），不是路由名。

后端下发的菜单名是 `SystemUser` 这样的路由名，而页面文件统一叫 `index.vue`，
SFC 编译器据此推断的组件名是 `index`：

- `include: ['SystemUser']` —— 永远匹配不上；
- `include: ['index']` —— 更糟，所有页面共用一个名字。

**解法**：在把后端字符串解析成组件时（`stores/permission.ts`），顺手把路由名挂到组件上：

```ts
function withRouteName(loader: () => Promise<unknown>, routeName: string) {
  return async () => {
    const mod = (await loader()) as Record<string, unknown> | undefined
    const component = (mod?.default ?? mod) as { name?: string } | undefined
    if (component && typeof component === 'object' && !component.name) {
      component.name = routeName   // name 优先于 __name，include 从此能匹配
    }
    return mod
  }
}
```

好处是**后端以后新增菜单不需要再动前端**：路由名与组件名在这一处自动对齐。

替代做法是每个页面写 `defineOptions({ name: 'SystemUser' })`。它更显式，但要求
页面名与后端 `route_name` 手工保持一致，漏一次就静默不缓存（而且不报错）。

### 坑 2：把「当前页」排除在 `include` 之外

原始实现里有这么一行：

```ts
.filter((name) => name !== route.name)   // 错
```

意图大概是「当前页不用缓存」。但 `include` 是白名单：名字不在里面的组件会被
**立刻销毁**。于是从 B 切回 A 的瞬间，A 的名字正好被排除 → 缓存被清 → 页面重建 →
输入丢失。这个 bug 的症状与「没写 keep-alive」完全一样，很容易误判。

**解法**：`include` 包含**所有已打开标签页**，包括当前页。规则抽到
`utils/keepAlive.ts`，并有单元测试断言「最后一项（当前页）必须在结果里」。

### 坑 3：`<keep-alive>` 内部的 HTML 注释

```vue
<keep-alive>
  <!-- 这里写说明 -->
  <component :is="Component" :key="current.path" />
</keep-alive>
```

开发模式下模板注释是**保留**的（生产构建才剥离），`<keep-alive>` 于是认为自己有两个子节点：

```
<KeepAlive> expects exactly one child component.
```

坑在于：`npm run build` **能通过**（注释被剥掉），只有 dev 报错。说明只写在
`<script setup>` 的头部注释里。

## 四、实测证据

| 验证项 | 结果 |
|---|---|
| 在「用户管理」输入 `MARK-5` → 切「角色管理」→ 切回 | 输入值仍是 `MARK-5`；且 `.el-table__body` 是**同一个 DOM 节点**（说明组件没重建） |
| 切走时被缓存页面的 DOM | `isConnected === true`（挂在隐藏容器里，未销毁） |
| 关闭「用户管理」标签页 | `include` 收缩 → Vue 自动剔除该缓存项 |
| 关闭后重新打开「用户管理」 | 输入为空、重新请求列表 —— 确实是全新实例 |
| 连续关闭两个标签页 | store 与 DOM 同步（5→4→3），无残留 |

## 五、keep-alive 配 vue-router 的常见问题

### 1. 名字对不上（最高频）
见坑 1。**判断方法**：在 Vue DevTools 里选中页面组件，看它显示的名字；与 `include`
数组里的值对比。名字不同就不缓存，且没有任何警告。

### 2. 同一组件被多个路由复用
`/user/1`、`/user/2` 若共用一个组件，`include` 只能按名字匹配，两者会**共用一个缓存实例**，
后访问的复用前一个实例的数据。解法：

- 路由名与组件名一一对应（本项目的做法，一个页面一个路由）；
- 或者用 `:key="route.fullPath"` 区分实例（代价：每个参数组合一个缓存副本）；
- 或者干脆不走 keep-alive，用「进入时按参数重新拉数据 + 表单状态放 Pinia」。

### 3. `key` 选错：缓存爆炸或数据串台
- `:key="route.fullPath"` → 每次换 query 都新建实例并缓存，内存只增不减；
- `:key="route.path"` → 换 query 复用实例，需要配合 `onActivated` 刷新数据（本项目用这个）。

### 4. 缓存项取不回来（没有「清理单个」API）
`keep-alive` 没有 `remove(name)` 这样的方法。**唯一的官方途径是改 `include`**：
把名字移出数组，Vue 会同步销毁该项。所以「关闭标签页 = 清缓存」必须落在
`include` 上（本项目的 `removeView` → `include` 收缩 → 自动剔除）。

### 5. 数据陈旧
组件不重建 → `onMounted` 只跑一次 → 别处改了数据，切回来还是旧的。解法：

```ts
onActivated(() => { void fetchList() })   // 每次激活刷新列表
```
表单数据在 setup 作用域里，刷新列表不会清空它 —— 这正是「保留草稿 + 数据不过期」的组合。
本项目**尚未**给各列表页统一加这一层，属于已知空白。

### 6. 后台任务泄漏
被缓存的页面不会卸载，`setInterval`、`addEventListener`、WebSocket 订阅会一直跑。
必须成对处理：

```ts
onActivated(() => startPolling())
onDeactivated(() => stopPolling())
onUnmounted(() => stopPolling())   // 关闭标签页时
```

### 7. 内存增长
缓存的是整个组件实例 + DOM 树。开二十个标签页，就是二十份。可选手段：
`<keep-alive :max="10">`（超出按 LRU 淘汰）、只缓存关键页、或关闭标签时及时剔除。

### 8. 与 `<transition>` 的嵌套顺序
必须是 `<transition>` 在外、`<keep-alive>` 在内。反过来（`<keep-alive>` 包 `<transition>`）
动画会失效。另外 `mode="out-in"` 会让离场动画先播完再挂新页，切换稍慢但不会重叠。

### 9. 嵌套路由只缓存了外层
`<keep-alive>` 只对它**直接子节点**生效。多级 `router-view` 里，要在每一层需要缓存的
地方各自包一个 `keep-alive`，否则深层页面不会被缓存。

### 10. 动态路由下 `include` 与后端不同步
菜单由后端下发时，前端容易忘记把新页面的名字加进去。解法是像本项目一样
**从路由记录派生**名称，而不是手写一份白名单。

## 六、其它缓存页面的方案

| 方案 | 原理 | 优点 | 缺点 | 适用 |
|---|---|---|---|---|
| **keep-alive + include**（本项目） | 组件实例不销毁 | 保留一切状态（输入、滚动、展开行） | 名字匹配脆弱；内存随标签数增长；数据易陈旧 | 表单多、切换频繁的后台 |
| **状态提到 Pinia** | 组件照常销毁，数据在 store 里 | 与生命周期解耦；刷新页面也能恢复（配合持久化） | 要手写「哪些字段存 store」；DOM 状态（滚动、展开）丢失 | 表单草稿、跨页选择的筛选条件 |
| **sessionStorage / localStorage** | 序列化表单值 | 刷新、换标签页都能恢复 | 手动序列化；有大小与安全性限制 | 长表单、防误关页面 |
| **同时渲染所有已打开页面（`v-show` 栈）** | 不用 keep-alive，标签页切显示/隐藏 | 连 DOM/滚动都保留；逻辑最简单可预测 | 内存占用最大；所有页面同时在跑副作用；需要自己管理挂载 | 标签页不多、且强依赖「绝对不丢」 |
| **手动 VNode 缓存（`Map<path, VNode>`）** | 自己存 vnode 并渲染 | 可精确控制淘汰策略 | 实现复杂、易与响应式系统打架 | 框架层/组件库内部 |
| **只缓存「查询条件」** | 把筛选条件放 query string | 可分享、可前进后退、刷新不丢 | 不适合富文本类大表单 | 列表页筛选 |
| **不缓存，进入即重取** | 每次重建 | 数据永远新；内存稳定 | 用户体验差（重新填/重新翻页） | 强实时页面（如监控） |

**选择建议**：

1. 只有几个字段的筛选条件 → 放 URL query，最省事且刷新不丢；
2. 表单草稿、跨页选择 → 放 Pinia；
3. 确实需要「切回来连滚动位置都在」→ keep-alive；
4. 页面数量可控且要求绝对不丢 → `v-show` 栈；
5. **不要**为了「少写几行状态管理」上 keep-alive —— 它带来的问题是隐性的
   （名字不匹配不报错、数据陈旧、副作用泄漏），排查成本远高于显式管理状态。

## 七、本项目的已知空白

1. 列表页尚未统一加 `onActivated` 刷新，**缓存页的数据可能陈旧**（见问题 5）。
2. 尚未使用 `:max` 限制缓存数量，标签页很多时内存会持续增长（见问题 7）。
3. `:key` 用 `route.path`，同一页面不同 query 会复用实例；若将来需要按 query 区分，
   要改成 `fullPath` 并同步调整标签页的去重口径。
