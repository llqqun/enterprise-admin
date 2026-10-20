/**
 * 字典读取与缓存。
 *
 * 字典在页面里出现的频率很高（状态列、性别列、下拉框），而它几乎不变。所以按 `dictType`
 * 缓存**整个 Promise**：并发的十个组件同时要 `sys_normal_disable`，只会发一次请求。
 * 缓存的是 Promise 而不是结果，是为了让并发调用共享同一次飞行。
 */
import { ref } from 'vue'

import { dictByType } from '@/api/system/dict'
import type { DictDataRow } from '@/api/system/dict'

const cache = new Map<string, Promise<DictDataRow[]>>()

/** 取一个字典的全部启用项。失败时返回空数组 —— 标签渲染不出来不该让整页崩掉。 */
export function loadDict(dictType: string): Promise<DictDataRow[]> {
  const cached = cache.get(dictType)
  if (cached) {
    return cached
  }
  const pending = dictByType(dictType)
    .then((rows) => rows)
    .catch(() => {
      // 失败不缓存，下一次还会重试；否则一次网络抖动会让这个字典永久为空。
      cache.delete(dictType)
      return [] as DictDataRow[]
    })
  cache.set(dictType, pending)
  return pending
}

/** 显式失效：字典维护页改完之后要调用它，否则别的页面还显示旧标签。 */
export function invalidateDict(dictType?: string): void {
  if (dictType) {
    cache.delete(dictType)
  } else {
    cache.clear()
  }
}

/** 组件里用的响应式包装。 */
export function useDict(dictType: string) {
  const options = ref<DictDataRow[]>([])
  void loadDict(dictType).then((rows) => {
    options.value = rows
  })
  return options
}
