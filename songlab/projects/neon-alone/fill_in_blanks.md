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

## Section Coverage

- Production Notes: `source` roles=bass techniques=none
- Second Drop: `source` roles=bass, chords, clap, drums, fx, hat, impact, kick, lead, noise, reverse, ride, riser, sub, vocal techniques=layering, reverb, reverse, sidechain, automation, stereo, distortion
- Intro: `source` roles=chords, lead, fx techniques=filtering, reverb
- Verse: `source` roles=automation, bass, chords, fx, lead, drums, vocal techniques=automation, filtering, eq, reverb
- Build: `source` roles=clap, crowd, drums, hat, kick, lead, pluck, riser, snare, fx, automation, noise, guitar techniques=filtering, layering, tease_hook, automation, delay
- Intro: `source` roles=automation, bass, drums, fx, lead, riser, chords techniques=arrangement_reuse, automation, filtering, reverb
- Production Notes: `source` roles=bass, chords, clap, crash, drums, hat, kick, lead, snare, sub techniques=layering, sidechain
- Break: `source` roles=automation, chords, lead, reverse, vocal, fx techniques=automation, filtering, reverb, reverse, sidechain
- Build: `source` roles=automation, drums, hat, lead, riser, clap, fx, noise techniques=automation, filtering, layering, delay
- Drop: `source` roles=bass, chords, crash, drums, fx, hat, lead, ride, sub techniques=layering, sidechain, eq, compression, stereo
- Outro: `source` roles=automation, chords, downlifter, drums, impact, lead, fx techniques=automation, filtering, reverb, sidechain

## Post-Render Loop

- Render the project or inspect existing stems.
- Run `python3 tools/does_this_sound_good.py --project-id <project-id> --format markdown`.
- Convert the checker's loudness, low-end, stereo, missing-audio, and arrangement findings into the next Songlab iteration note.
