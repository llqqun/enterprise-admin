<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <h1 class="not-found__code">404</h1>
    <p class="not-found__text">抱歉，你访问的页面不存在或已被移除。</p>
    <el-button type="primary" @click="router.push('/')">返回首页</el-button>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 60vh;
}

.not-found__code {
  margin: 0;
  font-size: 88px;
  line-height: 1;
  color: var(--el-color-primary);
}

.not-found__text {
  margin: 0;
  color: var(--el-text-color-secondary);
}
</style>
