// One-off screenshot capture script (not part of the app/test suite) —
// launches Chromium against the real running dev server + backend and
// captures the single-page UI in meaningful, populated states for
// assets/screenshots/. Run with: node scripts/capture-screenshots.mjs
// Requires: `npm run dev` (frontend) and the FastAPI backend both
// already running.
import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const OUT_DIR = path.resolve(import.meta.dirname, '..', '..', 'assets', 'screenshots')
const BASE_URL = 'http://localhost:5173'

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

  await page.goto(BASE_URL)
  // Switch to dark theme for consistent, clean screenshots.
  const themeToggle = page.getByRole('button', { name: /switch to dark theme/i })
  if (await themeToggle.count()) await themeToggle.click()
  await page.waitForTimeout(300)

  // 1. Overview — real backend status + real stats.
  await page.locator('#overview').scrollIntoViewIfNeeded()
  await page.waitForSelector('.stat-tile dd')
  await page.waitForTimeout(500)
  await page.screenshot({ path: path.join(OUT_DIR, '01-overview.png') })

  // 2. Upload — real file selected, real preview, real upload result.
  await page.locator('#upload').scrollIntoViewIfNeeded()
  await page.setInputFiles('#file-input', path.resolve(import.meta.dirname, '..', '..', 'assets', 'demo', 'payment-service-architecture.md'))
  await page.waitForTimeout(300)
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await page.getByText(/was uploaded and indexed successfully|status:/).first().waitFor({ timeout: 15000 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, '02-upload.png') })

  // 3. Review — real /review call and real evidence cards.
  await page.locator('#review').scrollIntoViewIfNeeded()
  await page.getByLabel('Question').fill(
    'Does this architecture comply with the requirement that production customer databases must not be publicly accessible?',
  )
  await page.getByRole('button', { name: 'Run review' }).click()
  await page.getByText('FAIL', { exact: true }).first().waitFor({ timeout: 15000 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, '03-review.png') })

  // 4. Evidence — real hybrid search results.
  await page.locator('#evidence').scrollIntoViewIfNeeded()
  await page.getByLabel('Search query').fill('public subnet database access')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByText(/Results \(\d+\)/).waitFor({ timeout: 15000 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, '04-evidence.png') })

  // 5. Graph — real component relationships (event-collector chain).
  await page.locator('#graph').scrollIntoViewIfNeeded()
  await page.getByLabel('Component name').fill('event-collector')
  await page.getByRole('button', { name: 'Query graph' }).click()
  await page.getByText(/path\(s\) found/).waitFor({ timeout: 15000 })
  await page.waitForTimeout(400)
  await page.screenshot({ path: path.join(OUT_DIR, '05-graph.png') })

  // 6. Evaluation — real last-measured metrics table.
  await page.locator('#evaluation').scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await page.screenshot({ path: path.join(OUT_DIR, '06-evaluation.png') })

  // 7. Full-page hero shot (top of page, nav visible).
  await page.locator('#overview').scrollIntoViewIfNeeded()
  await page.waitForTimeout(200)
  await page.screenshot({ path: path.join(OUT_DIR, '00-hero.png') })

  await browser.close()
  console.log('Screenshots written to', OUT_DIR)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
