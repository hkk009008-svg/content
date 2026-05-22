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
  const narrationOn = s.narration_mode && s.narration_mode !== 'none'

  return (
    <SettingsSection title="Audio & Voice">
      <div>
        <label className={LABEL_CLS}>Narration Mode</label>
        <select
          value={s.narration_mode || 'none'}
          onChange={e => update('narration_mode', e.target.value)}
          className={INPUT_CLS}
        >
          <option value="none">No Narration — characters speak their dialogue</option>
          <option value="omniscient">Omniscient Narrator — voiceover above the action</option>
          <option value="character_vo">Character Voiceover — inner monologue</option>
          <option value="documentary">Documentary — neutral informative narrator</option>
        </select>
      </div>

      {narrationOn && (
        <div>
          <label className={LABEL_CLS}>Narrator Voice</label>
          <select
            value={s.narrator_voice || 'auto'}
            onChange={e => update('narrator_voice', e.target.value)}
            className={INPUT_CLS}
          >
            <option value="auto">Auto — matches scene mood</option>
            <option value="Daniel">Daniel — Authoritative British</option>
            <option value="Callum">Callum — Intense, dramatic</option>
            <option value="Adam">Adam — Deep, commanding</option>
            <option value="Patrick">Patrick — Wise, elder</option>
            <option value="Clyde">Clyde — Warm storyteller</option>
            <option value="Charlotte">Charlotte — Warm British woman</option>
            <option value="Rachel">Rachel — Gentle female</option>
          </select>
        </div>
      )}

      <div>
        <label className={LABEL_CLS}>Voice Effect</label>
        <select
          value={s.voice_effect || 'none'}
          onChange={e => update('voice_effect', e.target.value)}
          className={INPUT_CLS}
        >
          <optgroup label="Clean">
            <option value="none">None — clean, unprocessed</option>
            <option value="warm_broadcast">Warm Broadcast — polished, compressed</option>
          </optgroup>
          <optgroup label="Cinematic">
            <option value="cinema_reverb">Cinema Reverb — large room echo</option>
            <option value="intimate_room">Intimate Room — small, close</option>
            <option value="cathedral">Cathedral — massive reverb</option>
            <option value="epic_narrator">Epic Narrator — booming, present</option>
            <option value="vintage_film">Vintage Film — old film bandwidth</option>
          </optgroup>
          <optgroup label="Special">
            <option value="telephone">Telephone — bandpass phone call</option>
            <option value="radio">Radio — compressed broadcast</option>
            <option value="megaphone">Megaphone — harsh, distorted</option>
            <option value="underwater">Underwater — muffled, submerged</option>
            <option value="dream_sequence">Dream Sequence — ethereal, slowed</option>
            <option value="robot">Robot — pitch shifted, chorus</option>
            <option value="whisper_intimate">Whisper Enhance — breathy, close</option>
          </optgroup>
        </select>
      </div>

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
