import { type ComponentProps } from 'react'
import PipelineLayout from '../pipeline/PipelineLayout'

/**
 * RunPage (stub) — renders the existing `PipelineLayout` with its full
 * callback set forwarded unchanged. `AppShell` threads every pipeline prop
 * (state + mutation callbacks, wrapped in `withRefresh` up in `App.tsx`)
 * straight through, so the live-run behavior is identical to the old
 * `mode === 'pipeline'` branch. Later tasks replace this with the redesigned
 * Run surface; for now it is a pass-through so nothing regresses.
 */

type Props = ComponentProps<typeof PipelineLayout>

export default function RunPage(props: Props) {
  return (
    <div data-page="run" className="h-full min-h-0 overflow-y-auto">
      <PipelineLayout {...props} />
    </div>
  )
}
