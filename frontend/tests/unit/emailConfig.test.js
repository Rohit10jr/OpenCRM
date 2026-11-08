import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils', () => ({ validateEmail: () => true }))

const { addableServices, services } = await import(
  '@/components/Settings/emailConfig'
)

describe('email providers', () => {
  it('does not offer Frappe Mail for a new account', () => {
    const names = addableServices.map((s) => s.name)
    expect(names).not.toContain('Frappe Mail')
    expect(names).toEqual(
      expect.arrayContaining(['GMail', 'Outlook', 'Sendgrid', 'SparkPost', 'Yahoo', 'Yandex']),
    )
  })

  it('still knows Frappe Mail, so a saved account opens with its own form', () => {
    expect(services.find((s) => s.name === 'Frappe Mail')?.custom).toBe(true)
  })
})
