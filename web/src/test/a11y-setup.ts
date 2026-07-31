/**
 * a11y-setup — shared config + assertion helper for the `*.a11y.test.tsx`
 * suite (slice 13a). Imported directly by those files; NOT added to
 * `vite.config.ts`'s global `setupFiles`, so `jest-axe` only loads for the
 * accessibility run, not every `vitest run`.
 *
 * Deliberately uses plain vitest assertions (`expect(...).toEqual([])`)
 * instead of registering jest-axe's `toHaveNoViolations` custom matcher:
 * that matcher's real return shape is a Jest `{pass, message()}` object,
 * and vitest's `Assertion<T>` interface has no ambient knowledge of it
 * without hand-writing a second module-augmentation just to get a slightly
 * prettier failure string. `expectNoAxeViolations` below prints the same
 * information (rule id, description, and the offending node's outerHTML)
 * on failure via a plain thrown assertion, with no extra typing surface.
 */
import { expect } from 'vitest'
import { axe, type AxeResults, type JestAxeConfigureOptions } from 'jest-axe'

/**
 * Rule overrides for scanning an isolated component FRAGMENT rather than a
 * full document. `jest-axe`'s own `axe()` already disables the `cat.color`
 * rule category (color-contrast and friends) by default -- see
 * `node_modules/jest-axe/index.js`: "Color contrast checking doesn't work
 * in a jsdom environment" -- so this only needs to add the page-structure
 * rules that are correct for a full page but meaningless for a fragment
 * (no single `<main>`, no single `<h1>`, nothing to "skip to content" past).
 */
export const FRAGMENT_AXE_CONFIG: JestAxeConfigureOptions = {
  rules: {
    region: { enabled: false },
    'landmark-one-main': { enabled: false },
    'page-has-heading-one': { enabled: false },
    bypass: { enabled: false },
  },
}

function formatViolations(results: AxeResults): string {
  return results.violations
    .map((v) => {
      const nodes = v.nodes.map((n) => `    - ${n.html}`).join('\n')
      return `[${v.impact ?? 'unknown'}] ${v.id}: ${v.help}\n  ${v.helpUrl}\n${nodes}`
    })
    .join('\n\n')
}

/** Runs axe against `target` with `FRAGMENT_AXE_CONFIG` and asserts zero
 *  violations, printing rule id/description/offending markup on failure. */
export async function expectNoAxeViolations(target: Element | Document | string): Promise<void> {
  const results = await axe(target, FRAGMENT_AXE_CONFIG)
  expect(results.violations, formatViolations(results)).toEqual([])
}
