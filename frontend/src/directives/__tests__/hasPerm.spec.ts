/** Permission directives: they hide, they do not enforce. */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h, withDirectives } from 'vue'

import { hasPerm } from '@/directives/hasPerm'
import { hasRole } from '@/directives/hasRole'
import { useUserStore } from '@/stores/user'

/** A component rendered with `withDirectives`, so no template compiler is needed. */
function probe(directive: typeof hasPerm, value: string[]) {
  return defineComponent({
    render() {
      return h('div', [
        withDirectives(h('button', { id: 'target' }, 'action'), [[directive, value]]),
        h('span', { id: 'sibling' }, 'keep me'),
      ])
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('v-hasPerm', () => {
  it('keeps the element when the permission is held', () => {
    const user = useUserStore()
    user.perms = ['system:user:add']

    const wrapper = mount(probe(hasPerm, ['system:user:add']))

    expect(wrapper.find('#target').exists()).toBe(true)
  })

  it('removes the element when the permission is missing', () => {
    const user = useUserStore()
    user.perms = ['system:user:list']

    const wrapper = mount(probe(hasPerm, ['system:user:add']))

    expect(wrapper.find('#target').exists()).toBe(false)
    expect(wrapper.find('#sibling').exists()).toBe(true)
  })

  it('treats the wildcard as "everything"', () => {
    const user = useUserStore()
    user.perms = ['*:*:*']

    const wrapper = mount(probe(hasPerm, ['system:anything:do']))

    expect(wrapper.find('#target').exists()).toBe(true)
  })

  it('accepts any one of several codes', () => {
    const user = useUserStore()
    user.perms = ['system:user:edit']

    const wrapper = mount(probe(hasPerm, ['system:user:add', 'system:user:edit']))

    expect(wrapper.find('#target').exists()).toBe(true)
  })

  it('removes the element when nothing is granted', () => {
    const user = useUserStore()
    user.perms = []

    const wrapper = mount(probe(hasPerm, ['system:user:add']))

    expect(wrapper.find('#target').exists()).toBe(false)
  })
})

describe('v-hasRole', () => {
  it('keeps the element when the role is held', () => {
    const user = useUserStore()
    user.roles = ['admin']

    const wrapper = mount(probe(hasRole, ['admin']))

    expect(wrapper.find('#target').exists()).toBe(true)
  })

  it('removes the element when the role is missing', () => {
    const user = useUserStore()
    user.roles = ['staff']

    const wrapper = mount(probe(hasRole, ['admin']))

    expect(wrapper.find('#target').exists()).toBe(false)
  })
})
