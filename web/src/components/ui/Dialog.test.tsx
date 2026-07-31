import { useRef, useState } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Dialog } from './Dialog'

afterEach(cleanup)

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(
      <Dialog isOpen={false} onClose={vi.fn()} title="Hidden">
        <p>body</p>
      </Dialog>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('is a modal dialog named by its title', () => {
    render(
      <Dialog isOpen onClose={vi.fn()} title="Confirm action">
        <p>Are you sure?</p>
      </Dialog>,
    )
    expect(screen.getByRole('dialog', { name: 'Confirm action' })).toHaveAttribute(
      'aria-modal',
      'true',
    )
  })

  it('falls back to aria-label when no title is given', () => {
    render(
      <Dialog isOpen onClose={vi.fn()} aria-label="Custom dialog name">
        <p>body</p>
      </Dialog>,
    )
    expect(screen.getByRole('dialog', { name: 'Custom dialog name' })).toBeInTheDocument()
  })

  it('warns in dev when neither title nor aria-label is given', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(
      <Dialog isOpen onClose={vi.fn()}>
        <p>body</p>
      </Dialog>,
    )
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('no accessible name'))
    warn.mockRestore()
  })

  it('moves focus to the first focusable descendant on open', () => {
    render(
      <Dialog isOpen onClose={vi.fn()} title="T">
        <button>First</button>
        <button>Second</button>
      </Dialog>,
    )
    expect(screen.getByText('First')).toHaveFocus()
  })

  it('honors an explicit initialFocusRef over the first focusable descendant', () => {
    function Harness() {
      const secondRef = useRef<HTMLButtonElement>(null)
      return (
        <Dialog isOpen onClose={vi.fn()} title="T" initialFocusRef={secondRef}>
          <button>First</button>
          <button ref={secondRef}>Second</button>
        </Dialog>
      )
    }
    render(<Harness />)
    expect(screen.getByText('Second')).toHaveFocus()
  })

  it('restores focus to the element that opened it, on close', async () => {
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <div>
          <button onClick={() => setOpen(true)}>Open</button>
          <Dialog isOpen={open} onClose={() => setOpen(false)} title="T">
            <button>Inside</button>
          </Dialog>
        </div>
      )
    }
    render(<Harness />)
    const opener = screen.getByText('Open')
    await userEvent.click(opener)
    expect(screen.getByText('Inside')).toHaveFocus()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('Escape calls onClose by default', async () => {
    const onClose = vi.fn()
    render(
      <Dialog isOpen onClose={onClose} title="T">
        <button>Inside</button>
      </Dialog>,
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Escape does nothing when closeOnEscape is false', async () => {
    const onClose = vi.fn()
    render(
      <Dialog isOpen onClose={onClose} title="T" closeOnEscape={false}>
        <button>Inside</button>
      </Dialog>,
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('traps Tab: past the last focusable element wraps to the first', async () => {
    render(
      <Dialog isOpen onClose={vi.fn()} title="T">
        <button>First</button>
        <button>Second</button>
      </Dialog>,
    )
    expect(screen.getByText('First')).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByText('Second')).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByText('First')).toHaveFocus()
  })

  it('traps Shift+Tab: back past the first focusable element wraps to the last', async () => {
    render(
      <Dialog isOpen onClose={vi.fn()} title="T">
        <button>First</button>
        <button>Second</button>
      </Dialog>,
    )
    expect(screen.getByText('First')).toHaveFocus()
    await userEvent.tab({ shift: true })
    expect(screen.getByText('Second')).toHaveFocus()
  })

  it('clicking the overlay closes by default', async () => {
    const onClose = vi.fn()
    render(
      <Dialog isOpen onClose={onClose} title="T">
        <button>Inside</button>
      </Dialog>,
    )
    // The overlay is the dialog panel's parent.
    await userEvent.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('clicking inside the panel never closes it', async () => {
    const onClose = vi.fn()
    render(
      <Dialog isOpen onClose={onClose} title="T">
        <p>Body text</p>
      </Dialog>,
    )
    await userEvent.click(screen.getByText('Body text'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('overlay click does nothing when closeOnOverlayClick is false', async () => {
    const onClose = vi.fn()
    render(
      <Dialog isOpen onClose={onClose} title="T" closeOnOverlayClick={false}>
        <button>Inside</button>
      </Dialog>,
    )
    await userEvent.click(screen.getByRole('dialog').parentElement as HTMLElement)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('locks body scroll while open and restores it on close', async () => {
    function Harness() {
      const [open, setOpen] = useState(true)
      return (
        <div>
          <button onClick={() => setOpen(false)}>Close</button>
          <Dialog isOpen={open} onClose={() => setOpen(false)} title="T">
            <p>body</p>
          </Dialog>
        </div>
      )
    }
    render(<Harness />)
    expect(document.body.style.overflow).toBe('hidden')
    await userEvent.click(screen.getByText('Close'))
    expect(document.body.style.overflow).toBe('')
  })
})
