# Neon Studio Native Mac Preview

This is the first native AppKit/AVFoundation proof-of-direction for Neon Studio.
It builds a real `.app` bundle without Electron, Tauri, or a browser runtime.

Build:

```sh
./mac/NeonStudio/build.sh
```

Launch:

```sh
open "mac/build/Neon Studio.app"
```

Current native slice:

- Loads `.neon.json` projects from `data/projects` and `public/projects`.
- Draws the playlist tracks and clips.
- Plays/stops project WAV stems from `exports`.
- Opens as a normal macOS app window.

The web app remains the production surface for editing and Vocal Lab while this
native app is expanded.
