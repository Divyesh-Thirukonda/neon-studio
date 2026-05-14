# Producer Step-by-Step: Dark Trap/Festival Drop Walkthrough

This file converts the full video transcript into a DAW-neutral production recipe. It is written for a normal producer using any modern production tool, not for one specific app. Use the concepts, roles, and processing chains with your own samples and presets.

## Approximation vs Exact Source

This document separates three levels of evidence:

1. Transcript facts: things the producer says or clearly demonstrates in the walkthrough.
2. Local approximation: the Neon Studio reconstruction in `factory/projects/just-cant-stop.neon.json`, rendered stems, and `render_just_cant_stop.py`.
3. Exact source claims: original sample filenames, exact MIDI notes, plugin presets, automation curves, fader balances, and Ableton bar positions.

Only the first two are available locally. Do not treat local bar numbers, patch settings, sample roles, or mix balances as proof of the original DAW session. Any exact-source claim still needs the original project file, screenshots, isolated stems, preset files, or sample filenames.

## Timestamped Video Map

Use this map if you need to line the written steps back up with the video.

1. 0:50-1:36: Producer explains the goal of the video, promises a chronological walkthrough, and says plugins/sample choices will be disclosed.
2. 1:45-2:36: Original idea starts from the main bass-synth section. For an intro track, add more drama with sweeps, reverses, and a long one-note bass-synth sample.
3. 2:44-3:39: The long sample becomes the core melody. Layer it with a simple analog bass, likely from a hardware-style synth such as Super 6.
4. 3:39-4:44: Intro adds simple clap layers and an Omnisphere room/delay layer from Sonic Extensions-style sounds.
5. 4:44-5:34: Melody is intentionally darker than older happier/catchier work.
6. 5:41-6:35: Add random stereo breath sounds, a found vocal sample, and dynamic risers into the next section.
7. 6:57-8:03: Pre-build loops and chops the vocal, then brightens it with Fresh Air.
8. 8:11-10:16: Add an aggressive pre-build synth/preset, process with multiband compression and Crystalline reverb.
9. 10:16-11:05: Use reverb contrast. Some sounds are dry, some are roomy. Keep clap continuity across sections.
10. 11:13-12:15: Build uses delayed material bouncing left and right while the main hype layer continues.
11. 12:15-14:40: Add Rave Generator old-school layers and tease the upcoming drop lead before the drop.
12. 14:40-16:17: Use a strong build sample with chants, trap snares, and white noise. Add odd background filler.
13. 16:25-19:20: Drop vocal chops, call-and-response phrases, vocal tags, and delay movement act as phrase markers.
14. 20:08-21:39: Kick uses a clicky sample and a Pultec-style low boost around 100 Hz.
15. 21:39-23:24: Snare/clap stack uses multiple layers, including jingle and offbeat trap snare elements, with minimal EQ.
16. 23:33-24:18: Add a tiny high hat tick, heavily high-passed, to occupy its own high-frequency slot.
17. 24:25-26:28: Crash stack combines open hat, shaped snare/noise, and synth white noise for mono and stereo coverage.
18. 26:28-27:51: Mid/side EQ is mentioned as useful, then another small offbeat hat is added for bounce.
19. 27:51-30:53: Serum-style bass/wobble design starts simple, then uses envelope movement, OTT/multiband, white noise, filter routing, and drive.
20. 31:10-36:23: Drop lead stack uses high sizzle, a rough Omnisphere source, waveshaping, clipping, low cuts, Crystalline, Snap Heap, and post-effect EQ.
21. 36:33-38:07: Reverb/glitch tails and chaotic background filler are chopped and kept as ear candy.
22. 38:14-40:03: Sub patch uses a simple low oscillator plus white noise routed into a driven filter.
23. 40:10-41:18: First drop is up an octave, second drop goes lower. Sustained sub can work better than matching every wobble pulse.
24. 41:27-42:37: Second part reuses earlier material and adds Humanoid/vocoder-style weirdness as background space.
25. 42:37-43:53: Second drop introduces a huge preset/patched synth, then processes it for size and aggression.
26. 43:53-45:45: Add old-school trap sirens and laser sounds with pitch movement and heavy distortion.
27. 45:51-47:42: Add a Shadow/UK bass-style sample, PolySaturator, Serum FX preset processing, and mono control.
28. 47:42-50:24: Add old-school trap stabs with VintageVerb, OTT, soothe, and low cuts. Keep useful distortion artifacts if they work.
29. 50:24-50:54: End with a callback to the beginning.
30. 50:54-52:25: Use Transit/Transit 2 or a similar macro transition tool for gritty delays, filters, chorus, and movement.
31. 52:25-53:31: Closing note: the walkthrough is meant to share practical process and plugin choices openly.

## 1. Overall Target

1. Build a dark, trap-influenced electronic track with an intro, hype pre-build, first drop, second build, second drop, and short outro callback.
2. Keep the arrangement simple in terms of core musical material, but fill transitions and drops with ear candy, vocal chops, risers, tags, glitch tails, and one-off texture sounds.
3. Prioritize sample selection. Many important sounds are not designed from scratch. They come from strong source samples, presets, or packs, then get processed.
4. Keep the main musical idea centered around one memorable bass-synth line.
5. Let contrast do a lot of the work: dry basses against roomy leads, mono/sub elements against wide hats and crashes, simple drums against chaotic fills.
6. Do not over-polish every artifact. Some distortion, phasing, grit, and rough edges are kept because they add character.

## 2. Session Setup

1. Set the project around a trap/festival tempo. The local project uses 150 BPM.
2. Use a minor/dark tonal center. The local project notes point toward F minor / Ab major.
3. Organize the session top to bottom:
   - Vocal chops and tags
   - Transition effects and risers
   - Main synths and leads
   - Bass and sub
   - Drums
   - Background filler and ear candy
4. Work chronologically through the arrangement:
   - Pre-intro
   - Intro
   - Pre-build / bridge
   - Build
   - Drop 1
   - Second part / second build
   - Drop 2
   - Outro callback

## Local Project Approximation Arrangement Map

This map comes from `factory/projects/just-cant-stop.neon.json`, not from the original producer's DAW session. The project JSON stores zero-based `startBar` values; the table below uses normal one-based bar numbers for producer readability.

