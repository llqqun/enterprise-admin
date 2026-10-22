/**
 * keep-alive 的 `include` 列表。
 *
 * 从标签页列表派生，而不是在组件里现拼 —— 这样「哪些页面该保留」只有一个来源，
 * 而且这条规则可以被单元测试钉住。
 */
import type { VisitedView } from '@/stores/tagsView'

/**
 * 取所有已打开标签页的组件名，**包含当前页**。
 *
 * 为什么强调「包含当前页」：`<keep-alive :include>` 的语义是白名单，名字一旦不在里面，
 * Vue 会立刻把该组件从缓存中剔除并销毁。如果按「当前页不需要缓存」的思路把当前路由
 * 排除掉，那么从 B 切回 A 的瞬间 A 的名字正好不在白名单里 —— 缓存被清掉，页面重建，
 * 用户刚输入的内容随之丢失。这个 bug 曾经真实存在过，所以用测试守住。
 */
export function buildKeepAliveInclude(views: readonly Pick<VisitedView, 'name'>[]): string[] {
  return views
    .map((view) => view.name)
    .filter((name): name is string => typeof name === 'string' && name.length > 0)
}
