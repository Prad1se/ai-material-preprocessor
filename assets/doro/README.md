# Doro document mascot asset contract

No Doro image is distributed in this directory. The project currently has no confirmed
redistribution rights for a Doro image, so the application uses a neutral text-and-icon status
view.

Future assets must have documented redistribution rights and should provide transparent PNGs for
these states:

- `empty.png`
- `ready.png`
- `processing.png`
- `success.png`
- `warning.png`
- `error.png`

Use a consistent canvas and character scale. Recommended source size is 512 x 512 pixels with a
transparent background and safe content inside the central 440 x 440 pixels. The UI must retain
the text status and accessible description when artwork is added; color or artwork alone must not
communicate state.

Replacing the neutral presentation must happen inside `DocumentMascotView`. Workspace layout and
task lifecycle code must not depend on a particular image file.
