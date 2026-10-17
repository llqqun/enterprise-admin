<script setup lang="ts">
/**
 * Renders the current route, keeping visited pages alive so a tab switch does not
 * lose form state.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useTagsViewStore } from '@/stores/tagsView'

const route = useRoute()
const tagsView = useTagsViewStore()

/** Names of the views that should stay mounted. */
const cachedViews = computed(() =>
  tagsView.visitedViews
    .filter((view) => view.closable)
    .map((view) => view.name)
    .filter((name) => name !== route.name),
)
</script>

<template>
  <router-view v-slot="{ Component, route: current }">
    <transition name="fade-transform" mode="out-in">
      <keep-alive :include="cachedViews">
        <component :is="Component" :key="current.path" />
      </keep-alive>
    </transition>
  </router-view>
</template>
