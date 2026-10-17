/** UI shell state: sidebar, theme, and the device class the layout adapts to. */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type DeviceType = 'desktop' | 'mobile'

export const useAppStore = defineStore('app', () => {
  const sidebarOpened = ref(true)
  const device = ref<DeviceType>('desktop')
  const dark = ref(false)

  /** Flip the sidebar, or force it to a known state. */
  function toggleSidebar(value?: boolean): void {
    sidebarOpened.value = value ?? !sidebarOpened.value
  }

  function setDevice(next: DeviceType): void {
    device.value = next
    if (next === 'mobile') {
      sidebarOpened.value = false
    }
  }

  function toggleDark(value?: boolean): void {
    dark.value = value ?? !dark.value
    document.documentElement.classList.toggle('dark', dark.value)
  }

  return { sidebarOpened, device, dark, toggleSidebar, setDevice, toggleDark }
})
