<script setup lang="ts">
// Temporary probe for Task 11: Element Plus components and APIs must resolve
// through auto-import before this file can compile. Replaced in Task 13.
function ping(): void {
  ElMessage.success('auto-import works')
}
</script>

<template>
  <el-button type="primary" @click="ping">probe</el-button>
  <el-icon><Setting /></el-icon>
</template>

<style scoped></style>
