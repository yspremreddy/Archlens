import { expect, test } from '@playwright/test'

// This smoke test exercises the single-page UI shell and its scrolling
// nav only — it does not require a running backend, so it stays
// meaningful in CI where Postgres/Neo4j aren't wired up for the frontend
// job. A separate manual smoke test (see README.md "Demo flow")
// exercises the real backend end-to-end.
test('all six sections render on one page and nav links scroll to them', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'ArchLens', exact: true })).toBeVisible()

  // All sections exist in the DOM at once — a single scrollable page,
  // not separate routes/tabs.
  await expect(page.locator('#overview')).toBeVisible()
  await expect(page.locator('#upload')).toBeVisible()
  await expect(page.locator('#review')).toBeVisible()
  await expect(page.locator('#evidence')).toBeVisible()
  await expect(page.locator('#graph')).toBeVisible()
  await expect(page.locator('#evaluation')).toBeVisible()

  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Architecture Review' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Evidence Search' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Component Graph' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Evaluation', exact: true })).toBeVisible()

  // Clicking a nav link scrolls the page to that section instead of
  // navigating to a new route/URL path.
  await page.getByRole('link', { name: 'Evaluation' }).click()
  await expect(page.locator('#evaluation')).toBeInViewport()
  expect(page.url()).toContain('/')

  await page.getByRole('link', { name: 'Upload', exact: true }).click()
  await expect(page.locator('#upload')).toBeInViewport()
})

test('theme toggle updates the pressed state', async ({ page }) => {
  await page.goto('/')
  const toggle = page.getByRole('button', { name: /switch to (dark|light) theme/i })
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
})
