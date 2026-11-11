<p align="center">
  <img src="docs/hero.png" alt="Infocard: hover any setting to see what it does" width="100%">
</p>

<h1 align="center">Infocard</h1>

<p align="center">
  <b>Stop guessing what a setting does. Hover it and see.</b><br>
  A picture card for every setting in Blender. Offline, instant, free.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Blender-4.2%2B-orange" alt="Blender 4.2+">
  <img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="GPL-3.0">
  <img src="https://img.shields.io/badge/settings%20with%20pictures-4%2C700%2B-success" alt="4,700+ settings">
  <img src="https://img.shields.io/badge/works-offline-lightgrey" alt="Offline">
</p>

---

## The problem

Blender has thousands of settings. Most of them come with a one-line tooltip like *"Amount of
subsurface scattering"*, which tells you nothing until you already know the answer.
So you stop, open a browser, search, watch a 12-minute video, and come back.

## The fix

Rest your mouse on any setting for a second. **Infocard** shows two pictures side by side
(*low vs high*, *off vs on*, *without vs with*) and one or two plain sentences. You *see* what
the setting does, right where you are.

<p align="center"><img src="docs/screenshot_1.png" width="90%"></p>

## What's covered

| Area | Pictures |
|---|---|
| **Shading:** Principled BSDF, every shader and texture node and their sockets | ✔ |
| **Geometry Nodes:** 480+ nodes, 650+ node inputs | ✔ |
| **Compositor:** every node, 360+ inputs | ✔ |
| **Modifiers:** every type, 750+ settings | ✔ |
| **Constraints:** every type, 340+ settings | ✔ |
| **Physics:** cloth, soft body, fluid, rigid body, fields, particles, dynamic paint | ✔ animated |
| **Render and World:** passes, light paths, film, color management, EEVEE and Cycles | ✔ |
| **Viewport:** overlays, shading, gizmos, snapping, pivot, proportional editing | ✔ |
| **Paint, Sculpt and Grease Pencil:** brush and stroke settings | ✔ |
| **Animation:** interpolation, easing, NLA, F-curve modifiers | ✔ animated |

**4,700+ settings have their own picture**, many as small looping animations.
Every other setting gets a short, human explanation, written for someone learning Blender.

<p align="center"><img src="docs/screenshot_2.png" width="90%"></p>

## Designed to stay out of your way

- **Waits for you:** the card appears only after 1.5 s of hovering. Move on and it's gone. Start editing and it's gone.
- **Instant swaps:** once a card is open, moving to the next setting swaps it immediately.
- **Your layout:** *Corner*, *Position* (exact pixels) or *Manual* (drag it anywhere). Resize it, and pick the picture ratio (1:1, 4:3, 16:9…).
- **Light:** pictures load straight to the GPU, with no data-blocks added to your file and nothing written to disk.
- **Private:** no internet, no account, no tracking.

## Quick start

1. Install from **Preferences › Get Extensions** (search *Infocard*), or download the zip from [Releases](../../releases) and use **Install from Disk**.
2. In the 3D View press **N** and open the **Infocard** tab.
3. Hover anything.

## Store version vs full version

| | Extensions platform | GitHub release (full) |
|---|:-:|:-:|
| Cards on every setting, node and socket | ✔ | ✔ |
| Cards inside *Add Modifier*, *Add Node*, *Add Constraint* menus and the toolbar | — | ✔ |

The full version wraps a few of Blender's built-in menu drawing functions so it can show cards inside those menus.
The store version never touches Blender's own code.

## Pairs well with

**[Infocard Recipes](https://github.com/yotamkiper1/infocard-recipes)** has 3,000 one-click node recipes and smart
*Alt-drag* effects for shaders, Geometry Nodes and the compositor. With both installed, recipe previews appear in your Infocard.

## FAQ

**Does it slow Blender down?**
No. It only reacts when the mouse moves, and it never adds data to your file.

**Which Blender version?**
4.2 or newer. The pictures were made in Blender 5.x.

**Can I turn it off quickly?**
Yes. There's one toggle at the top of the Infocard tab.

**Found a setting without a picture?**
[Open an issue](../../issues) with a screenshot and it'll be added to the next update.

## License

Code: GPL-3.0-or-later · Pictures: CC0. Every picture was rendered in Blender for this project.
