<script setup lang="ts">
/**
 * 按字典把值渲染成带颜色的标签。
 *
 * 用法：`<DictTag dict-type="sys_normal_disable" :value="row.status" />`
 *
 * 字典里查不到这个值时**原样显示值**，而不是留空或显示「未知」——原样显示能让人立刻发现
 * 「字典缺了这一项」，而显示「未知」会把配置问题伪装成正常现象。
 */
import { computed } from 'vue'

import { useDict } from '@/composables/useDict'

const props = defineProps<{
  dictType: string
  value: string | number | null | undefined
}>()

const options = useDict(props.dictType)

const matched = computed(() =>
  options.value.find((item) => String(item.dict_value) === String(props.value ?? '')),
)

type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

const tagType = computed<TagType | undefined>(() => {
  const raw = matched.value?.tag_type
  if (!raw) {
    return undefined
  }
  return raw as TagType
})
</script>

<template>
  <el-tag v-if="matched" :type="tagType" disable-transitions>{{ matched.dict_label }}</el-tag>
  <span v-else class="dict-tag__raw">{{ value ?? '—' }}</span>
</template>

<style scoped>
.dict-tag__raw {
  color: var(--el-text-color-secondary);
}
</style>
