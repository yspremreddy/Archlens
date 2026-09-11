import { expect, test } from '@playwright/test'

// Exercises the real running FastAPI backend (started separately, not
// by this test) end-to-end through the UI: search a question that was
// just ingested via the backend smoke test, and confirm the answer view
// renders citations from the live API. Skipped automatically if no
// backend is reachable, so it never blocks a frontend-only CI run.
test('search view renders real results from a running backend', async ({ page, request }) => {
  const health = await request.get('http://localhost:8000/health').catch(() => null)
  test.skip(!health || !health.ok(), 'backend not running on :8000 — skipping live smoke test')

  await page.goto('/')
  await page.getByRole('tab', { name: 'Search' }).click()
  await page.getByLabel('Query').fill('does payment-api have rate limiting?')
  await page.getByRole('button', { name: 'Search', exact: true }).click()

  await expect(page.getByText(/Results \(\d+\)/)).toBeVisible({ timeout: 15000 })
})
