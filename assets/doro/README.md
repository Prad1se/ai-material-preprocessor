# Doro document mascot assets

The selected Doro artwork in this directory is distributed with AI Material Preprocessor for
**non-commercial use only**, based on confirmation from the project maintainer. These image files
are **not licensed under the repository's MIT license**. Commercial distributions must remove or
replace them, or obtain separate permission from the relevant rights holders.

This notice records the project's usage basis; it does not claim that the repository owns the
Doro character or the underlying artwork. Copyright, character, and trademark interests remain
with their respective owners and creators. Inclusion does not imply endorsement.

## Included states and provenance

| File | UI state | Source record | Rights basis |
|---|---|---|---|
| `orange.png` | Initial empty state | User-provided project asset | Maintainer-confirmed non-commercial use |
| `ready.png` | Documents selected | User-provided project asset | Maintainer-confirmed non-commercial use |
| `carrying.jpg` | Preview ready | User-provided still from `https://v.douyin.com/6ADvfDOi1TA/` | Maintainer-confirmed non-commercial use and redistribution |
| `processing.gif` | Processing | `https://media1.tenor.com/m/qDqG7n_EV6YAAAAC/doro.gif` | Maintainer-confirmed non-commercial use |
| `cheering.webp` | Success | `https://gengtu.tos-accelerate.volces.com/memes/49/eb/5d/63/49eb5d635abfadf07224b3606638b016.jpeg` | Maintainer-confirmed non-commercial use |
| `wave.gif` | Warning | `https://media4.giphy.com/media/2SJUQVZxSQJoSTrim5/giphy.gif` | Maintainer-confirmed non-commercial use |
| `resting.gif` | Completed / resting | `https://media1.tenor.com/m/6n9eZuKhc3oAAAAd/goddess-of-victory-nikke-doro-meme-sleep.gif` | Maintainer-confirmed non-commercial use |

The error state intentionally keeps the neutral symbol fallback because none of the selected
artwork communicates an error without contradicting the readable status message.

## Presentation contract

`DocumentMascotView` owns artwork selection and scaling. Workspace layout and task lifecycle code
must not depend on a particular file. The UI retains a readable status and accessible description;
color or artwork alone never communicates state.

`AI_MATERIAL_DORO_ASSET_DIR` may point to a user-supplied replacement set. Source-mode users can
also place replacements under the Git-ignored `assets/doro/local/` directory. Overrides use the
same filenames and are never fetched from the network at runtime.
