import type { App } from 'vue'

import { hasPerm } from './hasPerm'
import { hasRole } from './hasRole'

/** Register `v-hasPerm` and `v-hasRole` globally. */
export function setupDirectives(app: App): void {
  app.directive('hasPerm', hasPerm)
  app.directive('hasRole', hasRole)
}

export { hasPerm, hasRole }