| Bars | Local section | Active local lanes | Producer purpose |
| --- | --- | --- | --- |
| 1-8 | Pre-intro / reverse setup | Sample Bass Synth, Analog Bass, Transit Macro FX, Dynamic Risers, Stereo Breaths from bar 3 | Establish the main sample-bass identity, reverse/impact drama, and early atmosphere before the full groove is revealed. |
| 9-12 | Intro expands | Sample Bass Synth, Analog Bass, Dark Room Layer, Same Clap Stack, Stereo Breaths, Transit Macro FX tail | Bring in the room/delay layer and clap continuity while keeping the arrangement sparse. |
| 13-16 | Vocal pre-build pickup | Previous intro lanes plus Fresh Vocal Chops | Introduce the found vocal idea as a loop/chop before the heavier bridge texture arrives. |
| 17-22 | Bridge / old-school color | Vocal Chops, Rave Generator, intro bass/support lanes, room, claps, breaths | Add the rave-generator stab color and increase rhythmic density without exposing the full drop. |
| 23-24 | Build handoff | Dynamic Risers return over the bridge lanes | Use risers and filter/volume motion to point toward the formal build. |
| 25-28 | Build loop | Build Loop, Transit Macro FX, Random Filler, Vocal Chops, Rave Generator, risers | Let the Green Room-style build sample, macro movement, and odd filler create the main pre-drop lift. |
| 29-32 | Final Drop 1 tease | Lead Tease joins the build loop, risers, macro FX, vocal chops, rave stabs, random filler | Preview the drop rhythm without giving away the full lead stack. |
| 33-35 | Drop 1 phrase A | Drop Drums, Drop Vocals, Drop Lead, Driven Sub, Crash Layers, Same Clap Stack | Hit the first drop with the octave-up lead, vocal rhythm, sub support, and full drum/crash stack. |
| 36-44 | Drop 1 fills | Drop 1 lanes plus Glitch Tail from bar 36 | Keep the drop alive with chopped reverb/glitch-tail ear candy while the main phrase continues. |
| 45-48 | Drop 1 answer / transition | Drop 1 lanes, Glitch Tail, Sirens Lasers from bar 45, Stereo Breaths re-enter at bar 47 | Use siren/laser answers and breath texture to push out of the first drop. |
| 49-54 | Second part reset | Sample Bass Synth callback, Analog Bass callback, Dark Room Layer, Random Filler, Stereo Breaths | Return to the opening identity with added humanoid/vocoder-style background space. |
| 55-56 | Second build pickup | Dynamic Risers return while second-part filler continues | Start the second lift before the build loop fully re-enters. |
| 57-60 | Second build | Fresh Vocal Chops, Build Loop, Rave Generator, Transit Macro FX, Dynamic Risers, Random Filler | Rebuild energy with familiar vocal/build materials while keeping the background busier than the first pass. |
| 61-64 | Second drop tease | Lead Tease returns over the second build | Signal the upcoming second drop and finish the build macro movement. |
| 65-68 | Drop 2 hit | Drop Drums, Drop Vocals, Same Clap Stack, Driven Sub, Crash Layers, Second Drop Synths, Sirens Lasers | Swap the first-drop lead focus for the huge second-drop synth layer and heavier siren/laser treatment. |
| 69-70 | Drop 2 / outro bleed | Drop 2 lanes plus Random Filler outro chaos | Let the final drop decay into chaotic filler instead of cutting cleanly. |
| 71-72 | Ending transition | Drop 2 lanes, Random Filler, Transit Macro FX ending transition | Use the transition macro as the short callback/outro gesture. |

Local clip anchors by role:

- `sample-bass-synth`: bars 1-24 and 49-56.
- `analog-bass`: bars 1-24 and 49-56.
- `room-layer`: bars 9-24 and 49-56.
- `clap-stack`: bars 9-24, 33-48, and 65-72.
- `breaths`: bars 3-24 and 47-64.
- `vocal-chops`: bars 13-32 and 57-72.
- `risers`: bars 1-8, 23-32, and 55-64.
- `prebuild-drums`: bars 25-32 and 57-64.
- `rave-generator`: bars 17-32 and 57-64.
- `lead-tease`: bars 29-32 and 61-64.
- `random-filler`: bars 25-32, 49-64, and 69-72.
- `drop-drums`, `drop-vocals`, `sub`, and `crash-layers`: bars 33-48 and 65-72, with `drop-lead` only on bars 33-48 and `second-drop-synths` only on bars 65-72.
- `glitch-tail`: bars 36-47.
- `sirens-lasers`: bars 45-48 and 65-72.
- `transition-fx`: bars 1-8, 25-32, 57-64, and 71-72.

## 3. Core Sound Palette

1. Long granular bass-synth sample
   - Use a long one-note synth or bass sample as the center of the track.
   - Long samples are easier to turn into a playable main synth because they do not need obvious looping tricks.
   - Write a simple bass-synth melody from this one source.

2. Analog bass support
   - Layer the sample bass-synth with a simple analog-style bass.
   - Keep it restrained. The goal is body and authenticity, not complexity.
   - A real hardware-style synth or a convincing analog plugin works.

3. Room layer
   - Add an atmospheric synth layer with built-in room, delay, or space.
   - Omnisphere-style preset libraries are appropriate here.
   - The layer should make the intro feel wider and darker without replacing the main line.

4. Random human textures
   - Add breath sounds or similar stereo organic sounds.
   - Keep them low enough that they feel like movement, not a lead.
   - Use them to widen the intro and make the production feel less static.

5. Vocal snippets
   - Use small vocal samples as rhythmic hooks, not necessarily full lyrics.
   - Chop, repeat, brighten, delay, and pan them.
   - Let them act as call-and-response moments before changes.

### Sample / Source Selection Checklist

Use this before heavy processing. A weak source usually costs more time than it saves.

