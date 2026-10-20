<script setup lang="ts">
/**
 * 服务监控。
 *
 * 只读的一次快照，不自动轮询 —— 这个页面的用途是「看一眼现在怎么样」，而不是盯着看。
 * 需要刷新就点「刷新」，否则每 5 秒发一次请求只会让被监控的进程多干点活。
 */
import { onMounted, ref } from 'vue'

import { getServerStatus } from '@/api/monitor/server'
import type { ServerStatus } from '@/api/monitor/server'

const loading = ref(false)
const info = ref<ServerStatus | null>(null)

async function fetchStatus(): Promise<void> {
  loading.value = true
  try {
    info.value = await getServerStatus()
  } finally {
    loading.value = false
  }
}

/**
 * 进度条颜色随占用率变化：<70 正常，<90 警告，再高危险。
 *
 * 用 `color` 而不是 `status`：Element Plus 在设置 `status` 时会用**状态图标替换百分比数字**，
 * 于是内存/交换这两块只剩下一个对勾，看不到具体占用 —— 监控页最该显示的就是数字本身。
 */
function healthColor(percent: number): string {
  if (percent >= 90) {
    return 'var(--el-color-danger)'
  }
  return percent >= 70 ? 'var(--el-color-warning)' : 'var(--el-color-success)'
}

function gb(mb: number): string {
  return `${(mb / 1024).toFixed(1)} GB`
}

function uptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return [days ? `${days} 天` : '', hours ? `${hours} 小时` : '', `${minutes} 分钟`].filter(Boolean).join(' ')
}

onMounted(fetchStatus)
</script>

<template>
  <div v-loading="loading" class="app-container">
    <el-row class="toolbar" :gutter="8">
      <el-button type="primary" @click="fetchStatus">刷新</el-button>
    </el-row>

    <template v-if="info">
      <el-row :gutter="14">
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>CPU</template>
            <el-progress
              type="dashboard"
              :percentage="Math.round(info.cpu.percent)"
              :color="healthColor(info.cpu.percent)"
            />
            <div class="metric">
              <span>{{ info.cpu.cores_logical }} 逻辑核</span>
              <span>{{ info.cpu.cores_physical ?? '—' }} 物理核</span>
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>内存</template>
            <el-progress
              type="dashboard"
              :percentage="Math.round(info.memory.percent)"
              :color="healthColor(info.memory.percent)"
            />
            <div class="metric">
              <span>已用 {{ gb(info.memory.used_mb) }}</span>
              <span>共 {{ gb(info.memory.total_mb) }}</span>
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>交换分区</template>
            <el-progress
              type="dashboard"
              :percentage="Math.round(info.swap.percent)"
              :color="healthColor(info.swap.percent)"
            />
            <div class="metric">
              <span>已用 {{ gb(info.swap.used_mb) }}</span>
              <span>共 {{ gb(info.swap.total_mb) }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="section" shadow="never">
        <template #header>磁盘</template>
        <el-table :data="info.disk" border size="small">
          <el-table-column prop="mount" label="挂载点" min-width="120" />
          <el-table-column prop="fstype" label="文件系统" width="110" />
          <el-table-column label="已用 / 总量" min-width="170">
            <template #default="{ row }">{{ gb(row.used_mb) }} / {{ gb(row.total_mb) }}</template>
          </el-table-column>
          <el-table-column label="占用" min-width="200">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.percent)" :color="healthColor(row.percent)" />
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-row :gutter="14">
        <el-col :span="12">
          <el-card class="section" shadow="never">
            <template #header>运行时</template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="Python">{{ info.runtime.python }}（{{ info.runtime.implementation }}）</el-descriptions-item>
              <el-descriptions-item label="操作系统">{{ info.runtime.platform }}</el-descriptions-item>
              <el-descriptions-item label="主机名">{{ info.runtime.hostname }}</el-descriptions-item>
              <el-descriptions-item label="进程号">{{ info.process.pid }}</el-descriptions-item>
              <el-descriptions-item label="已运行">{{ uptime(info.process.uptime_seconds) }}</el-descriptions-item>
              <el-descriptions-item label="启动于">{{ info.process.started_at }}</el-descriptions-item>
              <el-descriptions-item label="进程内存">{{ info.process.rss_mb }} MB</el-descriptions-item>
              <el-descriptions-item label="线程数">{{ info.process.threads }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card class="section" shadow="never">
            <template #header>依赖版本</template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item v-for="(ver, name) in info.packages" :key="name" :label="name">
                {{ ver ?? '未安装' }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <div class="count-hint">
        数据来自本机 psutil 的一次采样。页面不自动刷新 —— 需要最新值请点「刷新」。
      </div>
    </template>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.section {
  margin-top: 14px;
}
.metric {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.count-hint {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
