import { describe, expect, it } from 'vitest'

import { buildKeepAliveInclude } from '@/utils/keepAlive'

describe('buildKeepAliveInclude', () => {
  it('keeps every opened page, including the one being shown right now', () => {
    const views = [
      { name: 'Dashboard' },
      { name: 'SystemUser' },
      { name: 'SystemRole' },
    ]

    // 最后一项就是当前页。它必须在白名单里：一旦被排除，切回来时缓存会被剔除。
    expect(buildKeepAliveInclude(views)).toEqual(['Dashboard', 'SystemUser', 'SystemRole'])
  })

  it('returns a new array and does not mutate the input', () => {
    const views = [{ name: 'A' }, { name: 'B' }]
    const result = buildKeepAliveInclude(views)

    expect(result).not.toBe(views)
    expect(views).toHaveLength(2)
  })

  it('drops empty names instead of passing them to keep-alive', () => {
    // 空字符串会让 include 里出现一个永远匹配不上的条目，掩盖真正的问题。
    expect(buildKeepAliveInclude([{ name: '' }, { name: 'SystemUser' }])).toEqual(['SystemUser'])
  })

  it('returns an empty list for an empty store', () => {
    // 注意：空 include 意味着「什么都不缓存」，而不是「全都缓存」。
    expect(buildKeepAliveInclude([])).toEqual([])
  })
})
