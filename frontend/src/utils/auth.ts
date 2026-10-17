/**
 * Token storage.
 *
 * Deliberately explicit and in one place: the access token is read by the request
 * interceptor on every call and written by the login flow and the refresh flow.
 * Two mechanisms writing the same key is how "logged out but still authenticated"
 * bugs happen.
 *
 * NOTE: `localStorage` is readable by any script on the origin. That is acceptable
 * for this project's threat model (a local demo) and is listed in the docs as a
 * production hardening item — httpOnly cookies would be the real fix.
 */

const ACCESS_TOKEN_KEY = 'ea_access_token'
const REFRESH_TOKEN_KEY = 'ea_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

/**
 * Store a token pair.
 *
 * `expiresIn` is accepted so the shape matches the backend response and so a
 * future "proactively refresh before expiry" change has the value to hand; it is
 * intentionally not used for a timer today (YAGNI).
 */
export function setTokens(accessToken: string, refreshToken: string, expiresIn?: number): void {
  void expiresIn
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function removeTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}
