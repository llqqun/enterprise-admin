/** One Pinia instance, created here so `main.ts` and tests share the shape. */
import { createPinia } from 'pinia'

const pinia = createPinia()

export default pinia

export { useAppStore } from './app'
export { usePermissionStore } from './permission'
export { useUserStore } from './user'
