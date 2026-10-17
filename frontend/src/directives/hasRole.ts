/** `v-hasRole="['admin']"` — remove the element when the caller lacks the role. */
import type { Directive, DirectiveBinding } from 'vue'

import { useUserStore } from '@/stores/user'
import { hasRole as checkRoles } from '@/utils/permission'

export const hasRole: Directive<HTMLElement, string[]> = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string[]>) {
    const required = binding.value ?? []
    if (!checkRoles(useUserStore().roles, required)) {
      el.parentNode?.removeChild(el)
    }
  },
}