| Role | Choose a source that has | Reject or replace if |
| --- | --- | --- |
| Long bass-synth sample | A sustained one-note tone, clear pitch center, enough length to chop or stretch, and a memorable midrange identity. | It loops obviously, has baked-in drums, changes chords, or loses identity when pitched. |
| Analog bass support | Simple low-mid body, stable pitch, and restrained movement. | It competes with the main sample-bass line or has too much top-end character. |
| Room / atmosphere layer | Built-in space, dark tone, and a tail that supports the intro without becoming the hook. | It masks the main riff or makes the intro feel washed out before the build. |
| Breath / human texture | Stereo detail, short phrases, and organic movement. | It sounds like a lead vocal, contains distracting words, or pokes out during drop sections. |
| Vocal chop / tag | A clean syllable or phrase with rhythm, attitude, and room for delay throws. | The lyric becomes the main song identity, the timing cannot be tightened, or the source is too noisy to brighten. |
| Build loop | Chants, trap snares, big snare/noise, and enough energy to lift into the drop. | It dictates the whole groove in a way that fights the song or has unusable tonal content. |
| Rave / trap stab | Immediate old-school attitude, short decay, and a pitch that can sit against the bass line. | It sounds too happy, too clean, or too harmonically dense for the dark arrangement. |
| Kick | Clicky transient plus low punch around the song's low-end pocket. | It needs extreme EQ to be heard or fights the sub fundamental. |
| Clap / snare stack | Separate layers for body, snap, jingle/character, and offbeat trap flavor. | Every layer hits the same frequency range or the stack gets wider but not stronger. |
| Tiny hat / offbeat hat | Small high-frequency tick that stays out of the snare and vocal range. | It becomes a main rhythm or sounds harsh after high-pass. |
| Crash / noise stack | Mono impact plus wide high-end, with open-hat/snare/noise layers that complement each other. | The stack has no center hit or turns into uncontrolled white-noise wash. |
| Drop 1 lead source | Rough attitude, strong contour, and enough mid/high bite to survive distortion. | It only works solo, loses hook in context, or needs low end that belongs to the sub. |
| Driven sub source | Stable low oscillator or simple patch that accepts drive without losing pitch. | It wobbles too much, has stereo low end, or masks the kick transient. |
| Second-drop huge synth | Lower/heavier identity than Drop 1, strong midrange, and useful harmonics after saturation. | It is only louder, not different; or it hides the vocal tag, sirens, and sub. |
| Siren / laser | Fast pitch motion, recognizable old-trap gesture, and controllable low end. | It has too much bass, cannot be mono-compatible, or distracts from the second-drop synth. |
| Random filler / glitch tail | Weird texture that fills gaps at low level and can be chopped rhythmically. | It becomes identifiable in a bad way or competes with the main hook. |
| Transition FX | Useful movement over a short range: filter, delay, pitch, riser, downlifter, or reverb swell. | It sounds like a stock effect pasted on top instead of part of the phrase. |

## 4. Pre-Intro

1. Start with drama before the main groove enters.
2. Take the first main bass-synth sound and create a reverse version of it.
3. Add sweeps, risers, and reversed effects leading into the first recognizable hit.
4. Keep the sound sparse so the opening feels intentional and cinematic.
5. Use this section to introduce the sonic world before the drums fully arrive.

## 5. Intro

1. Bring in the main bass-synth line.
   - Source: a long one-note bass/synth sample.
   - Program it into a simple repeated melody.
   - Make it the identity of the whole track.

2. Add the analog bass layer.
   - Keep it very simple.
   - Use it to reinforce the fundamental weight of the sample synth.

3. Add a clap stack.
   - Use two or more simple clap samples.
   - Do not overwork them.
   - Reuse this clap stack throughout the song so the rhythm has continuity.

4. Add the room/space layer.
   - Use a preset or patch with room tone and delay.
   - Keep it tucked behind the main bass-synth.

5. Add breaths or odd stereo textures.
   - Place them between phrases or under the main line.
   - Treat them as width and mood.

6. Add a short vocal sample.
   - Choose something that feels cool even if the lyric is not central yet.
   - Let it lead naturally into the next section.

7. Add dynamic risers at the end of the intro.
   - Automate volume, filter, pitch, or reverb intensity upward.
   - Use risers as part of the composition, not only as stock transition noise.

## 6. Pre-Build / Bridge

1. Loop or repeat the same vocal idea from the intro.
2. Chop the vocal into a more rhythmic pattern.
3. Brighten the vocal.
   - Suggested plugin: Slate Digital Fresh Air.
   - Use mid and high bands to add shine and presence.
   - This can make dull vocal chops feel immediately more exciting.

4. Add a rhythmic synth or preset layer.
   - The video references Omnisphere Sonic Extensions, especially Seismic Shock, Unclean Machine, and Undercurrent-style sounds.
   - Pick something aggressive and rhythmic.
   - Freeze or print it if needed, but keep notes about the source if you plan to explain or revise later.

5. Process the pre-build synth.
   - Add a multiband compressor similar to OTT. The video mentions Dank Sauce as an alternative.
   - Add Crystalline or another bright/metallic reverb.
   - Keep the reverb somewhat springy or harsh if the track wants a more aggressive tone.

6. Maintain dynamic contrast.
   - Some elements should be very dry.
   - Some elements should be very reverberant.
   - This dry/wet contrast makes the production feel larger than the number of tracks suggests.

## 7. Build Into Drop 1

1. Extend the pre-build energy with delayed vocal chops.
2. Use delays that bounce left and right.
   - Keep the movement audible.
   - The bouncing delays help the build feel hectic and wide.

3. Keep the main pre-build rhythmic layer moving underneath.
4. Add old-school rave/trap flavor.
   - Suggested source: Rave Generator or a similar 90s/early-2000s rave sample instrument.
   - Use classic stabs, hits, or chord intervals that feel slightly wonky.
   - Layer these against the existing bass-synth line for a rougher old-school character.

5. Tease the coming drop lead during the build.
   - Bring in a small version of the drop lead rhythm before the drop.
   - Keep it low or filtered.
   - The goal is to tell the listener what is coming without fully revealing it.

6. Use a strong build sample if it works.
   - The transcript references Green Room sample packs.
   - A build can include chants, trap snares, white noise, and a big snare.
   - If the sample already works, do not replace it only for pride.

7. Add random filler in the background.
   - Drag in odd sounds, resample them, or freeze them.
   - Keep them low.
   - They do not need to carry melody. They fill negative space and add personality.

## 8. Drop 1: Vocal Elements

1. Place vocal chops at the top of the drop section.
2. Create a short rhythmic vocal phrase.
   - Chop the vocal tightly.
   - Add heavy delay and stereo movement.
   - Let it feel hectic.

3. Add call-and-response vocal moments in empty spaces.
   - The video describes hearing a phrase like a response in a break.
   - Use the same rhythm or melody as the synth break so the vocal locks into the drop.

4. Add a producer-style tag or recognizable vocal stamp if appropriate.
   - Treat it like a hip-hop tag.
   - Process with chorus, OTT/multiband compression, Fresh Air, or other brightening.
   - Place tags before changes so they announce a new phrase.

5. Use vocal breaks to signal arrangement changes.
   - Drop hits phrase 1.
   - Vocal/tag break.
   - Switch to the next synth layer or variation.

## 9. Drop 1: Drums

1. Kick
   - Use a big, clicky kick.
   - Add low-end weight with a Pultec-style EQ.
   - Boost around 100 Hz or use a similar low-frequency boost.
   - Keep the change subtle. The goal is a cleaner rumble and more body.

