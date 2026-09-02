# Fill In The Blanks: Neon Alone

## Policy

Infer plausible production defaults from the brief; do not claim exact original samples, patches, MIDI, or mix values without evidence.

## Defaults

- Style lane: `bright_future_bass`
- Tempo: `142`
- Key: `D major`

## Inferred Decisions

- techniques: Second Drop: filled techniques automation, distortion, stereo. Reason: The section needed production moves, not only instrument names.
- track roles: Intro: filled roles fx. Reason: Section role coverage was incomplete for a buildable arrangement.
- techniques: Intro: filled techniques reverb. Reason: The section needed production moves, not only instrument names.
- track roles: Verse: filled roles drums, vocal. Reason: Section role coverage was incomplete for a buildable arrangement.
- techniques: Verse: filled techniques eq, reverb. Reason: The section needed production moves, not only instrument names.
- track roles: Build: filled roles automation, fx, guitar, noise. Reason: Section role coverage was incomplete for a buildable arrangement.
- techniques: Build: filled techniques automation, delay. Reason: The section needed production moves, not only instrument names.
- track roles: Intro: filled roles chords. Reason: Section role coverage was incomplete for a buildable arrangement.
- track roles: Break: filled roles fx. Reason: Section role coverage was incomplete for a buildable arrangement.
- track roles: Build: filled roles clap, fx, noise. Reason: Section role coverage was incomplete for a buildable arrangement.
- techniques: Build: filled techniques delay. Reason: The section needed production moves, not only instrument names.
- track roles: Drop: filled roles sub. Reason: Section role coverage was incomplete for a buildable arrangement.
- techniques: Drop: filled techniques compression, eq, sidechain, stereo. Reason: The section needed production moves, not only instrument names.
- track roles: Outro: filled roles fx. Reason: Section role coverage was incomplete for a buildable arrangement.
- lane defaults: Production Notes: added bass starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Second Drop: added chords, bass, lead, kick, snare, hat starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Verse: added chords, bass, lead, kick, snare starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Build: added chords, lead, clap, automation starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Intro: added chords, bass, kick, snare starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Production Notes: added chords, bass, clap starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Break: added chords, lead starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Build: added lead, kick, snare, clap, hat starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Drop: added chords, bass, lead, kick, snare, hat starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- lane defaults: Outro: added chords, lead, kick, snare starter lane data. Reason: No explicit enough lane events existed for those musical roles.
- arrangement: Classified 1 described-but-unplaced section(s): section-07 -> second_drop. Reason: They carried real parts and would otherwise have been dropped from the build entirely.
- arrangement: Reordered sections into playback order: intro -> verse -> build -> intro -> drop -> break -> build -> second_drop -> second_drop -> outro. Reason: They were parsed in the order the walkthrough discussed them (second_drop -> intro -> verse -> build -> intro -> second_drop -> break -> build -> drop -> outro), which is not the order the song plays.
- arrangement: Resolved 4 duplicated section(s): section-06: intro -> break, folded section-08 into the break, folded section-09 into the build, folded section-07 into the second_drop. Reason: The walkthrough described some parts more than once; laid out literally that produces repeated sections with nothing between them.
- arrangement: Set section lengths from style defaults; the arrangement runs 80 bars (~2.3 min at 142 BPM). Reason: No timecodes were available, and a section with no length gets an arbitrary one at build time.
- arrangement: Reordered sections into playback order: intro -> verse -> build -> drop -> break -> second_drop -> outro. Reason: They were parsed in the order the walkthrough discussed them (intro -> verse -> build -> break -> drop -> second_drop -> outro), which is not the order the song plays.
- missing step: High-pass everything that is not the low end: Give each lane a high-pass: chords 180 Hz, lead 220 Hz (250 in the drop), plucks 250 Hz, vocals 150 Hz, guitars 120 Hz, FX/risers/noise/crashes 300 Hz. Only the kick, sub and bass are exempt. Record it as a mix note so the renderer and a human agree. Reason: Every melodic and FX layer carries low rumble that adds up into the 200-500 Hz range, which is exactly where the checker reports mud.
- missing step: Keep the bottom mono: State a mono crossover — 110 Hz for house, 130 for future bass and modern EDM, 150 for darker bass music — and mark the kick, sub and bass lanes mono. Apply every widener, chorus and reverb send after the lane's high-pass, never before it. Reason: Widened low frequencies partially cancel when the track is played in mono, so the bass disappears on phones and club systems.
- missing step: Decide what is allowed to be wide: Assign each lane a width tier: centre-locked (kick, sub, bass, snare body, the main hook), mid 0.25-0.40 (chords, hats, plucks), wide 0.60-0.80 (the lead octave double, vocal chops, FX, reverb returns). Keep no more than two or three lanes wide at once. Reason: When every layer is widened, nothing sounds wide, the centre hollows out, and stereo correlation drops far enough for the checker to flag it.
- missing step: Set a level ladder and a peak budget: Write lane offsets relative to the kick: kick 0 dB, sub -2, bass -5, lead -4, clap -6, chords -7, vocal -8, plucks -12, FX -12, hats -14. Set a master ceiling of -1.0 dBFS and allow only the drop within a dB of it. Reason: With no target levels the render is balanced by whatever the generator's defaults happen to be, which is how a mix ends up either quiet or squashed.
- missing step: Stop the drums repeating bar for bar: Scope some drum events to particular bars: an open hat on odd bars, a kick dropped on the last beat of bar 4, an extra clap on bar 6. Small differences, but they stop the pattern reading as a loop. Reason: The renderer reuses an unscoped pattern for every bar, so without bar-scoped events the sixteenth bar of a drop is identical to the first.
- missing step: Give every named part something to play: For each role with no lane events, either write a starter pattern for it or take it out of the section. An empty lane is worse than an absent one, because it hides the fact that the part was never made. Reason: A role listed in a section but never given events becomes a track with no clips: the project looks fuller than it sounds, and the checker reports it as missing audio.
- missing step: Derive every melodic part from one idea: Pick the drop's hook as canonical and derive the rest from it: the intro states a truncated filtered version, the break plays it slower or on a different instrument, the outro plays its first two notes. Same idea, different treatment. Reason: Unrelated melodies in the intro, drop and break give a song three identities and no hook; one idea restated is what makes an arrangement cohere.

