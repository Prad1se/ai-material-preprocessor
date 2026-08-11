# Privacy

AI Material Preprocessor is local-first. Document conversion, Markdown cleanup, OCR, video
processing, metadata inspection, naming, history, and previews run on the Windows computer where
the application is installed.

## Data that stays local

- source documents, media, extracted text, images, frames, GPS coordinates, and OCR results;
- output files and AI packages;
- task state, history manifests, configuration, and diagnostic reports.

The application does not contain telemetry, analytics, accounts, advertising, or cloud OCR. It
does not upload files by default. Original source files are never deleted or overwritten.

## Optional network access

Update checking is disabled by default. The application contacts the public GitHub Releases API
only after the user enables update checking in Settings and manually clicks **Check for updates**.
That request contains the application version and a generic User-Agent; it does not include file
contents, names, paths, GPS coordinates, history, or configuration.

External tools installed by the user remain subject to their own privacy policies. This release
does not provide online geocoding or cloud OCR.

## Local deletion

History can be searched, deleted selectively, or cleared in the application. Deleting history is
separate from deleting derived cache files, and neither operation deletes source files.
