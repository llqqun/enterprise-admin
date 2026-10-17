<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getCaptcha } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const user = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const captchaEnabled = ref(true)
const captchaImage = ref('')

const form = reactive({
  // Prefilled for the local demo; the password is deliberately not.
  username: 'admin',
  password: '',
  code: '',
  uuid: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

async function refreshCaptcha(): Promise<void> {
  const result = await getCaptcha()
  captchaEnabled.value = result.captcha_enabled
  captchaImage.value = result.img ? `data:image/png;base64,${result.img}` : ''
  form.uuid = result.uuid
  form.code = ''
}

async function submit(): Promise<void> {
  if (!formRef.value) {
    return
  }
  // `validate()` rejects on invalid input; the field messages are the feedback, so
  // there is nothing to report here.
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  loading.value = true
  try {
    await user.login({ ...form })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch {
    // Every failed attempt consumes its captcha, so a retry with the same code
    // would fail for the wrong reason. The request layer has already surfaced the
    // server's message.
    await refreshCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(refreshCaptcha)
</script>

<template>
  <div class="login">
    <el-card class="login__card" shadow="always">
      <template #header>
        <div class="login__header">
          <h1 class="login__title">enterprise-admin</h1>
          <p class="login__subtitle">企业级后台管理系统</p>
        </div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="账号" clearable>
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            @keyup.enter="submit"
          >
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item v-if="captchaEnabled" prop="code">
          <div class="login__captcha">
            <el-input
              v-model="form.code"
              placeholder="验证码"
              maxlength="6"
              @keyup.enter="submit"
            />
            <img
              v-if="captchaImage"
              class="login__captcha-image"
              :src="captchaImage"
              alt="点击更换验证码"
              title="点击更换验证码"
              @click="refreshCaptcha"
            />
          </div>
        </el-form-item>

        <el-button
          class="login__submit"
          type="primary"
          size="large"
          :loading="loading"
          @click="submit"
        >
          登 录
        </el-button>
      </el-form>

      <p class="login__hint">演示账号：admin / Admin@123456</p>
    </el-card>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(160deg, #1f2a44 0%, #2f4a7a 100%);
}

/* min-width: 0 keeps the card from being stretched by long content, and the fixed
   width keeps it from collapsing on a narrow viewport. */
.login__card {
  width: 420px;
  max-width: calc(100vw - 32px);
  min-width: 0;
}

.login__header {
  text-align: center;
}

.login__title {
  margin: 0;
  font-size: 22px;
  letter-spacing: 1px;
}

.login__subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.login__captcha {
  display: flex;
  gap: 12px;
  width: 100%;
}

.login__captcha-image {
  width: 120px;
  height: 40px;
  cursor: pointer;
  border-radius: 4px;
  flex: 0 0 auto;
}

.login__submit {
  width: 100%;
}

.login__hint {
  margin: 16px 0 0;
  font-size: 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
