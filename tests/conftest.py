import os

# Unit tests exercise widget behavior without requiring the native Windows shell.
# Native rendering, tray, DPI, and installer behavior are covered by separate smoke checks.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
