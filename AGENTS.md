# Repository instructions: OfflinePDF

Windows desktop PDF tool (Python 3.12, CustomTkinter, PyMuPDF). Build and release
details are in BUILDING.md; user-facing text is Korean first (translations in
offline_pdf/translations.json).

## Version numbers: bump them yourself

Every change that will be released gets a version bump, chosen by the size of the
change (the project owner's rule). Bumping a position resets the lower ones to 0,
and a trailing `.0` fix number is not written (`1.0.1`, not `1.0.1.0`).

| Change | Position | From 1.0.0 |
| --- | --- | --- |
| Substantial update (new features, reworked screens) | second | 1.1.0 |
| Small update (improvements, packaging/distribution changes) | third | 1.0.1 |
| Bug fixes only | fourth | 1.0.0.1 |

Never change the first number unless the owner asks for it.

Update all of these together (tests/test_version.py fails the build otherwise):
- `offline_pdf/__init__.py` (`__version__`)
- `packaging/windows-version.txt` (four numbers, e.g. `(1, 0, 1, 0)`, and the two strings)
- "current source version" in `README.md` and `README.en.md`
- a `## <version> · <date>` section at the top of `CHANGELOG.md` (Korean)

Several changes before one release share one bump: use the size of the largest.