2. Snare and clap stack
   - Layer multiple snare/clap sounds.
   - Include one layer with a little jingle or character.
   - Include one trap-style snare that can also hit slightly off-grid.
   - Do not assume every layer needs EQ if the stack already hits well.

3. Offbeat snare flavor
   - Add a trap snare or rim-type sound on offbeats.
   - Also layer it with the main snare when useful.
   - This makes the groove feel more trap-influenced and less clean.

4. Tiny high hat
   - Add a very small, high-frequency hat or tick.
   - Keep the rhythm simple and repetitive.
   - High-pass aggressively. The transcript references a cut around 474 Hz.
   - Let this hat occupy a frequency range the other drums do not dominate.

5. Crash stack
   - Build the crash from multiple layers if one sample is not enough.
   - Include an open hip-hop hat pitched down.
   - Add a snare/noise layer shaped to mimic a crash with a slower attack.
   - Add white noise from a synth such as Operator.
   - Make sure the stack covers mono center, stereo sides, and wide high-end energy.

6. Extra offbeat hat
   - Add a small offbeat hat that sits almost subliminally in the groove.
   - It should add bounce without becoming a main rhythm.

## 10. Drop 1: Bass, Sub, and Wobbles

1. Create a simple Serum-style wobble or bass hit.
   - Start with a basic waveform.
   - Use an envelope or LFO to shape movement.
   - Add OTT or multiband compression.
   - Add white noise through the filter.
   - Increase filter drive for aggression.

2. Keep the sound design simple before processing.
   - The raw patch can be plain.
   - The power comes from filter drive, white noise, distortion, and compression.

3. Create the sub patch.
   - Use a simple triangle, saw, or sine-like low oscillator.
   - A triangle/saw variation can feel slightly thicker than a pure sine.
   - Add bright white noise routed into the filter.
   - Drive the filter hard.
   - The filter drive clips and excites the bass so it reads on more systems.

4. Let the sub sustain through wobble gaps when it feels better.
   - The visible synth waveform may pulse up and down.
   - The sub does not always need to copy the exact movement.
   - Long sustained sub notes can make the drop feel fuller and more continuous.

5. First drop octave strategy
   - Put the first drop lead or main synth up an octave.
   - Save the lower, heavier version for the second drop.

### Driven Sub Patch Appendix

Use this as a generic Serum-style or stock-synth substitute for the local `Driven Sub` lane. The local renderer approximates it with a triangle core, sine support, a small amount of bright noise into drive, and long sustained notes under the wamps.

1. Oscillator core
   - Main oscillator: triangle, soft saw-triangle, or sine/triangle blend.
   - Pitch: fundamental octave, often around the same root as the drop bass. Drop it one octave if it competes with the lead.
   - Level target: the clean oscillator should carry most of the weight before processing.
   - Optional support oscillator: sine at the same pitch, mixed 20-40 percent under the triangle if the patch needs cleaner low fundamental.

2. Noise and filter drive
   - Noise source: bright white noise or high-passed noise.
   - Noise level: very low, around 2-8 percent. It should add edge to the filter, not sound like a separate hiss layer.
   - Filter: low-pass, 12 dB or 24 dB style.
   - Cutoff starting range: about 120-450 Hz for the sub lane. Raise only enough for the driven edge to read.
   - Resonance: low to moderate, roughly 0-20 percent.
   - Drive: medium-high, roughly 40-75 percent, or until the sub starts speaking on small speakers without becoming fuzzy.

3. Envelope and movement
   - Amp attack: 0-10 ms.
   - Decay: 60-140 ms.
   - Sustain: 70-90 percent for sustained drop notes.
   - Release: 80-220 ms, long enough to avoid clicks but short enough not to smear the next root.
   - Optional LFO/envelope on filter cutoff: small depth, roughly 5-20 percent, synced to the wobble phrase only if the sub needs visible movement.
   - Do not force the sub to retrigger every wobble. In this local approximation, bars 33-48 and 65-72 use longer sub continuity under the moving synths.

4. Processing chain
   - First: clean utility or mono control. Keep the fundamental mono.
   - Second: soft clip, tube drive, or filter drive. Push until harmonics are audible, then back off slightly.
   - Third: light OTT/multiband only if the sub disappears on smaller playback. Keep amount low, roughly 10-30 percent.
   - Fourth: sidechain or volume shaper keyed by the kick. Use enough ducking for kick clearance without making the sub pump like a lead.
   - Final EQ: high-cut or low-pass anything that fights the lead. Let the lead own the aggressive mids.

5. A/B targets
   - With the lead muted, the sub should feel steady and heavy, not like a separate wobble performance.
   - With drums in, the kick transient should still be obvious.
   - With the full drop in, the sub should add weight and small-speaker harmonics without masking the octave-up Drop 1 lead or the huge Drop 2 synth.
   - If the low end feels crowded, reduce noise/filter drive before lowering the fundamental.

## 11. Drop 1: Lead Stack

1. Add a high sizzle layer.
   - Use a sample or one-shot with strong high-frequency bite.
   - This completes the lead, especially in trap/electronic contexts.

2. Add the main wonky lead.
   - Source can be a rough preset or sample.
   - It may sound bad alone.
   - Judge it in the full stack before discarding it.

3. Process the main lead.
   - Add a waveshaper such as Melda MWaveShaper or equivalent.
   - Add a clipper.
   - High-pass or cut lows because the sub owns that range.
   - Add Crystalline or a metallic reverb.
   - Add Snap Heap or a modular multi-effect rack.
   - Try phase distortion, repeated distortion blocks, or unusual modulation.
   - Add another EQ cut after effects if the processing reintroduces low-frequency junk.

4. Accept some phase or grit if it works in context.
   - The transcript explicitly keeps imperfect artifacts when the full layer sounds good.
   - Do not spend hours fixing issues that are not hurting the record.

5. Add glitch-tail filler.
   - Take a reverb tail or processed lead tail.
   - Distort or glitch it.
   - Chop it into rhythmic fills at phrase endings.
   - Keep it as a small movement that makes transitions less empty.

6. Add chaotic background filler.
   - Use strange, unidentifiable textures.
   - Keep them low and continuous through parts of the drop.
   - They should make the drop feel unique without stealing focus.

### Drop 1 Lead Stack Appendix

Use this as a generic substitute chain for the local `Drop Lead` lane. The local project places this lane on bars 33-48, labels it as the first-drop lead up an octave, and stores waveshaper, clipper, low-cut, Snap Heap phase-distortion, and Crystalline-style reverb slots.

