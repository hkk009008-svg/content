import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

const INPUT_CLS =
  'w-full bg-editorial-ink border border-editorial-rule rounded-lg ' +
  'px-3 py-2 text-sm text-editorial-ivory'

const LABEL_CLS =
  'text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider'

export function AudioSection({ s, update }: Props) {
  return (
    <SettingsSection title="Audio & Voice">
      <div>
        <label className={LABEL_CLS}>Music Mastering</label>
        <select
          value={s.music_mastering || 'cinema_master'}
          onChange={e => update('music_mastering', e.target.value)}
          className={INPUT_CLS}
        >
          <option value="none">None — raw, unmastered</option>
          <option value="cinema_master">Cinema Master — warm, wide, polished</option>
          <option value="lo_fi">Lo-Fi — vinyl warmth, tape hiss</option>
          <option value="epic_wide">Epic Wide — orchestral, boosted lows</option>
          <option value="intimate_acoustic">Intimate Acoustic — close, minimal</option>
          <option value="dark_ambient">Dark Ambient — deep, spacious, mysterious</option>
        </select>
      </div>

      <div className="bg-editorial-ink border border-editorial-rule rounded-lg p-3">
        <span className="text-eyebrow text-editorial-brass font-mono font-bold uppercase">
          40 Voice Delivery Styles
        </span>
        <p className="text-eyebrow text-editorial-ivory-mute mt-1 leading-relaxed">
          Set per dialogue line: whisper, angry, crying, scared, sarcastic, commanding, exhausted,
          drunk, seductive, and 31 more. The dialogue writer auto-assigns delivery based on context.
        </p>
      </div>
    </SettingsSection>
  )
}
