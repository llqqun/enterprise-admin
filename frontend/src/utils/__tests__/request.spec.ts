/**
 * The typed axios layer, and the single-flight refresh that keeps concurrent 401s
 * from each triggering their own refresh.
 *
 * The adapter is mocked rather than the module: the behaviour under test is the
 * interceptor chain, and mocking `axios` itself would replace the thing being
 * checked.
 *
 * NOTE for anyone extending this file: a custom axios adapter must reject non-2xx
 * itself. `validateStatus` lives inside the *default* adapter, so returning a 401
 * response object resolves the promise and the error interceptor never runs.
 */
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getAccessToken, getRefreshToken, removeTokens, setTokens } from '@/utils/auth'
import { refreshClient, request, service, sessionHooks } from '@/utils/request'

const REFRESH_URL = '/auth/refresh'

interface Reply {
  status: number
  payload: unknown
}

type Responder = (config: InternalAxiosRequestConfig) => Reply

function envelope<T>(data: T, msg = '操作成功'): Reply {
  return { status: 200, payload: { code: 200, msg, data } }
}

function failure(status: number, msg: string): Reply {
  return { status, payload: { code: status, msg, data: null } }
}

/** Install a responder on both instances the module talks through. */
function useResponder(responder: Responder): void {
  const adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    const { status, payload } = responder(config)
    const response: AxiosResponse = {
      data: payload,
      status,
      statusText: String(status),
      headers: {},
      config,
    }
    if (status >= 200 && status < 300) {
      return response
    }
    const message = (payload as { msg?: string } | null)?.msg ?? `Request failed: ${status}`
    throw new AxiosError(message, 'ERR_BAD_REQUEST', config, {}, response)
  }
  service.defaults.adapter = adapter
  refreshClient.defaults.adapter = adapter
}

function bearer(config: InternalAxiosRequestConfig): string {
  return String(config.headers.Authorization ?? '')
}

beforeEach(() => {
  localStorage.clear()
  sessionHooks.notifyError = vi.fn<(message: string) => void>()
  sessionHooks.onSessionExpired = vi.fn<() => void>()
})

describe('request layer', () => {
  it('attaches the bearer token to requests', async () => {
    setTokens('access-1', 'refresh-1', 1800)
    let seen = ''
    useResponder((config) => {
      seen = bearer(config)
      return envelope({})
    })

    await request.get('/system/user')

    expect(seen).toBe('Bearer access-1')
  })

  it('unwraps the response envelope', async () => {
    useResponder(() => envelope({ rows: [1, 2], total: 2 }))

    const data = await request.get<{ rows: number[]; total: number }>('/system/user')

    expect(data).toEqual({ rows: [1, 2], total: 2 })
  })

  it('rejects and reports when the business code is not 200', async () => {
    useResponder(() => ({ status: 200, payload: { code: 400, msg: '库存不足', data: null } }))

    await expect(request.post('/system/user', {})).rejects.toThrow('库存不足')
    expect(sessionHooks.notifyError).toHaveBeenCalledWith('库存不足')
  })

  it('does not send an Authorization header when there is no token', async () => {
    let seen: unknown = 'unset'
    useResponder((config) => {
      seen = config.headers.Authorization
      return envelope({})
    })

    await request.get('/health')

    expect(seen).toBeUndefined()
  })
})