1. Source and stack
   - Main source: a rough lead preset, sample, or resampled synth that has attitude even if it sounds awkward solo.
   - Pitch/register: keep Drop 1 higher than the second drop. The local approximation treats it as the octave-up lead.
   - Sizzle support: add a high-passed noise, one-shot, or bright layer only if the lead lacks top-end bite.
   - Gain staging: leave headroom before distortion. Aim for a strong signal that is not already clipping.

2. Ordered processing chain
   - Wave shaper: start with a soft curve, then increase drive until the midrange becomes animated. Suggested range: 20-60 percent wet/drive.
   - Clipper: shave only the sharpest peaks after the wave shaper. Suggested range: 1-4 dB of clipping or 10-35 percent amount.
   - Low cut: remove lows because the driven sub owns that space. Start around 120-180 Hz; raise toward 250 Hz if the lead is still clouding the kick/sub.
   - Metallic reverb: add Crystalline-style bright room/metallic tail in parallel or low mix. Suggested wet range: 6-18 percent, high-passed on the wet return.
   - Multi-effect rack: use Snap Heap-style phase distortion, chorus, frequency shifting, or repeated distortion blocks. Suggested wet range: 5-25 percent.
   - Post-effect EQ: cut lows again if reverb or phase distortion reintroduces mud. Dip harsh resonances only after hearing the full drop.

3. Automation and phrase use
   - Bring the lead tease in during bars 29-32 at lower level or with a darker filter.
   - Open the full lead at bar 33 with the Drop 1 drums and vocal rhythm.
   - Let vocal breaks, tag moments, or siren answers create gaps instead of filling every beat with lead.
   - If the chain has a rack macro, automate small changes at phrase boundaries rather than changing the whole patch.

4. A/B targets
   - With drums and sub muted, the lead should still have a recognizable hook and aggressive contour.
   - With the sub enabled, the lead should lose low-end authority but keep mid/high presence.
   - In mono, the phase distortion should not erase the hook. If it does, reduce the rack wet amount before changing the source.
   - Bypassing the wave shaper and clipper should make the lead feel smaller. If bypassing them improves clarity, the distortion is too heavy.

## 12. Second Part / Second Build

1. Bring back the intro material as a callback.
   - Reuse the bass-synth line.
   - Reuse the analog layer.
   - Reuse the same vocal and build devices.

2. Add a new random effect to refresh the repeated section.
   - The transcript mentions Baby Audio Humanoid.
   - Use a vocoder-like or formant-like process on a texture.
   - It can sound odd or even slightly wrong by itself as long as it fills space in context.

3. Reuse the Rave Generator-style layer.
4. Reuse the same claps and vocal chops for continuity.
5. Prepare the second drop to feel related but bigger or heavier than the first.

## 13. Drop 2: Main Synth Change

1. Introduce a new huge synth sound.
   - The transcript references Omnisphere Seismic Shock and a preset like "Big Nuke Button."
   - Use a large, aggressive preset if it fits.
   - Adjust sustain or envelope slightly if needed.

2. Add waveshaping or distortion after the preset.
3. Keep continuity with the first drop sub or bass behavior.
4. Make this section an old-school trap callback.
   - Add sirens, lasers, or rave alarm-like effects.
   - Reference the energy of older festival trap without copying any specific song.

### Drop 2 Huge Synth Substitute Chain

Use this when you do not have the exact Seismic Shock / Big Nuke-style preset. The local `Second Drop Synths` lane covers bars 65-72 and stores a preset layer, PolySaturator-style harmonics, a Serum FX-style preset chain, soothe-style resonance cleanup, and a low cut around 250 Hz.

1. Source layer
   - Choose a large aggressive synth, resampled bass stab, rave stab, or distorted wavetable preset.
   - Favor a source with immediate midrange identity over a clean patch that needs too much design.
   - Register: make Drop 2 lower/heavier than Drop 1, but keep enough upper harmonics for translation.
   - If the source is stereo, check that the hook survives in mono before adding width.

2. Shape and saturate
   - Start with envelope cleanup. Shorten sustain/release if the preset smears into the next hit.
   - Add harmonic saturation after the source. PolySaturator-style drive can be replaced by tube, diode, foldback, or soft-clip saturation.
   - Suggested saturation range: 15-45 percent, or until the layer feels bigger without flattening every transient.
   - Add a clipper only if peaks jump out after saturation.

3. Movement and FX rack
   - Use a Serum FX-style rack, multi-effect preset, or stock chain with filter, distortion, comb/chorus, and short ambience.
   - Keep the rack focused on movement and aggression, not wash. Suggested wet range: 10-35 percent.
   - Automate one macro across the 8-bar Drop 2 phrase if it helps the sound avoid repeating exactly.
   - Avoid wide low end. Put widening, chorus, or reverb after a low split or high-pass.

4. Cleanup
   - Low cut quickly if the layer fights the sub. Start around 180-250 Hz, matching the local project's `Low Cut at 250` note.
   - Use soothe-style resonance ducking only after saturation/FX reveal painful peaks. Suggested depth: light to medium, enough to tame whistles without dulling the hook.
   - If the sound has bass that is useful, split it from the sub lane rather than leaving both full-range.
   - Check that sirens/lasers can still cut above this layer.

5. A/B targets
   - Compared with Drop 1, Drop 2 should feel lower, heavier, and more aggressive, not merely louder.
   - Muting the `Second Drop Synths` lane should make bars 65-72 lose their new identity immediately.
   - Muting the sub should still leave a gritty midrange hook; unmuting the sub should add weight without making the synth muddy.
   - If the layer masks the vocal tag or siren answer, reduce saturation mids or narrow the FX rack before lowering the entire track.

## 14. Drop 2: Sirens, Lasers, and Aggressive Layers

1. Create or choose a laser/siren sound.
   - Use pitch movement, octave sweeps, or fast pitch automation.
   - A pitch device can rise and fall quickly for the laser effect.

2. Process the laser/siren.
   - Use distortion or a heavy effect preset.
   - Add crush or saturation if it needs aggression.
   - Watch the low end. The transcript notes one sound had more bass than it probably needed.

3. Add a UK bass or Shadow-style sample layer.
   - Use a sample with strong movement and grit.
   - Process with Polyverse PolySaturator or a harmonic saturation tool.
   - Add Serum FX or another synth FX rack and scroll effect presets until something works.
   - Convert to mono if the layer needs to sit in the center.

4. Add old-school trap synth stabs.
   - Search trap packs or older-sounding serum presets.
   - The source can be a preset. The key is choosing something with the right attitude.

