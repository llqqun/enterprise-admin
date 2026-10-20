<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <h1 class="not-found__code">404</h1>
    <p class="not-found__text">抱歉，你访问的页面不存在或已被移除。</p>
    <p class="not-found__hint">
      如果你是从左侧菜单点进来的，那多半是这个模块还没有实现 —— 字典、参数、公告、操作日志、
      登录日志、在线用户、文件管理属于设计文档里的 P2 阶段，菜单按设计建好了，页面尚未落地。
    </p>
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

.not-found__hint {
  max-width: 560px;
  margin: 0;
  padding: 0 16px;
  text-align: center;
  line-height: 1.7;
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}
</style>
