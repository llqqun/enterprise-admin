/**
 * The typed axios layer.
 *
 * Two instances on purpose:
 *   * `service`      — every application call; carries the auth interceptor.
 *   * `refreshClient` — used only for the token refresh. Having no interceptors is
 *     what makes "refresh a 401 from the refresh endpoint" impossible by
 *     construction rather than by a flag that someone can forget to check.
 *
 * The single-flight refresh is what makes `Promise.all([...])` of calls that all
 * hit a 401 behave: three concurrent failures must produce exactly one refresh,
 * not three (which would rotate the refresh token three times and invalidate two
 * of them).
 */
import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiResult } from '@/types/api/common'
import type { LoginResult } from '@/types/api/auth'
import { getAccessToken, getRefreshToken, removeTokens, setTokens } from '@/utils/auth'

const BASE_URL = (import.meta.env.VITE_APP_BASE_API as string | undefined) ?? '/api/v1'
const TIMEOUT_MS = 15_000

/**
 * Side effects the layer needs but does not own. Injectable so tests can assert on
 * them instead of mocking a UI library, and so the router can be swapped in later
 * without this module importing it (which would be a cycle).
 */
export const sessionHooks = {
  notifyError(message: string): void {
    // Auto-imported from Element Plus by unplugin-auto-import at build time.
    ElMessage.error(message)
  },
  onSessionExpired(): void {
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  },
}

function createInstance(): AxiosInstance {
  return axios.create({
    baseURL: BASE_URL,
    timeout: TIMEOUT_MS,
    headers: { 'Content-Type': 'application/json' },
  })
}

export const service = createInstance()
export const refreshClient = createInstance()

/** Marks a request that has already been replayed after a refresh. */
interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

// ---------------------------------------------------------------------------
// Single-flight refresh
// ---------------------------------------------------------------------------

let refreshPromise: Promise<string> | null = null

async function performRefresh(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('no refresh token available')
  }

  const response = await refreshClient.post<ApiResult<LoginResult>>('/auth/refresh', {
    refresh_token: refreshToken,
  })
  const result = response.data.data
  setTokens(result.access_token, result.refresh_token, result.expires_in)
  return result.access_token
}

/**
 * Refresh the access token, collapsing concurrent callers onto one in-flight
 * request. The promise is cleared when it settles so a later expiry can refresh
 * again.
 */
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

// ---------------------------------------------------------------------------
// Interceptors
// ---------------------------------------------------------------------------

service.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

service.interceptors.response.use(
  (response: AxiosResponse<ApiResult<unknown>>) => {
    const payload = response.data
    // A response that is not an envelope (a file download, say) passes through.
    if (payload === null || typeof payload !== 'object' || !('code' in payload)) {
      return response
    }
    if (payload.code === 200) {
      return response
    }
    // HTTP 200 with a non-200 business code: an expected rejection, not a fault.
    sessionHooks.notifyError(payload.msg)
    return Promise.reject(new Error(payload.msg))
  },
  async (error: AxiosError<ApiResult<unknown>>) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status

    if (status === 401 && config && !config._retried) {
      config._retried = true

      let token: string | null = null
      try {
        token = await refreshAccessToken()
      } catch {
        token = null
      }

      if (token === null) {
        // The *refresh* failed, so the session genuinely is over.
        removeTokens()
        sessionHooks.onSessionExpired()
        return await Promise.reject(error)
      }

      config.headers.Authorization = `Bearer ${token}`
      // The replay is deliberately outside the try above. Its own failure returns
      // through this same handler with `_retried` set, so a 403, a 500 or a timeout
      // on the replay is handled as an ordinary request failure rather than
      // destroying a session whose refresh token is still perfectly good.
      return await service.request(config)
    }

    if (status === 401) {
      // A 401 that could not be refreshed away: either the refresh failed above, or
      // the replay was rejected with a token minted moments ago. Either way the
      // stored session cannot be trusted.
      removeTokens()
      sessionHooks.onSessionExpired()
      return await Promise.reject(error)
    }

    const message = error.response?.data?.msg ?? error.message
    sessionHooks.notifyError(message)
    return await Promise.reject(error)
  },
)

// ---------------------------------------------------------------------------
// Typed helpers
// ---------------------------------------------------------------------------

async function unwrap<T>(call: Promise<AxiosResponse<ApiResult<T>>>): Promise<T> {
  const response = await call
  return response.data.data
}

export const request = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return unwrap<T>(service.get(url, config))
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return unwrap<T>(service.post(url, data, config))
  },
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return unwrap<T>(service.put(url, data, config))
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return unwrap<T>(service.delete(url, config))
  },
}