5. Process the old-school stab.
   - Add Valhalla VintageVerb or another bright room/plate.
   - Use a modern bright color setting rather than a dark vintage one if the sound needs to cut.
   - Add OTT/multiband compression.
   - Add soothe-style resonance reduction.
   - Cut lows quickly with a simple EQ if you do not need detailed EQ work.
   - If distortion artifacts sound cool in context, you can keep them.

6. Reuse the vocal tag and drop vocal breaks.
   - Let them mark the phrase changes just like in Drop 1.

### Drop 2 Siren / Laser Appendix

Use this for the old-trap siren and laser role. The local `Sirens Lasers` lane appears as a first-drop answer at bars 45-48 and as a larger Drop 2 layer at bars 65-72, with quick pitch rise/fall, mono utility, and bright reverb slots.

1. Source or synth patch
   - Start with a sine, triangle, narrow saw, or simple FM tone.
   - Keep the raw tone simple. The character comes from fast pitch motion, saturation, and placement.
   - Use short notes or one-shot sweeps rather than long melodic phrases.

2. Pitch movement
   - Draw a fast upward or downward pitch curve over roughly 1 beat.
   - For a laser feel, use a curved sweep rather than a straight ramp: slow at one end, faster at the other.
   - Range can be broad, roughly low-mid to upper-mid, as long as the sweep stays above the sub lane.
   - Alternate rise and fall gestures in Drop 2 so the layer feels like a response, not a constant alarm.

3. Processing
   - Add distortion, clipper, or overdrive after pitch movement. Push until the sweep cuts through the second-drop synth.
   - Use mono utility or narrow the low/mid part so the sweep does not destabilize the drop.
   - Add bright room/plate reverb at low-to-medium mix. Keep the tail short enough that the next hit remains clear.
   - Low-cut aggressively if the source has accidental bass.

4. Placement
   - Use bars 45-48 as a short siren answer after Drop 1.
   - Use bars 65-72 as the fuller second-drop laser layer.
   - Place sweeps in gaps around vocal tags and synth hits, not on top of every important transient.
   - Automate level down quickly after each gesture so the layer does not become the lead.

5. A/B targets
   - Muting the sirens should make the drop less old-school and less animated, but the main hook should still work.
   - In mono, the sweep should still be audible and should not cancel.
   - If the second-drop synth loses focus, reduce siren level, low mids, or reverb before removing the layer.

## 15. Outro Callback

1. End by referencing the beginning.
2. Bring back the original bass-synth or intro motif.
3. Remove the heavy drop layers.
4. Let the track close with a recognizable callback rather than a totally new idea.

## 16. Transition Processing

1. Use transition-focused plugins where they save time.
   - The transcript mentions Baby Audio Transit / Transit 2.
   - Similar tools include multi-effect macro plugins or custom racks.

2. Build a single macro that moves several effects at once.
   - High-pass
   - Low-pass
   - Band-pass
   - Notch
   - Chorus
   - Delay
   - Reverb
   - Grit or distortion

3. Automate the macro through builds and transitions.
4. Use gritty delay or filter presets as starting points.
5. Customize the preset rather than leaving it untouched if the transition needs a more specific shape.

### Transition Automation Target Table

These are recommended targets for recreating the local arrangement. They are not exact original automation curves.

| Local bars | Moment | Main lanes | Suggested automation targets |
| --- | --- | --- | --- |
| 1-8 | Pre-intro reverse and impact setup | Transit Macro FX, Dynamic Risers, Sample Bass Synth | Fade in riser volume, open a high-pass/low-pass macro, increase reverb or delay send into the first hit, and keep the reversed impact darker than the intro groove. |
| 23-24 | Build handoff | Dynamic Risers over bridge lanes | Start a riser volume/filter lift and slightly increase vocal or room send so the formal build does not feel abrupt. |
| 25-28 | Build loop begins | Build Loop, Transit Macro FX, Vocal Chops, Random Filler | Raise Transit macro amount, increase delay feedback on vocal chops, and let filler volume rise only enough to fill gaps. |
| 29-32 | Final Drop 1 tease | Lead Tease, Build Loop, Risers, Transit Macro FX | Open the lead-tease filter or level, push riser pitch/brightness, narrow the low end, and prepare a hard macro reset on bar 33. |
| 33 | Drop 1 impact | Drop Drums, Drop Vocals, Drop Lead, Driven Sub, Crash Layers | Snap build macros back down, cut excess delay feedback, restore sub weight, and keep only intentional vocal throws. |
| 36-47 | Drop 1 fill lane | Glitch Tail, Drop Lead, Drop Vocals | Automate glitch-tail volume and delay throws at phrase endings instead of running them at full level continuously. |
| 45-48 | Siren answer out of Drop 1 | Sirens Lasers, Glitch Tail, Stereo Breaths | Automate quick pitch rise/fall, reduce low end on sirens, and use a short delay/reverb throw to bridge into the second-part reset. |
| 55-64 | Second build | Dynamic Risers, Transit Macro FX, Vocal Chops, Rave Generator, Lead Tease | Repeat the build lift but make it busier: more vocal delay feedback, slightly brighter risers, and a clearer lead-tease open before bar 65. |
| 65 | Drop 2 impact | Second Drop Synths, Sirens Lasers, Drop Drums, Driven Sub | Reset build effects, let the huge synth enter lower/heavier, preserve mono sub, and keep siren movement above the main synth. |
| 69-72 | Outro callback / ending transition | Random Filler, Transit Macro FX, Drop 2 lanes | Fade or filter down the heavy layers, increase transition delay/reverb, and let the ending macro close the track quickly. |

## 17. Plugin and Tool References From the Video

Use these as examples, not requirements:

1. Omnisphere Sonic Extensions
   - Seismic Shock
   - Unclean Machine
   - Undercurrent

2. Slate Digital Fresh Air
   - Brightens vocals and chops.
   - Useful on dull mid/high content.

3. Dank Sauce or OTT-style multiband compression
   - Adds density and aggression.
   - Useful on synths and vocals.

4. Baby Audio Crystalline
   - Metallic/bright reverb.
   - Strong for electronic leads and pre-build sounds.

5. Baby Audio Humanoid
   - Vocoder/formant-like processing.
   - Good for weird background color.

6. Baby Audio Transit / Transit 2
   - Macro transition effects.
   - Useful for builds, sweeps, and section changes.

7. Rave Generator
   - Old-school rave stabs and classic sample-style sounds.

8. Valhalla Room
   - Room reverb for snare/clap layers.

9. Valhalla VintageVerb
   - Brighter standard reverb for synth stabs and melodic effects.

10. Serum and Serum FX
   - Bass patches, white noise/filter drive, and preset FX chains.

