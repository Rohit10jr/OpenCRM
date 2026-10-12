// Signs in once as Administrator through the real form and saves the browser state
// (the token pair in localStorage and the user_id cookie) for the `chromium` project.
// auth.spec.js covers the form itself; nothing else has to log in again.
import { test as setup, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { ADMIN_STATE } from '../../playwright.config.js'
import { login, readTokens } from './helpers.js'
import { users } from './users.js'

setup('sign in as Administrator', async ({ page }) => {
  // The first navigation on a cold dev server compiles the whole app.
  setup.setTimeout(400_000)
  await login(page, users.admin)
  const tokens = await readTokens(page)
  expect(tokens.access, 'an access token in localStorage').toBeTruthy()
  expect(tokens.refresh, 'a refresh token in localStorage').toBeTruthy()
  fs.mkdirSync(path.dirname(ADMIN_STATE), { recursive: true })
  await page.context().storageState({ path: ADMIN_STATE })
})
