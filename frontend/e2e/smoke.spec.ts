import { expect, test } from '@playwright/test'

// This smoke test exercises the UI shell and tab navigation only — it
// does not require a running backend, so it stays meaningful in CI
// where Postgres/Neo4j aren't wired up for the frontend job. A separate
// manual smoke test (see README.md "Demo flow") exercises the real
// backend end-to-end.
test('loads the dashboard and can switch tabs via keyboard-accessible tablist', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'ArchLens', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Dashboard', exact: true })).toHaveAttribute('aria-selected', 'true')

  await page.getByRole('tab', { name: 'Upload' }).click()
  await expect(page.getByRole('heading', { name: 'Upload an artifact' })).toBeVisible()

  await page.getByRole('tab', { name: 'Evaluation' }).click()
  await expect(page.getByRole('heading', { name: 'Evaluation results' })).toBeVisible()
})

test('theme toggle updates the pressed state', async ({ page }) => {
  await page.goto('/')
  const toggle = page.getByRole('button', { name: /switch to (dark|light) theme/i })
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
})