11. Operator or any simple synth
   - White noise crash layer.

12. Melda MWaveShaper / Melda bundle
   - Waveshaping and unusual utility effects.

13. Kilohearts Snap Heap
   - Modular multi-effect processing and distortion/modulation chains.

14. Polyverse PolySaturator
   - Harmonic enhancement and frequency-focused saturation.

15. soothe
   - Resonance control and harshness reduction.

16. Pultec-style EQ
   - Low-end kick enhancement, especially around 100 Hz.

### Stock / Generic Replacement Table

Use these replacements by role. The goal is to reproduce the production function, not the brand name.

| Named tool or source | Role in the walkthrough | Stock or generic substitute |
| --- | --- | --- |
| Omnisphere Sonic Extensions / Seismic Shock / Big Nuke-style presets | Aggressive preset source, room layer, huge Drop 2 synth | Any wavetable, sampler, granular, or rompler preset with strong midrange identity; layer a saw/square core with noise, distortion, and short ambience. |
| Slate Digital Fresh Air | Vocal-chop brightness and presence | High-shelf EQ into a gentle exciter, air band, or parallel saturation focused above 4-8 kHz. |
| Dank Sauce / OTT | Dense multiband compression on synths and vocals | Stock multiband compressor, upward compressor, or OTT-style preset at low-to-medium mix. |
| Baby Audio Crystalline | Bright metallic reverb on pre-build and lead layers | Stock plate/room reverb with short-to-medium decay, high-passed wet return, bright damping, and optional shimmer/chorus. |
| Baby Audio Humanoid | Weird humanoid/vocoder background texture | Vocoder, formant shifter, ring mod, spectral/formant filter, or resampled vocal-texture rack kept low in the mix. |
| Baby Audio Transit / Transit 2 / Endless Smile-style tools | One-knob transition macro | Custom macro rack controlling high-pass, low-pass, delay feedback, reverb send, chorus, and saturation. |
| Rave Generator | Old-school rave/trap stab color | Stock sampler with rave stab one-shots, chord stabs, hoovers, organ hits, or a simple detuned saw/square stab. |
| Valhalla Room | Snare/clap room and general space | Stock room reverb with early reflections and short decay. |
| Valhalla VintageVerb | Bright synth-stab reverb | Stock plate/hall reverb with bright color, high-passed wet return, and pre-delay. |
| Serum / Serum FX | Wamp synths, white-noise filter drive, preset FX chains | Any wavetable/FM/subtractive synth plus a stock multi-FX chain: filter, distortion, chorus/comb, compression, EQ. |
| Operator | White-noise crash/noise layer | Any stock synth or sampler noise oscillator into envelope, filter, and reverb. |
| Melda MWaveShaper / Melda bundle | Waveshaping, clipping, utility effects | Stock waveshaper, saturator, overdrive, clipper, frequency shifter, or utility device. |
| Kilohearts Snap Heap | Modular distortion/modulation rack | Stock audio-effect rack with phase distortion, chorus, filter, frequency shifter, delay, and parallel wet/dry control. |
| Polyverse PolySaturator | Frequency-focused harmonic enhancement | Tube/tape/diode saturator, soft clipper, multiband saturator, or parallel distortion bus. |
| soothe | Harsh-resonance control | Dynamic EQ, multiband compressor, de-esser, or manual narrow EQ cuts automated only where resonances jump out. |
| Pultec-style EQ | Kick low boost around 100 Hz | Stock EQ bell/shelf boost near the kick fundamental, optionally paired with a small low-mid attenuation. |
| EQ250 / simple low cut | Fast cleanup around 180-250 Hz | Any stock EQ high-pass or low shelf cut. |

## 18. Practical Production Principles From The Video

1. Use fewer layers when one excellent sound does the job.
2. Layer when the missing role is clear: click, body, sizzle, stereo width, mono weight, room, or movement.
3. Do not EQ by default. EQ when a layer has a job conflict or unwanted frequency content.
4. Dry and wet contrast matters as much as melody.
5. Use random filler sounds to make sparse sections feel alive.
6. Tease important drop sounds before they fully arrive.
7. Reuse claps, tags, and vocal motifs to make the track coherent.
8. Let the first drop and second drop differ by octave, density, or lead source.
9. Keep a few recognizable sonic signatures across the whole track.
10. When a preset or sample already works, use it. The production value comes from arrangement, context, and processing as much as original sound design.

### Rough Mix Checklist

These are starting relationships from the local approximation, not exact fader values from the original source project.

1. Low end
   - Kick/drop drums and driven sub should be the loudest low-end anchors.
   - Keep the sub mono and centered.
   - Low-cut Drop 1 lead, second-drop synth layers, sirens, stabs, reverbs, and filler before they fight the sub.
   - Start low cuts around 120-180 Hz for leads and 180-250 Hz for big second-drop synth layers, then adjust by ear.
   - If the kick loses click, reduce bass/synth low mids before boosting the kick harder.

2. Level relationships
   - Drop Drums and Driven Sub are the main anchors.
   - Drop Lead and Second Drop Synths should feel slightly below the drums/sub but still define the hook.
   - Drop Vocals and Vocal Chops should read as phrase markers, not full lead vocals.
   - Room Layer, Random Filler, Glitch Tail, Breaths, and transition FX should sit behind the main pattern unless they are announcing a change.
   - In the local project, reference gains cluster roughly like this: Drop Drums 0.86, Driven Sub and Second Drop Synths 0.82, Drop Lead 0.78, Drop Vocals/Transit FX 0.74, filler and room layers about 0.50-0.62.

3. Stereo width
   - Keep kick, sub, main drop impact, and important vocal/tag hits centered.
   - Use Stereo Breaths, Crash Layers, Glitch Tail, room layers, and selected delays for side energy.
   - Check mono after adding Snap Heap-style phase distortion, wide crashes, and siren layers.
   - If the hook disappears in mono, reduce width or phase effects before changing the notes.

4. Reverb and space contrast
   - Keep Driven Sub mostly dry.
   - Let Dark Room Layer, Rave Generator, Drop Lead reverb, and Glitch Tail carry the obvious room/space.
   - High-pass reverb returns so they do not thicken the low end.
   - Use delay throws on vocals and transition moments rather than leaving every vocal chop washed out.
   - The track should alternate dry impact and wet chaos, not stay equally wet throughout.

