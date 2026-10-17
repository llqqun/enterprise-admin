/**
 * `v-hasPerm="['system:user:add']"` — remove the element when the caller lacks the
 * permission.
 *
 * This hides controls; it does **not** enforce anything. The backend's interface
 * level check is the enforcement, and the two must agree — which they do, because
 * both read permission codes produced by the same backend query.
 */
import type { Directive, DirectiveBinding } from 'vue'

import { useUserStore } from '@/stores/user'
import { hasPermission } from '@/utils/permission'

export const hasPerm: Directive<HTMLElement, string[]> = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string[]>) {
    const required = binding.value ?? []
    if (!hasPermission(useUserStore().perms, required)) {
      el.parentNode?.removeChild(el)
    }
  },
}
