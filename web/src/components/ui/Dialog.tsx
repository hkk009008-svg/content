import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

/**
 * Dialog — accessible modal primitive (slice 13a). Fills the gap
 * `console/RejectAutoApproveModal.tsx`'s own docstring names explicitly:
 * "no shared Modal component exists; the inline overlay approach mirrors
 * GenerationPanel and other overlay surfaces." This is that shared
 * component, implementing the WAI-ARIA APG "Dialog (Modal)" pattern:
 *
 * - `role="dialog"` + `aria-modal="true"`, named via `title` (renders a
 *   heading and wires `aria-labelledby` to it) or an explicit `aria-label`
 *   when the caller doesn't want a visible heading.
 * - Focus moves INTO the dialog on open -- to `initialFocusRef` if given,
 *   else the first focusable descendant, else the panel itself -- and is
 *   RESTORED to whatever had focus before opening when the dialog closes
 *   (or unmounts while open).
 * - Tab / Shift+Tab is trapped to the panel's focusable elements (wraps
 *   last -> first and first -> last instead of escaping to the page body).
 * - Escape closes, unless `closeOnEscape={false}`.
 * - Clicking the overlay closes, unless `closeOnOverlayClick={false}`;
 *   clicking inside the panel never bubbles to the overlay.
 * - Background scroll is locked while open.
 * - Rendered through a portal to `document.body` so a fixed-position
 *   overlay is never clipped or mispositioned by an ancestor's `transform`/
 *   `overflow` (a real risk for a shared primitive mounted from anywhere).
 * - Every other direct body child is temporarily `inert` and
 *   `aria-hidden`, with reference-counted restoration for nested dialogs, so
 *   pointer, keyboard, and screen-reader browse navigation stay inside the
 *   active modal.
 *
 * `children` is the full panel body -- this primitive owns only the
 * overlay/panel chrome and the a11y mechanics, not any particular form or
 * button layout, so existing bespoke modals can adopt it without losing
 * their own content shape.
 *
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type BackgroundLockState = {
  count: number
  ariaHidden: string | null
  hadInert: boolean
}

const backgroundLocks = new WeakMap<HTMLElement, BackgroundLockState>()

function acquireBackgroundLock(element: HTMLElement) {
  const existing = backgroundLocks.get(element)
  if (existing) {
    existing.count += 1
    return
  }
  backgroundLocks.set(element, {
    count: 1,
    ariaHidden: element.getAttribute('aria-hidden'),
    hadInert: element.hasAttribute('inert'),
  })
  element.setAttribute('aria-hidden', 'true')
  element.setAttribute('inert', '')
}

function releaseBackgroundLock(element: HTMLElement) {
  const state = backgroundLocks.get(element)
  if (!state) return
  state.count -= 1
  if (state.count > 0) return
  backgroundLocks.delete(element)
  if (state.ariaHidden === null) element.removeAttribute('aria-hidden')
  else element.setAttribute('aria-hidden', state.ariaHidden)
  if (!state.hadInert) element.removeAttribute('inert')
}

interface DialogProps {
  isOpen: boolean
  onClose: () => void
  children: ReactNode
  /** Rendered as an `<h2>` and wired to `aria-labelledby`. Omit and pass
   *  `aria-label` instead for a dialog whose visible content already reads
   *  as its own heading. */
  title?: string
  'aria-label'?: string
  className?: string
  closeOnOverlayClick?: boolean
  closeOnEscape?: boolean
  /** Explicit initial-focus target, when the first focusable descendant
   *  isn't the right one (e.g. a destructive dialog that should NOT default
   *  focus onto its own confirm button). Nullable to match how React 19
   *  types a ref created via `useRef<T>(null)`. */
  initialFocusRef?: RefObject<HTMLElement | null>
}

export function Dialog({
  isOpen,
  onClose,
  children,
  title,
  'aria-label': ariaLabel,
  className = '',
  closeOnOverlayClick = true,
  closeOnEscape = true,
  initialFocusRef,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  if (isOpen && !title && !ariaLabel) {
    // TypeScript can't express "at least one of title/aria-label" without an
    // overload pair that would complicate every call site -- this warning is
    // the enforcement backstop, matching the accessible-name requirement
    // Toggle/SelectPill already enforce at the type level. Unconditional
    // (not dev-gated): this project has no `vite-env.d.ts`, so there's no
    // typed `import.meta.env.DEV` to check, and a console.warn is harmless
    // for real users either way.
    console.warn('[Dialog] no `title` or `aria-label` given -- this dialog has no accessible name.')
  }

  // Focus lifecycle: move focus in on open, restore it on close/unmount.
  // Keyed on `isOpen` alone -- the cleanup closure captures whatever had
  // focus at the moment THIS effect ran, so it fires exactly once per
  // open/close pair regardless of how many re-renders happen in between.
  useEffect(() => {
    if (!isOpen) return
    const opener = document.activeElement as HTMLElement | null

    const target =
      initialFocusRef?.current ??
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
      panelRef.current
    target?.focus()

    return () => {
      opener?.focus?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Escape-to-close + Tab trap, active only while open.
  useEffect(() => {
    if (!isOpen) return

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        if (!closeOnEscape) return
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      if (!focusable || focusable.length === 0) {
        e.preventDefault()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [isOpen, onClose, closeOnEscape])

  // Background scroll lock while open.
  useEffect(() => {
    if (!isOpen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
    }
  }, [isOpen])

  // Hide and disable every body-level background surface. Deriving the
  // targets from the portal overlay avoids coupling this shared primitive to
  // a hardcoded app-root id and also handles test/embedded roots. The shared
  // per-element counter preserves correct state when one modal opens over
  // another.
  useEffect(() => {
    if (!isOpen) return
    const overlay = panelRef.current?.parentElement
    if (!overlay) return
    const locked = Array.from(document.body.children).filter(
      (element): element is HTMLElement => element instanceof HTMLElement && element !== overlay,
    )
    locked.forEach(acquireBackgroundLock)
    return () => locked.forEach(releaseBackgroundLock)
  }, [isOpen])

  if (!isOpen) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={closeOnOverlayClick ? onClose : undefined}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : ariaLabel}
        tabIndex={-1}
        className={`relative w-full max-w-md rounded-lg border border-line bg-app shadow-xl focus:outline-none ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          {title && (
            <h2 id={titleId} className="font-display italic text-tx text-xl mb-4">
              {title}
            </h2>
          )}
          {children}
        </div>
      </div>
    </div>,
    document.body,
  )
}
