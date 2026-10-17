<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'

import { useAppStore } from '@/stores/app'
import AppMain from './components/AppMain.vue'
import AppNavbar from './components/AppNavbar.vue'
import Sidebar from './components/Sidebar/index.vue'
import TagsView from './components/TagsView.vue'

const app = useAppStore()

const MOBILE_BREAKPOINT = 768

function syncDevice(): void {
  app.setDevice(window.innerWidth < MOBILE_BREAKPOINT ? 'mobile' : 'desktop')
}

onMounted(() => {
  syncDevice()
  window.addEventListener('resize', syncDevice)
})

onUnmounted(() => {
  window.removeEventListener('resize', syncDevice)
})

const asideWidth = computed(() =>
  app.sidebarOpened ? 'var(--ea-aside-width)' : 'var(--ea-aside-collapsed-width)',
)
</script>

<template>
  <div class="layout">
    <aside class="layout__aside" :style="{ width: asideWidth }">
      <Sidebar />
    </aside>

    <div class="layout__body">
      <header class="layout__header">
        <AppNavbar />
        <TagsView />
      </header>
      <main class="layout__main">
        <AppMain />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/*
 * min-width: 0 on both flex children is load-bearing: a flex item's automatic
 * minimum size is its content's min-content width, and a long menu label or a wide
 * table would otherwise stretch the track and push the content area off-screen.
 */
.layout__aside {
  flex: 0 0 auto;
  min-width: 0;
  overflow: hidden auto;
  background-color: #1f2a44;
  transition: width 0.25s;
}

.layout__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.layout__header {
  flex: 0 0 auto;
}

.layout__main {
  flex: 1 1 auto;
  min-height: 0;
  padding: 12px;
  overflow: auto;
}
</style>
