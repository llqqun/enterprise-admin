/**
 * Permission predicates.
 *
 * Pure functions on purpose: the same "may this caller do this" question is asked
 * by the `v-hasPerm` directive, by the layout (to hide an empty menu group), and by
 * tests. The directive is only the DOM-removal part.
 */

/** Permission code that stands for "everything"; the backend grants it to admins. */
export const WILDCARD_PERM = '*:*:*'

/** Role key that identifies the superuser. */
export const ADMIN_ROLE_KEY = 'admin'

/**
 * True when the caller holds at least one of `required`.
 *
 * An empty `required` list means "no permission needed" and returns true, which is
 * what makes `<button v-hasPerm="[]">` a no-op rather than a hidden button.
 */
export function hasPermission(held: readonly string[], required: readonly string[]): boolean {
  if (required.length === 0) {
    return true
  }
  if (held.includes(WILDCARD_PERM)) {
    return true
  }
  return required.some((code) => held.includes(code))
}

/** True when the caller holds at least one of `required` roles. */
export function hasRole(held: readonly string[], required: readonly string[]): boolean {
  if (required.length === 0) {
    return true
  }
  return required.some((role) => held.includes(role))
}