describe('single-flight refresh', () => {
  function rotatingResponder(overrides: Partial<{ freshToken: string; secondStatus: number }> = {}) {
    const freshToken = overrides.freshToken ?? 'fresh'
    const state = { refreshCalls: 0, attempts: [] as string[] }

    const responder: Responder = (config) => {
      if (config.url === REFRESH_URL) {
        state.refreshCalls += 1
        return envelope({
          access_token: freshToken,
          refresh_token: 'refresh-2',
          expires_in: 1800,
          token_type: 'bearer',
        })
      }

      const authorization = bearer(config)
      state.attempts.push(authorization)
      if (authorization !== `Bearer ${freshToken}`) {
        return failure(401, '登录状态已失效，请重新登录')
      }
      if (overrides.secondStatus) {
        return { status: overrides.secondStatus, payload: { code: overrides.secondStatus, msg: 'nope', data: null } }
      }
      return envelope({ url: config.url })
    }

    return { responder, state }
  }

  it('refreshes once when three requests get 401 concurrently', async () => {
    setTokens('stale', 'refresh-1', 1800)
    const { responder, state } = rotatingResponder()
    useResponder(responder)

    const results = await Promise.all([
      request.get<{ url: string }>('/a'),
      request.get<{ url: string }>('/b'),
      request.get<{ url: string }>('/c'),
    ])

    expect(state.refreshCalls).toBe(1)
    expect(results).toHaveLength(3)
    // Each request was replayed with the new token.
    expect(state.attempts.filter((value) => value === 'Bearer fresh')).toHaveLength(3)
  })

  it('stores the rotated tokens after a refresh', async () => {
    setTokens('stale', 'refresh-1', 1800)
    const { responder } = rotatingResponder()
    useResponder(responder)

    await request.get('/system/user')

    expect(getAccessToken()).toBe('fresh')
    expect(getRefreshToken()).toBe('refresh-2')
  })

  it('clears tokens and signals session expiry when the refresh itself fails', async () => {
    setTokens('stale', 'refresh-1', 1800)
    useResponder((config) => {
      if (config.url === REFRESH_URL) {
        return failure(401, '登录状态已失效，请重新登录')
      }
      return failure(401, '登录状态已失效，请重新登录')
    })

    await expect(request.get('/system/user')).rejects.toBeDefined()

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(sessionHooks.onSessionExpired).toHaveBeenCalledTimes(1)
  })

  it('gives up after one retry instead of looping', async () => {
    setTokens('stale', 'refresh-1', 1800)
    let protectedCalls = 0
    useResponder((config) => {
      if (config.url === REFRESH_URL) {
        return envelope({
          access_token: 'still-rejected',
          refresh_token: 'refresh-2',
          expires_in: 1800,
          token_type: 'bearer',
        })
      }
      protectedCalls += 1
      return failure(401, 'nope')
    })

    await expect(request.get('/system/user')).rejects.toBeDefined()

    // One original attempt plus exactly one replay.
    expect(protectedCalls).toBe(2)
  })

  it('ends the session when the replay is rejected with the fresh token', async () => {
    setTokens('stale', 'refresh-1', 1800)
    useResponder((config) => {
      if (config.url === REFRESH_URL) {
        return envelope({
          access_token: 'fresh',
          refresh_token: 'refresh-2',
          expires_in: 1800,
          token_type: 'bearer',
        })
      }
      return failure(401, '登录状态已失效，请重新登录')
    })

    await expect(request.get('/system/user')).rejects.toBeDefined()

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(sessionHooks.onSessionExpired).toHaveBeenCalledTimes(1)
  })

  // A failure of the *replayed* request that is not an authentication failure says
  // nothing about the session. Treating it as one threw away a perfectly good
  // refresh token and ejected the user.
  it('keeps the session when the replay fails with a server error', async () => {
    setTokens('stale', 'refresh-1', 1800)
    const { responder } = rotatingResponder({ secondStatus: 500 })
    useResponder(responder)

    await expect(request.get('/system/user')).rejects.toBeDefined()

    expect(getAccessToken()).toBe('fresh')
    expect(getRefreshToken()).toBe('refresh-2')
    expect(sessionHooks.onSessionExpired).not.toHaveBeenCalled()
  })

  it('keeps the session when the replay is forbidden', async () => {
    setTokens('stale', 'refresh-1', 1800)
    const { responder } = rotatingResponder({ secondStatus: 403 })
    useResponder(responder)

    await expect(request.get('/system/user')).rejects.toBeDefined()

    expect(getAccessToken()).toBe('fresh')
    expect(sessionHooks.onSessionExpired).not.toHaveBeenCalled()
    expect(sessionHooks.notifyError).toHaveBeenCalled()
  })

  it('keeps the session when the replay fails at the network layer', async () => {
    setTokens('stale', 'refresh-1', 1800)
    useResponder((config) => {
      if (config.url === REFRESH_URL) {
        return envelope({
          access_token: 'fresh',
          refresh_token: 'refresh-2',
          expires_in: 1800,
          token_type: 'bearer',
        })
      }
      if (bearer(config) === 'Bearer fresh') {
        throw new AxiosError('timeout of 15000ms exceeded', 'ECONNABORTED', config)
      }
      return failure(401, 'nope')
    })

    await expect(request.get('/system/user')).rejects.toBeDefined()

    expect(getAccessToken()).toBe('fresh')
    expect(sessionHooks.onSessionExpired).not.toHaveBeenCalled()
  })

  it('does not try to refresh a 401 from the refresh endpoint itself', async () => {
    setTokens('stale', 'refresh-1', 1800)
    let refreshCalls = 0
    useResponder((config) => {
      if (config.url === REFRESH_URL) {
        refreshCalls += 1
        return failure(401, 'nope')
      }
      return failure(401, 'nope')
    })

    await expect(
      refreshClient.post(REFRESH_URL, { refresh_token: 'refresh-1' }),
    ).rejects.toBeDefined()

    // The refresh client carries no interceptors, so there is nothing to recurse.
    expect(refreshCalls).toBe(1)
  })
})

describe('session storage', () => {
  it('stores and clears both tokens together', () => {
    setTokens('a', 'r', 1800)

    expect(getAccessToken()).toBe('a')
    expect(getRefreshToken()).toBe('r')

    removeTokens()

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })
})
