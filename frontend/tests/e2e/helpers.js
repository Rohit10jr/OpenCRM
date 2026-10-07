import { expect, request } from '@playwright/test'
import { requirePassword } from './users.js'

/** The two localStorage keys src/auth/tokens.js uses. */
export const ACCESS_KEY = 'crm:access_token'
export const REFRESH_KEY = 'crm:refresh_token'

/**
 * frappe-ui's onboarding keeps "steps completed" per app and user in localStorage and
 * opens the Getting Started panel over the page whenever it is false (onboarding.js,
 * `setUp`). The panel covers the right third of every list and dialog, so the tests
 * mark it complete before the app mounts.
 */
export const onboardingKey = (user) => `isOnboardingStepsCompletedfrappecrm${user.name}`

/** Sign in through the real form and wait until the app has left the login page. */
export async function login(page, user) {
  requirePassword(user)
  await page.goto('/crm/login')
  await page.evaluate((key) => localStorage.setItem(key, 'true'), onboardingKey(user))
  await page.locator('input[name="username"]').fill(user.name)
  await page.locator('input[name="password"]').fill(user.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((url) => url.pathname.startsWith('/crm') && !url.pathname.startsWith('/crm/login'))
}

/** The token pair the browser holds, or nulls when signed out. */
export async function readTokens(page) {
  return page.evaluate(
    ([access, refresh]) => ({
      access: localStorage.getItem(access),
      refresh: localStorage.getItem(refresh),
    }),
    [ACCESS_KEY, REFRESH_KEY],
  )
}

/** A name no other run will have used, so tests never trip over each other's rows. */
export function uniqueName(prefix) {
  return `${prefix} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

const enc = encodeURIComponent

async function unwrap(response, key) {
  if (!response.ok()) {
    throw new Error(`${response.request().method()} ${response.url()} -> ${response.status()}: ${await response.text()}`)
  }
  const body = await response.json()
  return key in body ? body[key] : body
}

/**
 * A backend client signed in as `user`, for seeding rows and cleaning up fast, outside
 * the browser. Everything goes through the same base URL the browser uses, so Vite's
 * proxy carries it to Django. `track()` registers a row for deletion when the client
 * is disposed, newest first.
 */
export async function backendClient(baseURL, user) {
  requirePassword(user)
  const anonymous = await request.newContext({ baseURL })
  const login = await anonymous.post('/api/method/login', {
    data: { usr: user.name, pwd: user.password },
  })
  if (!login.ok()) {
    throw new Error(
      `Signing in as ${user.name} answered ${login.status()}. Is the Django server on 8000 up, with the demo data loaded?`,
    )
  }
  const { message: tokens } = await login.json()
  await anonymous.dispose()

  const context = await request.newContext({
    baseURL,
    extraHTTPHeaders: { Authorization: `Bearer ${tokens.access}` },
  })
  const tracked = []

  return {
    context,
    tokens,
    track(doctype, name) {
      tracked.push([doctype, name])
      return name
    },
    async call(path, params = {}) {
      return unwrap(await context.post(`/api/method/${path}`, { data: params }), 'message')
    },
    async create(doctype, data) {
      const doc = await unwrap(await context.post(`/api/resource/${enc(doctype)}`, { data }), 'data')
      this.track(doctype, doc.name)
      return doc
    },
    async get(doctype, name) {
      return unwrap(await context.get(`/api/resource/${enc(doctype)}/${enc(name)}`), 'data')
    },
    async list(doctype, { filters = {}, fields = ['name'], limit = 20 } = {}) {
      const query = new URLSearchParams({
        filters: JSON.stringify(filters),
        fields: JSON.stringify(fields),
        limit_page_length: String(limit),
      })
      return unwrap(await context.get(`/api/resource/${enc(doctype)}?${query}`), 'data')
    },
    async remove(doctype, name) {
      const response = await context.delete(`/api/resource/${enc(doctype)}/${enc(name)}`)
      if (!response.ok() && response.status() !== 404) {
        throw new Error(`DELETE ${doctype} ${name} -> ${response.status()}: ${await response.text()}`)
      }
    },
    async dispose() {
      for (const [doctype, name] of tracked.reverse()) {
        try {
          await this.remove(doctype, name)
        } catch (error) {
          console.warn(`cleanup: ${error.message}`)
        }
      }
      await context.dispose()
    },
  }
}

/** Wait for one response to a method endpoint, e.g. `crm.api.doc.get_data`. */
export function waitForMethod(page, dottedPath, predicate = () => true) {
  return page.waitForResponse(
    (response) => response.url().includes(`/api/method/${dottedPath}`) && predicate(response),
  )
}

export { expect }
