#!/usr/bin/env node
/**
 * capture_ui_states.mjs — the reproducible screenshot command required by the
 * product-unification plan's slice 13d ("Retain named viewport/state
 * screenshots at 1440x1000 and 1024x768 under
 * logs/ui/product-unification/<viewport>/").
 *
 * Drives the REAL Flask backend and the built frontend. Makes NO provider
 * call and never clicks Generate, so a capture run costs nothing.
 *
 *   .venv/bin/python web_server.py &          # or: Cinemaker.app
 *   node scripts/capture_ui_states.mjs
 *
 * Exits non-zero if the server is not answering, rather than writing blank
 * or half-rendered PNGs — an unreadable artifact is worse than a missing one,
 * because it looks like evidence.
 */
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// playwright is a devDependency of web/, not of the repo root, and ESM resolves
// from THIS file's directory — so resolve it explicitly against web/package.json.
// Same idiom scripts/product_surface_frontend_inventory.mjs uses for typescript.
const { chromium } = createRequire(path.join(ROOT, 'web', 'package.json'))('playwright')
const OUT = path.join(ROOT, 'logs', 'ui', 'product-unification')
const BASE = process.env.CINEMA_URL || 'http://localhost:8080'

const VIEWPORTS = [
  { name: '1440x1000', width: 1440, height: 1000 },
  { name: '1024x768', width: 1024, height: 768 },
]

/** Settle: the app hydrates from the backend, so wait for real content. */
async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function shoot(page, dir, name) {
  const file = path.join(dir, `${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  console.log(`  wrote ${path.relative(ROOT, file)}`)
}

async function run() {
  // Fail loudly and early if nothing is serving.
  const probe = await fetch(BASE).catch(() => null)
  if (!probe || !probe.ok) {
    console.error(`capture_ui_states: no server at ${BASE}. Start it first:\n` +
      `  .venv/bin/python web_server.py   (or open Cinemaker.app)`)
    process.exit(2)
  }

  const browser = await chromium.launch()
  try {
    for (const vp of VIEWPORTS) {
      const dir = path.join(OUT, vp.name)
      await mkdir(dir, { recursive: true })
      console.log(`\n[${vp.name}]`)

      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 2,
        colorScheme: 'dark',
      })
      const page = await ctx.newPage()

      // 1. loading — captured before the project list resolves.
      await page.goto(BASE, { waitUntil: 'commit' })
      await page.waitForTimeout(120)
      await shoot(page, dir, 'loading')

      // 2. project selection, fully hydrated.
      await settle(page)
      await shoot(page, dir, 'project-selection')

      // 3. open the newest existing project (no creation -> no state churn).
      const first = page.locator('button', { hasText: /·|[0-9a-f]{8}/ }).first()
      const rows = page.locator('[class*="cursor-pointer"], li, button')
      const target = (await first.count()) ? first : rows.first()
      if (await target.count()) {
        await target.click({ timeout: 5000 }).catch(() => {})
        await settle(page)
      }
      await shoot(page, dir, 'setup')

      // 4-6. the three product pages. Nav buttons are labelled.
      for (const [label, shotName] of [['Edit', 'edit'], ['Run', 'run-idle'], ['Capability', 'capability']]) {
        const nav = page.getByRole('button', { name: label, exact: true })
        if (await nav.count()) {
          await nav.first().click({ timeout: 5000 }).catch(() => {})
          await settle(page, 700)
          await shoot(page, dir, shotName)
        }
      }

      // 7. empty — back at the project list with a search that matches nothing,
      //    which is the honest way to reach the empty state without mutating data.
      const back = page.getByRole('button', { name: /back to projects/i })
      if (await back.count()) {
        await back.first().click({ timeout: 5000 }).catch(() => {})
        await settle(page, 600)
        const search = page.getByPlaceholder(/search by name or id/i)
        if (await search.count()) {
          await search.fill('zzz-no-such-project-zzz')
          await page.waitForTimeout(400)
          await shoot(page, dir, 'empty')
        }
      }

      // 8. error — a bad project id exercises the typed client's non-2xx path.
      await page.goto(`${BASE}/?project=does-not-exist-0000`, { waitUntil: 'commit' })
      await settle(page, 700)
      await shoot(page, dir, 'error')

      await ctx.close()
    }
  } finally {
    await browser.close()
  }
  console.log(`\nDone. Artifacts under ${path.relative(ROOT, OUT)}/<viewport>/`)
}

run().catch((err) => {
  console.error('capture_ui_states failed:', err)
  process.exit(1)
})
