/* 7px status indicator dot. Status name maps directly to the token applied. */

export type Status = 'ok' | 'warn' | 'fail' | 'idle' | 'run'

interface Props {
  status: Status
}

const STATUS: Record<Status, string> = {
  ok: 'bg-ok',
  warn: 'bg-warn',
  fail: 'bg-fail',
  idle: 'bg-dim',
  run: 'bg-acc',
}

export function StatusDot({ status }: Props) {
  return (
    <span
      aria-hidden
      className={['inline-block h-[7px] w-[7px] rounded-full', STATUS[status]].join(' ')}
    />
  )
}
