// Signing in and out, the guard around protected pages, and the token pair.
// Findings 28, 32, 33, 34, 35 and 38 in docs/FINDINGS.md were all on this path.
import { test, expect } from './fixtures.js'
import { login, readTokens } from './helpers.js'
import { userMenuButton } from './ui.js'
import { users } from './users.js'

// Every test here starts signed out; the state auth.setup.js saved is not used.
test.use({ storageState: { cookies: [], origins: [] } })

test.describe('the login page', () => {
  test('shows the sign-in form', async ({ page }) => {
    await page.goto('/crm/login')
    await expect(page.getByRole('heading', { name: 'Sign in to Frappe CRM' })).toBeVisible()
    await expect(page.locator('input[name="username"]')).toBeVisible()
    await expect(page.locator('input[name="password"]')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Forgot your password?' })).toBeVisible()
  })

  test('refuses a wrong password and stays on the page with nothing stored', async ({ page }) => {
    await page.goto('/crm/login')
    // An account that does not exist, so no real user's failed-attempt counter moves.
    await page.locator('input[name="username"]').fill('nobody@example.com')
    await page.locator('input[name="password"]').fill('not-the-password')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toHaveText('Invalid Email or Password')
    expect(new URL(page.url()).pathname).toBe('/crm/login')
    const tokens = await readTokens(page)
    expect(tokens.access).toBeNull()
    expect(tokens.refresh).toBeNull()
  })

  test('the forgot-password page shows its form', async ({ page }) => {
    await page.goto('/crm/forgot-password')
    await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Send reset link' })).toBeVisible()
  })
})

test.describe('signing in', () => {
  test('lands in the app, stores the token pair and sets the user cookie', async ({ page }) => {
    await login(page, users.admin)
    // Home resolves to the user's default view, Leads when none is set.
    await expect(page).toHaveURL(/\/crm\/leads/)
    const tokens = await readTokens(page)
    expect(tokens.access).toBeTruthy()
    expect(tokens.refresh).toBeTruthy()
    // frappe-ui's own session helper reads this cookie (FINDINGS.md 38).
    const cookie = (await page.context().cookies()).find((c) => c.name === 'user_id')
    expect(cookie?.value).toBe(users.admin.name)
  })

  test('a protected page visited signed out redirects to login, then back', async ({ page }) => {
    await page.goto('/crm/deals')
    await expect(page).toHaveURL(/\/crm\/login\?/)
    expect(new URL(page.url()).searchParams.get('redirect')).toMatch(/^\/deals/)
    await page.locator('input[name="username"]').fill(users.admin.name)
    await page.locator('input[name="password"]').fill(users.admin.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/crm\/deals/)
  })

  test('a redirect target never leaves the site', async ({ page, baseURL }) => {
    await page.goto('/crm/login?redirect=https://evil.example/phish')
    await page.locator('input[name="username"]').fill(users.admin.name)
    await page.locator('input[name="password"]').fill(users.admin.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL((url) => !url.pathname.startsWith('/crm/login'))
    expect(new URL(page.url()).origin).toBe(new URL(baseURL).origin)
  })

  test('a signed-in visitor to the login page is sent into the app', async ({ page }) => {
    await login(page, users.admin)
    await page.goto('/crm/login')
    await expect(page).not.toHaveURL(/\/crm\/login/)
  })
})

test.describe('signing out', () => {
  test('returns to the login page, clears the tokens and revokes the refresh token', async ({
    page,
    request,
  }) => {
    await login(page, users.admin)
    const { refresh } = await readTokens(page)

    await userMenuButton(page).click()
    await page.getByRole('menuitem', { name: 'Log out' }).click()
    await expect(page).toHaveURL(/\/crm\/login$/)

    const tokens = await readTokens(page)
    expect(tokens.access).toBeNull()
    expect(tokens.refresh).toBeNull()
    expect((await page.context().cookies()).find((c) => c.name === 'user_id')).toBeUndefined()

    // The refresh token was blacklisted on the way out (FINDINGS.md 35).
    const response = await request.post('/api/method/token/refresh', { data: { refresh } })
    expect(response.status()).toBe(401)
  })
})
