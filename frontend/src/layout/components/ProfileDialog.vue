<script setup lang="ts">
/**
 * 个人中心：改自己的资料、改自己的密码。
 *
 * 这两个动作在导航栏的用户下拉里，而不是「用户管理」页 —— 后者是管理员改别人的地方，
 * 由 `system:user:edit` 保护。这里改的是自己的东西，任何登录用户都能用。
 *
 * 资料表单只包含昵称/邮箱/手机/性别。用户名、状态、部门、角色都不在这里，
 * 因为那些是**管理动作**：自助接口如果能改部门，就等于能自己扩大数据权限。
 */
import { ElMessage } from 'element-plus'
import { reactive, ref, watch } from 'vue'

import { changePassword, updateProfile } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const user = useUserStore()
const tab = ref<'profile' | 'password'>('profile')
const submitting = ref(false)

const visible = ref(props.modelValue)
watch(
  () => props.modelValue,
  (value) => {
    visible.value = value
    if (value) {
      fillProfile()
    }
  },
)
watch(visible, (value) => emit('update:modelValue', value))

// --- 资料 -----------------------------------------------------------------

const profileForm = reactive({
  nick_name: '',
  email: '',
  phonenumber: '',
  sex: '' as '' | '0' | '1' | '2',
})

function fillProfile(): void {
  const me = user.profile
  profileForm.nick_name = me?.nick_name ?? ''
  profileForm.email = me?.email ?? ''
  profileForm.phonenumber = me?.phonenumber ?? ''
  profileForm.sex = (me?.sex as '' | '0' | '1' | '2' | undefined) ?? ''
}

async function submitProfile(): Promise<void> {
  if (!profileForm.nick_name.trim()) {
    ElMessage.warning('昵称不能为空')
    return
  }
  submitting.value = true
  try {
    await updateProfile({
      nick_name: profileForm.nick_name,
      email: profileForm.email || null,
      phonenumber: profileForm.phonenumber || null,
      sex: profileForm.sex || null,
    })
    // 重新拉一次，让导航栏的昵称跟着变
    await user.fetchProfile()
    ElMessage.success('资料已更新')
    visible.value = false
  } finally {
    submitting.value = false
  }
}

// --- 密码 -----------------------------------------------------------------

const passwordForm = reactive({ old_password: '', new_password: '', confirm: '' })

async function submitPassword(): Promise<void> {
  if (passwordForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  submitting.value = true
  try {
    const result = await changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success(
      result.revoked_sessions > 0
        ? `密码已修改，其它 ${result.revoked_sessions} 个会话已失效`
        : '密码已修改',
    )
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm = ''
    visible.value = false
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="个人中心" width="520px">
    <el-tabs v-model="tab">
      <el-tab-pane label="资料" name="profile">
        <el-form :model="profileForm" label-width="80px">
          <el-form-item label="账号">
            <el-input :model-value="user.profile?.user_name" disabled />
          </el-form-item>
          <el-form-item label="昵称">
            <el-input v-model="profileForm.nick_name" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="profileForm.email" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="profileForm.phonenumber" />
          </el-form-item>
          <el-form-item label="性别">
            <el-radio-group v-model="profileForm.sex">
              <el-radio value="0">男</el-radio>
              <el-radio value="1">女</el-radio>
              <el-radio value="2">未知</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <p class="hint">账号、状态、部门与角色由管理员在「用户管理」里维护，只能自助修改上面几项。</p>
      </el-tab-pane>

      <el-tab-pane label="修改密码" name="password">
        <el-form :model="passwordForm" label-width="90px">
          <el-form-item label="原密码">
            <el-input v-model="passwordForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="passwordForm.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="passwordForm.confirm" type="password" show-password />
          </el-form-item>
        </el-form>
        <p class="hint">
          改密码后**其它设备上的登录会立即失效**，当前这个会话保留 ——
          旧密码可能已经泄露时，把别人留在登录态里等于白改。
        </p>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        v-if="tab === 'profile'"
        type="primary"
        :loading="submitting"
        @click="submitProfile"
      >
        保存资料
      </el-button>
      <el-button v-else type="primary" :loading="submitting" @click="submitPassword">
        修改密码
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.hint {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.7;
}
</style>
