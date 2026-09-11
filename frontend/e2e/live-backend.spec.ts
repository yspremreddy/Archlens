import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const SAMPLE_DOC = path.join(REPO_ROOT, 'data', 'samples', 'payment-service.md')

// Exercises the real running FastAPI backend (started separately, not
// by this test) end-to-end through the single-page UI: scroll to the
// Evidence section and search a question against a live backend,
// confirming real results render. Skipped automatically if no backend
// is reachable, so it never blocks a frontend-only CI run.
test('evidence search renders real results from a running backend', async ({ page, request }) => {
  const health = await request.get('http://localhost:8000/health').catch(() => null)
  test.skip(!health || !health.ok(), 'backend not running on :8000 — skipping live smoke test')

  await page.goto('/')
  await page.getByRole('link', { name: 'Evidence' }).click()
  await expect(page.locator('#evidence')).toBeInViewport()

  await page.getByLabel('Search query').fill('does payment-api have rate limiting?')
  await page.getByRole('button', { name: 'Search', exact: true }).click()

  await expect(page.getByText(/Results \(\d+\)/)).toBeVisible({ timeout: 15000 })
})

test('overview shows connected backend status without a stale abort error', async ({
  page,
  request,
}) => {
  const health = await request.get('http://localhost:8000/health').catch(() => null)
  test.skip(!health || !health.ok(), 'backend not running on :8000 — skipping live smoke test')

  await page.goto('/')
  await expect(page.getByText('API:')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('connected', { exact: true })).toBeVisible()
  // Regression check: the fixed abort-handling bug used to leave "signal
  // is aborted without reason" visible in the Overview section even
  // while the API/database were healthy.
  await expect(page.getByText(/signal is aborted/i)).toHaveCount(0)
})

test('full upload -> review -> graph flow works end to end through the UI', async ({
  page,
  request,
}) => {
  const health = await request.get('http://localhost:8000/health').catch(() => null)
  test.skip(!health || !health.ok(), 'backend not running on :8000 — skipping live smoke test')

  await page.goto('/')

  // Upload: real file, real backend ingestion, preview shown.
  await page.getByRole('link', { name: 'Upload' }).click()
  await page.locator('#file-input').setInputFiles(SAMPLE_DOC)
  await expect(page.getByText('payment-service.md', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(page.getByText(/was uploaded and indexed successfully/)).toBeVisible({
    timeout: 15000,
  })

  // Review: real /review call, verdict + evidence with real text render.
  await page.getByRole('link', { name: 'Review', exact: true }).click()
  await page.getByLabel('Question').fill('does payment-api have rate limiting on the checkout endpoint?')
  await page.getByRole('button', { name: 'Run review' }).click()
  await expect(page.getByText('FAIL', { exact: true })).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(/no documented rate limiting/).first()).toBeVisible()

  // Graph: query a component known to have no extracted relationships
  // yet -> the documented empty state must render, not an error.
  await page.getByRole('link', { name: 'Graph' }).click()
  await page.getByLabel('Component name').fill('payment-api')
  await page.getByRole('button', { name: 'Query graph' }).click()
  await expect(page.getByText('No architecture relationships available yet.')).toBeVisible({
    timeout: 15000,
  })

  // Evaluation: static last-measured metrics render.
  await page.getByRole('link', { name: 'Evaluation' }).click()
  await expect(page.getByRole('rowheader', { name: 'Recall@5', exact: true })).toBeVisible()
})