## Missing Steps

Production steps the brief never mentioned, added so the song is buildable and so the sound check has less to complain about.

- **High-pass everything that is not the low end** — Give each lane a high-pass: chords 180 Hz, lead 220 Hz (250 in the drop), plucks 250 Hz, vocals 150 Hz, guitars 120 Hz, FX/risers/noise/crashes 300 Hz. Only the kick, sub and bass are exempt. Record it as a mix note so the renderer and a human agree. _(pre-empts: Low mids)_
  - Why: Every melodic and FX layer carries low rumble that adds up into the 200-500 Hz range, which is exactly where the checker reports mud.
- **Keep the bottom mono** — State a mono crossover — 110 Hz for house, 130 for future bass and modern EDM, 150 for darker bass music — and mark the kick, sub and bass lanes mono. Apply every widener, chorus and reverb send after the lane's high-pass, never before it. _(pre-empts: Mono)_
  - Why: Widened low frequencies partially cancel when the track is played in mono, so the bass disappears on phones and club systems.
- **Decide what is allowed to be wide** — Assign each lane a width tier: centre-locked (kick, sub, bass, snare body, the main hook), mid 0.25-0.40 (chords, hats, plucks), wide 0.60-0.80 (the lead octave double, vocal chops, FX, reverb returns). Keep no more than two or three lanes wide at once. _(pre-empts: Stereo)_
  - Why: When every layer is widened, nothing sounds wide, the centre hollows out, and stereo correlation drops far enough for the checker to flag it.
- **Set a level ladder and a peak budget** — Write lane offsets relative to the kick: kick 0 dB, sub -2, bass -5, lead -4, clap -6, chords -7, vocal -8, plucks -12, FX -12, hats -14. Set a master ceiling of -1.0 dBFS and allow only the drop within a dB of it. _(pre-empts: Level)_
  - Why: With no target levels the render is balanced by whatever the generator's defaults happen to be, which is how a mix ends up either quiet or squashed.
- **Stop the drums repeating bar for bar** — Scope some drum events to particular bars: an open hat on odd bars, a kick dropped on the last beat of bar 4, an extra clap on bar 6. Small differences, but they stop the pattern reading as a loop. _(pre-empts: Punch)_
  - Why: The renderer reuses an unscoped pattern for every bar, so without bar-scoped events the sixteenth bar of a drop is identical to the first.
- **Give every named part something to play** — For each role with no lane events, either write a starter pattern for it or take it out of the section. An empty lane is worse than an absent one, because it hides the fact that the part was never made. _(pre-empts: Missing audio)_
  - Why: A role listed in a section but never given events becomes a track with no clips: the project looks fuller than it sounds, and the checker reports it as missing audio.
- **Derive every melodic part from one idea** — Pick the drop's hook as canonical and derive the rest from it: the intro states a truncated filtered version, the break plays it slower or on a different instrument, the outro plays its first two notes. Same idea, different treatment.
  - Why: Unrelated melodies in the intro, drop and break give a song three identities and no hook; one idea restated is what makes an arrangement cohere.

## Section Coverage

- Intro: `source` roles=chords, lead, fx techniques=filtering, reverb
- Verse: `source` roles=automation, bass, chords, fx, lead, drums, vocal techniques=automation, filtering, eq, reverb
- Build: `source` roles=clap, crowd, drums, hat, kick, lead, pluck, riser, snare, fx, automation, noise, guitar techniques=filtering, layering, tease_hook, automation, delay
- Drop: `source` roles=bass, chords, crash, drums, fx, hat, lead, ride, sub techniques=layering, sidechain, eq, compression, stereo
- Break: `source` roles=automation, bass, drums, fx, lead, riser, chords, reverse, vocal techniques=arrangement_reuse, automation, filtering, reverb, reverse, sidechain
- Second Drop: `source` roles=bass, chords, clap, drums, fx, hat, impact, kick, lead, noise, reverse, ride, riser, sub, vocal, crash, snare techniques=layering, reverb, reverse, sidechain, automation, stereo, distortion
- Outro: `source` roles=automation, chords, downlifter, drums, impact, lead, fx techniques=automation, filtering, reverb, sidechain
- Production Notes: `source` roles=bass techniques=none

## Post-Render Loop

- Render the project or inspect existing stems.
- Run `python3 tools/does_this_sound_good.py --project-id <project-id> --format json > check.json`.
- Feed it straight back: `python3 tools/fill_in_blanks.py --input-json <spec> --feedback-json check.json`. Every finding is tagged with the requirements that would have prevented it, so the next pass gets measured steps instead of fresh guesses.
- Re-materialize and log the pass with `python3 tools/songlab.py iterate --project-id <id> --note ...`.