5. Harshness control
   - Check the 2-6 kHz area after wave shaping, clipping, Crystalline-style reverb, sirens, and second-drop saturation.
   - Check 8-12 kHz after Fresh Air-style brightening, hats, crash layers, and white-noise risers.
   - Use dynamic EQ, de-essing, or soothe-style reduction only where peaks jump out.
   - Reduce distortion/rack wet amount before applying deep EQ cuts if the whole layer feels brittle.
   - Keep some grit if it helps the record. The goal is controlled aggression, not clean sterility.

## 19. Condensed Build Checklist

1. Set BPM and key.
2. Find one long bass-synth sample.
3. Write the main bass-synth line.
4. Layer a simple analog bass.
5. Add sparse claps.
6. Add room/atmosphere layer.
7. Add breaths or stereo texture.
8. Add a short vocal sample.
9. Add reverse intro effects and risers.
10. Chop the vocal for the pre-build.
11. Brighten vocal chops with Fresh Air-style processing.
12. Add a rhythmic pre-build synth preset.
13. Compress and reverberate the pre-build synth.
14. Add left/right delays into the build.
15. Add rave stabs or old-school trap color.
16. Tease the drop lead before the drop.
17. Use a build sample with chants, snares, and white noise if it works.
18. Add low random filler before the drop.
19. Build drop vocals and tag moments.
20. Program a clicky kick with subtle Pultec-style low boost.
21. Layer snare/clap sounds.
22. Add a small high hat tick with aggressive high-pass.
23. Build crash layers from open hat, snare/noise, and white noise.
24. Make a simple driven sub patch.
25. Add white noise into the bass filter and drive it.
26. Build the lead stack with sizzle, main wonky lead, waveshaping, clipper, reverb, and multi-effects.
27. Chop a glitch tail for phrase endings.
28. Add chaotic background filler.
29. Bring back intro material for the second part.
30. Add a new weird effect layer to refresh the repeat.
31. Make the second drop heavier with a new huge synth.
32. Add sirens, lasers, and old-school trap stabs.
33. Process second-drop layers with saturation, Serum FX, reverb, OTT, soothe, and low cuts.
34. End with an intro callback.
35. Use a transition macro plugin or rack to automate movement between sections.

## 20. Ableton-Style Implementation Checklist

Use this if you are building the approximation in Ableton Live or any DAW with a similar Arrangement View workflow.

1. Set the Live set to 150 BPM and create locators for bars 1, 9, 13, 17, 23, 25, 29, 33, 36, 45, 49, 55, 57, 61, 65, 69, and 71.
2. Create grouped tracks in this order: vocals/tags, transition FX, lead/preset layers, bass/sub, drums, and background filler.
3. Add the main sample-bass clip across bars 1-24, then copy a shorter callback to bars 49-56.
4. Add analog bass support under the same regions, but keep its level lower than the sample-bass identity.
5. Add room layer and claps from bar 9 so the intro opens up after the pre-intro.
6. Add vocal chops from bars 13-32, then copy/rework them for bars 57-72.
7. Add build drums, risers, Transit-style macro FX, random filler, and lead tease across bars 25-32.
8. Build Drop 1 at bars 33-48 with drop drums, drop vocals, Drop Lead, Driven Sub, Same Clap Stack, and Crash Layers.
9. Place glitch-tail fills at phrase endings inside bars 36-47 rather than across the entire drop.
10. Add the first siren/laser answer at bars 45-48 to push out of Drop 1.
11. Reintroduce intro material at bars 49-56, then rebuild with vocal chops, build loop, risers, transition macro, rave stabs, and lead tease at bars 57-64.
12. Build Drop 2 at bars 65-72 with the lower/heavier second-drop synth, sub continuity, drop drums, vocal tags, crash stack, and sirens/lasers.
13. Use audio-effect racks for the lead chain, second-drop synth chain, and transition macro so wet/dry and drive can be automated from one or two visible controls.
14. Draw automation lanes only where the arrangement changes: riser/filter lifts into bars 33 and 65, delay throws around vocal breaks, pitch movement on sirens, and ending macro movement at bars 71-72.
15. Print or freeze any unstable preset/sample layers once the arrangement works, then keep notes on source role and substitute settings.

## 21. FL Studio / Logic Translation Notes

Use the same arrangement map and sound roles. Only the DAW terms change.

| Ableton-style term in this guide | FL Studio equivalent | Logic Pro equivalent |
| --- | --- | --- |
| Arrangement View locators | Playlist markers | Arrangement markers or marker track |
| Audio clip on a lane | Audio clip in the Playlist | Audio region on a track |
| Track group | Playlist track grouping plus mixer routing | Track stack or summing stack |
| Audio effect rack / macro | Patcher, Control Surface, or linked controls | Smart Controls, Track Stack controls, or bus channel strip macros |
| Freeze/flatten or print | Consolidate, render as audio clip, or record to Edison/audio track | Bounce in place or freeze track |
| Return/send reverb or delay | Mixer send track | Aux send/bus |
| Utility mono control | Stereo Shaper, Fruity Stereo Enhancer, or mixer mono switch | Direction Mixer, Gain mono, or channel strip mono |
| Automation lane | Automation clip | Track automation or region automation |
| Drum rack / sampler lanes | Channel Rack, FPC, or sampler channels | Drum Machine Designer, Quick Sampler, or Sampler |
| Warp/stretch sample | Stretch mode, time stretch, or audio clip stretch | Flex Time or region time/pitch controls |

FL Studio notes:

1. Keep Playlist tracks named by role, even if the sound source lives in the Channel Rack.
2. Use one mixer insert per major role: sample bass, sub, drop drums, drop vocals, Drop Lead, Second Drop Synths, transition FX, and filler.
3. Use automation clips for build macro amount, riser volume, vocal delay throws, and siren pitch movement.
4. Consolidate unstable audio/preset sections after the arrangement works so the Playlist remains readable.

Logic notes:

1. Use arrangement markers for the local bar map and track stacks for role groups.
2. Use Summing Stacks for lead, bass/sub, drums, vocals, and transition FX.
3. Use Track Automation for macro/filter/delay moves and Region Automation for one-off vocal or siren gestures.
4. Bounce in Place for heavy preset layers and keep the original instrument track muted but labeled if you need recall.

## 22. Deliverable Notes

The goal is not to recreate the exact commercial record. The goal is to reproduce the production method:

1. A simple central riff.
2. Strong sample and preset choices.
3. Aggressive but practical processing.
4. Sparse arrangement with detailed ear candy.
5. Dry/wet contrast.
6. Trap drum attitude.
7. Heavy sub and driven bass.
8. Old-school rave/trap callbacks.
9. Vocal tags and chops as arrangement markers.
10. A second drop that changes the lead identity while staying connected to the first.
