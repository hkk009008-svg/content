/**
 * Local type shim for `jest-axe` (slice 13a a11y harness).
 *
 * `jest-axe` ships no types of its own. `@types/jest-axe` was deliberately
 * NOT used instead: installing it pulls in `@types/jest` as a hard
 * dependency (`"dependencies": {"@types/jest": "*"}`), and with no `"types"`
 * array in this project's tsconfig.json, TypeScript auto-includes EVERY
 * package under `node_modules/@types/` -- so `@types/jest` would silently
 * add Jest's ambient `describe`/`it`/`expect`/... globals project-wide,
 * even though this project uses vitest and every test already imports those
 * names explicitly from `'vitest'`. Its bundled `axe-core` typings also
 * target v3.x while the real runtime dependency here is v4.x (verified:
 * `@types/jest-axe@3.5.9` depends on `axe-core@^3.5.5`; `jest-axe@11.0.0`
 * depends on `axe-core@4.12.1`). This shim declares only the exact surface
 * `a11y-setup.ts` and the `*.a11y.test.tsx` suite call, typed against the
 * real v4 result shape.
 */
declare module 'jest-axe' {
  export interface AxeViolation {
    id: string
    impact?: string | null
    description: string
    help: string
    helpUrl: string
    nodes: Array<{ html: string; target: string[]; failureSummary?: string }>
  }

  export interface AxeResults {
    violations: AxeViolation[]
    passes: unknown[]
    incomplete: unknown[]
    inapplicable: unknown[]
  }

  export interface JestAxeConfigureOptions {
    rules?: Record<string, { enabled: boolean }>
    [key: string]: unknown
  }

  export function axe(
    html: Element | Document | string,
    options?: JestAxeConfigureOptions,
  ): Promise<AxeResults>
}
