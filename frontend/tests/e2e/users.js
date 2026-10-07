// The demo accounts the http suite uses (docs/http/01_auth.http), with their passwords
// read from docs/http/.env by playwright.config.js. `name` is the User document's name,
// which is what the login form matches (docs/FINDINGS.md 36).
export const users = {
  admin: { name: 'Administrator', password: process.env.ADMIN_PWD, roles: ['System Manager'] },
  manager: { name: 'grace@example.com', password: process.env.MANAGER_PWD, roles: ['Sales Manager'] },
  sales: { name: 'ada@example.com', password: process.env.SALES_PWD, roles: ['Sales User'] },
}

export function requirePassword(user) {
  if (!user.password) {
    throw new Error(
      `No password for ${user.name}: set it in docs/http/.env (ADMIN_PWD, MANAGER_PWD, SALES_PWD) ` +
        'or in the environment before running the browser tests.',
    )
  }
  return user
}
