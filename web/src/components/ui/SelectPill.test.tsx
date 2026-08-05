import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SelectPill } from './SelectPill'

describe('SelectPill', () => {
  it('is a native <select>, reachable by Tab and operable via selectOptions', async () => {
    const onChange = vi.fn()
    render(
      <SelectPill value="a" onChange={onChange} options={['a', 'b', 'c']} aria-label="Pick one" />,
    )
    await userEvent.tab()
    const select = screen.getByRole('combobox', { name: 'Pick one' })
    expect(select).toHaveFocus()
    await userEvent.selectOptions(select, 'b')
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('normalizes {value,label} options and marks disabled ones with a title', () => {
    render(
      <SelectPill
        value="live"
        onChange={vi.fn()}
        options={[
          { value: 'live', label: 'Live engine' },
          { value: 'planned', label: 'Planned engine', disabled: true, title: 'Not yet selectable' },
        ]}
        aria-label="Engine"
      />,
    )
    const disabledOption = screen.getByRole('option', { name: 'Planned engine' })
    expect(disabledOption).toBeDisabled()
    expect(disabledOption).toHaveAttribute('title', 'Not yet selectable')
  })

  it('associates supporting instructions with the native select', () => {
    render(
      <>
        <SelectPill
          value="a"
          onChange={vi.fn()}
          options={['a', 'b']}
          aria-label="Pick one"
          aria-describedby="pick-one-help"
        />
        <p id="pick-one-help">Choose the verified option.</p>
      </>,
    )

    expect(screen.getByRole('combobox', { name: 'Pick one' })).toHaveAccessibleDescription(
      'Choose the verified option.',
    )
  })
})
