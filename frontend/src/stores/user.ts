/** The signed-in user: tokens, profile, roles and permission codes. */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getProfile, login as loginApi, logout as logoutApi } from '@/api/auth'
import type { LoginParams, ProfileResult, UserProfile } from '@/types/api/auth'
import { getAccessToken, getRefreshToken, removeTokens, setTokens } from '@/utils/auth'
import { usePermissionStore } from '@/stores/permission'

export const useUserStore = defineStore('user', () => {
  // Seeded from storage so a page refresh keeps the session without a round trip.
  const accessToken = ref<string | null>(getAccessToken())
  const refreshToken = ref<string | null>(getRefreshToken())
  const profile = ref<UserProfile | null>(null)
  const roles = ref<string[]>([])
  const perms = ref<string[]>([])
  /**
   * Whether the session has been hydrated from the server.
   *
   * A dedicated flag rather than "roles is non-empty": an account holding no enabled
   * role legitimately has `roles: []`, and using that as the sentinel made the
   * navigation guard re-hydrate and replay the same navigation forever.
   */
  const hydrated = ref(false)

  const isLoggedIn = computed(() => Boolean(accessToken.value))

  async function login(params: LoginParams): Promise<void> {
    const result = await loginApi(params)
    setTokens(result.access_token, result.refresh_token, result.expires_in)
    accessToken.value = result.access_token
    refreshToken.value = result.refresh_token
  }

  async function fetchProfile(): Promise<ProfileResult> {
    const result = await getProfile()
    profile.value = result.user
    roles.value = result.roles
    perms.value = result.permissions
    hydrated.value = true
    return result
  }

  function resetAll(): void {
    removeTokens()
    accessToken.value = null
    refreshToken.value = null
    profile.value = null
    roles.value = []
    perms.value = []
    hydrated.value = false
    // Dynamic routes belong to the session that produced them.
    usePermissionStore().resetRoutes()
  }

  async function logout(): Promise<void> {
    try {
      await logoutApi()
    } catch {
      // The server may be unreachable or the token already revoked. Either way the
      // local session ends: refusing to log out because the network is down is the
      // wrong failure mode.
    } finally {
      resetAll()
    }
  }

  return {
    accessToken,
    refreshToken,
    profile,
    roles,
    perms,
    hydrated,
    isLoggedIn,
    login,
    fetchProfile,
    logout,
    resetAll,
  }
})
