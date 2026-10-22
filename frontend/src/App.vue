<script setup lang="ts">
/**
 * Application shell. Everything visible is a route: the guard decides between the
 * login page and the authenticated layout, so this file has nothing else to do.
 *
 * 外面这层 `el-config-provider` 是给 Element Plus 配中文的。没有它，组件自带的文案
 * （确认框的 Cancel / OK、分页的 per page、日期选择器等）会保持英文，而界面其余部分都是中文 ——
 * 这种混搭只有真的点开一次确认框才看得见，代码审查与单元测试都不会报。
 *
 * 用 `ElConfigProvider` 而不是 `app.use(ElementPlus)`，是为了不把整个组件库一次性注册进来：
 * 组件本来由 unplugin 按需自动导入。
 */
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>

<template>
  <el-config-provider :locale="zhCn">
      <router-view></router-view>
  </el-config-provider>
</template>
