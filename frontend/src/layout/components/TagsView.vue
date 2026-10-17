<script setup lang="ts">
/** Open-tab bar; every visited authenticated route gets a tag. */
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useTagsViewStore } from '@/stores/tagsView'

const route = useRoute()
const router = useRouter()
const tagsView = useTagsViewStore()

watch(
  () => route.fullPath,
  () => {
    if (route.name) {
      tagsView.addView(route)
    }
  },
  { immediate: true },
)

async function close(path: string): Promise<void> {
  const wasActive = path === route.fullPath
  tagsView.removeView(path)
  if (wasActive) {
    const last = tagsView.visitedViews[tagsView.visitedViews.length - 1]
    await router.push(last ? last.path : '/')
  }
}
</script>

<template>
  <div class="tags-view">
    <el-tag
      v-for="view in tagsView.visitedViews"
      :key="view.path"
      class="tags-view__item"
      :effect="view.path === route.fullPath ? 'dark' : 'plain'"
      :closable="view.closable"
      size="small"
      @click="router.push(view.path)"
      @close="close(view.path)"
    >
      {{ view.title }}
    </el-tag>
  </div>
</template>

<style scoped>
.tags-view {
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--ea-tags-height);
  padding: 0 12px;
  overflow-x: auto;
  overflow-y: hidden;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.tags-view__item {
  flex: 0 0 auto;
  cursor: pointer;
}
</style>
