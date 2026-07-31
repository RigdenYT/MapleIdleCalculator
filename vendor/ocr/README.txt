GENERATED OCR RUNTIMES
======================

Do not commit platform OCR binaries here.

build_tools/stage_ocr_runtime.py creates one of these directories on the build
machine:

- vendor/ocr/windows-x86_64
- vendor/ocr/linux-x86_64

PyInstaller then embeds that staged runtime in the matching release. GitHub
Actions installs Tesseract on its temporary Windows/Linux runner and stages the
files automatically.
