# Neon Studio Native Mac App

A native AppKit + AVFoundation macOS app. No Electron, no Tauri, no browser
runtime. Projects are portable `.neon.json` files.

## Build and run

```sh
npm run build:mac        # release build + .app bundle
npm run open:mac         # launch it
npm run test:mac         # unit tests only
./mac/NeonStudio/build.sh --debug   # fast incremental build while developing
```

The app requires only Apple's Command Line Tools — there is no Xcode project
and none is needed.

## Architecture

The app is a **SwiftPM package** (`mac/NeonStudio/Package.swift`) with three
targets, and a **document-based** AppKit application.

```
mac/NeonStudio/
  Package.swift
  build.sh                     compiles the package, assembles "Neon Studio.app"
  Sources/
    NeonStudioKit/             pure logic — no view code, fully unit-tested
      Model/Project.swift          the .neon.json schema
      Model/Normalization.swift    defaults, migrations, snap maths
      Model/ProjectStore.swift     the project library on disk
      Audio/Transport.swift        AVAudioEngine playback
      Audio/NotePreviewRenderer.swift  renders notes and steps to audio
      Tools/ToolRunner.swift       async subprocess runner
      Tools/ToolPaths.swift        Python discovery
    NeonStudioApp/             the AppKit app
      App/                         delegate, environment, status, glossary
      Design/                      theme and control vocabulary
      Document/                    NeonDocument + its window controller
      Views/                       panes and editing canvases
      Onboarding/                  welcome window and guided tour
      Reports/                     sound-check, activity and shortcut windows
      Settings/                    preferences
      Menus/                       the main menu bar
  Tests/NeonStudioTests/       self-contained test runner (XCTest needs Xcode)
```

### Why document-based

Neon Studio edits `.neon.json` files, so `NSDocument` is the right shape for it.
Adopting it removed a large amount of hand-rolled machinery — a bespoke project
browser, open/save/import/delete, a debounced autosave timer, and a two-array
undo stack — and in exchange the app now gets, correctly and for free:

- Open Recent, and double-clicking a `.neon.json` in the Finder
- Save, Save As, Duplicate, Rename, Move To, Revert to Saved
- autosave-in-place and Versions
- the modified dot and a working proxy icon in the title bar
- "You have unsaved changes" on close and on quit
- several projects open at once, each in its own window
- window, split-position and toolbar restoration between launches

Undo is `NSUndoManager`, so the Edit menu reads "Undo Set Tempo" rather than a
bare "Undo", and history is per-document instead of a single global stack that
was discarded whenever another project was opened.

`.neon.json` is registered in `Info.plist` as the exported UTI
`studio.neon.project`, with `NeonDocument` as its `NSDocumentClass`.

### Audio

`Transport` drives one `AVAudioEngine`. Every source is scheduled against a
single shared host time, so stems start together instead of drifting apart.
Each track owns an `AVAudioMixerNode`, so gain, pan, mute and solo take effect
during playback. The loop range is honoured by pre-queuing loop repeats, the
playhead is real, and playback stops on its own when the song ends.

Tracks with no audio file are not silent: `NotePreviewRenderer` synthesises
their piano-roll notes and step patterns into a buffer that is scheduled like
any other stem. A brand-new project makes sound.

### Helper tools

The Python tools in `tools/` are run through `ToolRunner`, off the main thread,
with both pipes drained while the process runs. Long tasks show progress, can be
cancelled, and stream their output into the Activity log. The interpreter is
discovered rather than hardcoded, and is configurable in Settings.

## What the app does

- Seeds `factory`, `data`, `exports`, `tools` and `skills` into
  `~/Library/Application Support/Neon Studio`
- Opens, edits and saves `.neon.json` projects as real documents
- Arrange view: drag clips to move, drag edges to resize, draw, erase, loop
  brace, playhead, section markers
- Notes view: per-track piano roll with real note editing and velocity
- Mix view: draggable faders, pan, mute/solo/arm, sends, and true per-track
  meters tapped at each track's own mixer node
- Effects, Sample (with real waveforms and trim handles), and Recipe views
- Automation lanes with draggable breakpoints
- Records microphone takes with a count-in and punch-in/out: the clicks, the
  backing track and the recorder are pinned to one host time, so a take lands on
  the bar you aimed at rather than wherever your reaction time put it. With Loop
  on, the loop range becomes the punch range and recording stops itself.
- Imports audio and exports a mixdown
- Runs sound check, the DAW agent, transcript materialization and Vocal Lab
- First-run welcome window, a guided tour, empty states everywhere, and a
  plain-language mode that explains music jargon in place

## Regenerating the app icon

```sh
cd mac/NeonStudio/Resources && swift make_icon.swift
```

The result (`AppIcon.icns`) is committed, so ordinary builds need nothing extra.
