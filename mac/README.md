# Neon Studio Native Mac App

This is the native AppKit/AVFoundation version of Neon Studio. It builds a real
`.app` bundle without Electron, Tauri, or a browser runtime, and uses the same
portable `.neon.json` project files as the web app.

Build:

```sh
./mac/NeonStudio/build.sh
```

Launch:

```sh
open "mac/build/Neon Studio.app"
```

Current native surface:

- Seeds `public`, `data`, `exports`, and `tools` into
  `~/Library/Application Support/Neon Studio`.
- Loads, saves, deletes, imports, backs up, and reveals `.neon.json` projects.
- Draws playlist, piano roll, mixer, plugins, sample editor, recipe, automation,
  scope, browser, channel rack, mixer, and project panels.
- Plays/stops WAV stems from the project, respecting mute/solo/gain/pan.
- Autosaves project edits and supports undo/redo/delete shortcuts.
- Provides File, Edit, Add, View, Options, and Help menus.
- Imports audio files, records local takes, exports rendered mixdowns, and runs
  Vocal Lab through the bundled Python processor.
- Supports project BPM, song/pattern mode, snap, loop range, pattern, swing, and
  timeline zoom controls.
