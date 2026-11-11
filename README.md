<p align="center">
  <img src="docs/hero.png" alt="Infocard" width="100%">
</p>

<h1 align="center">Infocard</h1>

<p align="center">
  <strong>Visual explanations for every setting in Blender.</strong><br>
  Hover a setting and see what it does, with before/after pictures and a plain-language description.
</p>

<p align="center">
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/yotamkiper1/infocard?label=release" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/Blender-4.2%2B-orange" alt="Blender 4.2+">
  <img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="License GPL-3.0">
</p>

---

## Overview

Blender's tooltips describe settings in technical terms. Infocard replaces guesswork with a picture.
Rest the cursor on any setting and a compact card appears showing that setting at two values
(*low vs high*, *off vs on*, *without vs with*), together with a short explanation written for people learning Blender.

It works entirely offline, adds nothing to your files, and gets out of the way the moment you start working.

<p align="center"><img src="docs/screenshot_1.png" width="90%" alt="Infocard showing a modifier setting"></p>

## Key features

- **4,700+ illustrated settings.** Every image was rendered in Blender specifically for the setting it explains.
- **Animated where motion matters.** Physics and animation settings play as short looping clips.
- **Full coverage.** Settings without a picture still get a clear, human-written explanation.
- **Non-intrusive.**
  - The card appears after a 1.5-second hover.
  - It switches instantly between settings.
  - It hides when you edit a value or move away.
- **Flexible layout.** Anchor the card to a corner, set an exact position, or place it by hand. Adjust its size and picture aspect ratio.
- **Lightweight.**
  - Images are uploaded straight to the GPU.
  - No data-blocks are created and nothing is written to disk.

## Coverage

| Area | Included |
|---|---|
| Shading | Principled BSDF, all shader and texture nodes, node sockets |
| Geometry Nodes | 480+ nodes and 650+ node inputs |
| Compositor | All nodes and 360+ inputs |
| Modifiers | All modifier types and 750+ settings |
| Constraints | All constraint types and 340+ settings |
| Physics | Cloth, soft body, fluid, rigid body, force fields, particles, dynamic paint |
| Render & World | Render passes, light paths, film, color management, EEVEE and Cycles settings |
| Viewport | Overlays, shading, gizmos, snapping, pivot, proportional editing |
| Paint & Sculpt | Brush and stroke settings, Grease Pencil |
| Animation | Interpolation, easing, NLA, F-curve modifiers |

<p align="center"><img src="docs/screenshot_2.png" width="90%" alt="A selection of Infocard images"></p>

## Getting started

1. Download `infocard-1.1.0.zip` from the [latest release](../../releases/latest).
2. In Blender, open **Edit › Preferences › Add-ons**, click the menu in the top-right corner and choose **Install from Disk**, then select the zip.
3. In the 3D Viewport press **N** and open the **Infocard** tab.
4. Hover any setting.

## Configuration

All options are in the **Infocard** tab of the 3D Viewport sidebar:

| Option | Description |
|---|---|
| Infocard | Turns the cards on or off |
| Size | Scales the card |
| Edit Card Layout | Shows a preview card for positioning |
| Corner / Position / Manual | Snap to a corner, enter exact coordinates, or drag the card freely |
| Picture ratio | Sets the aspect ratio of the images (1:1, 4:3, 3:2, 16:9, 2:1) |

## Compatibility

- Blender 4.2 LTS or later (developed and tested on Blender 5.2).
- Windows, macOS and Linux.
- No internet connection, account or external dependencies required.

## FAQ

**Does Infocard affect performance?**
No. It only responds to mouse movement over the interface and adds no data to your scene.

**Can I use it with other add-ons?**
Yes. Infocard only reads the setting under the cursor and does not change other add-ons.

**A setting has no picture. What should I do?**
Please [open an issue](../../issues) with a screenshot of the setting. Missing pictures are added in updates.

## Support

Bug reports and suggestions are welcome through [GitHub Issues](../../issues).

## License

The source code is licensed under the [GNU General Public License v3.0 or later](LICENSE).
The images are released under CC0.
