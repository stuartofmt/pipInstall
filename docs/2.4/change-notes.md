# pipInstall2 2.4 - change notes

What changed since pipInstall2 2.1.0 ([2.1 documentation](../2.1/README.md)), newest first. The changes in versions 2.1.1 to 2.3.0 are included: they are part of 2.4. See [README.md](README.md) for what pipInstall2 does and how to use it.

## Unreleased

- An entry that looks like a mistyped requirements file name (e.g. `requirements.txt1`) now stops with exit code 13, instead of being looked up on PyPI as a package
- When the pip cache is disabled (normal under DSF), the cache purge no longer logs pip's warning and error - it is logged at debug level only

## Version 2.4.0-beta.2 - Stuart Strolin

- Removed the `!` prefix (added in 2.4.0-beta.1). An entry starting with `!` is now an invalid entry (exit code 11). The "Overriding a system package" section was removed from [special_cases.md](special_cases.md)

## Version 2.4.0-beta.1 - Stuart Strolin

- Argument errors now exit with their exit codes (previously crashed with IndexError / NameError)
- The venv python no longer prints the site-packages path every time it starts
- A requirements file (`.txt`) that is not found in `<plugin path>/dsf` now exits with code 13 (previously it was treated as a module name and looked up on PyPI)
- If the `packaging` module is not available in the system python it is installed into the venv and used from there - exits with code 14 if that fails
- `--user` is now ignored (with a warning) - all modules are installed in the plugin venv (previously they were installed in the user site-packages, outside the venv)
- Removed pkg_resources import (deprecated and unused)
- A failed install is no longer reported as succeeded for modules that import without version information
- Removed unused code (sysconfig import, UNSUPPORTED_CONDITIONAL exit code, Dependency types and uri)
- Log file lines are no longer wrapped in quotes
- `pip install --dry-run` (with `--report`) logs what will actually be installed, including dependencies
- Modules are installed together with a single `pip install -r` so pip resolves them consistently
- If that fails, falls back to installing one module at a time and reports each failure with pip's error
- Removed `--force-reinstall` (dependencies were reinstalled and re-downloaded every time)
- pip runs with `--no-cache-dir` (and `PIP_NO_CACHE_DIR=1` while creating the venv) and the pip cache is purged after installing, to save SD card space. The cache is per user (e.g. `~/.cache/pip`) - under DSF it is already disabled because the `dsf` user's home (`/`) is not writable
- Already installed modules with no version requested are no longer upgraded (rule 2 now applies to pip modules too)
- `sbcPythonDependencies` and the contents of requirements files are combined into one list, and each entry is corrected to standard requirements syntax (spaces, `--user`, platform markers). The combined list is logged
- `--verbose` can now be anywhere in `sbcPythonDependencies` or a requirements file (previously it had to be the first manifest entry)
- `--python<condition>` (e.g. `--python>=3.11`) sets the Python version the plugin needs. If the system's Python does not meet it, nothing is installed and pipInstall2 exits with the new exit code 15
- Documentation split: [README.md](README.md) covers the usual case (packages and versions); special entries, markers, git URLs, overriding system packages and the version-number reference moved to [special_cases.md](special_cases.md)
- A package prefixed with `!` (e.g. `!simplejpeg`) is always installed in the venv, even if a system copy already meets the request. These are installed first with `--ignore-installed --no-deps`; their dependencies are installed with everything else. For overriding system (apt) packages, e.g. picamera2 built against numpy 1.x on Bookworm
- The `.pth` / `.py` sys.path hook is no longer written to the venv (code commented out). Normal venv ordering already puts venv packages ahead of system packages; the hook also put them ahead of the standard library, which let PyPI backports (e.g. argparse) shadow stdlib modules
- Trailing comments are ignored e.g. `numpy==1.26  # needed for X`
- A `#` is treated as a comment when at the start or preceded by whitespace (same rule as pip)
- Applies to entries in plugin.json (including `--verbose`) and in requirements files

## Version 2.3.0 - Stuart Strolin

- Added support for version ranges and all PEP 440 comparisons e.g. `numpy>=1.2,<2.0`  `numpy!=1.3`  `numpy==1.*`
- Spaces are allowed around comparisons e.g. `numpy >= 1.2`
- `~=` is no longer converted to `>=` (pip handles it correctly)
- Module parsing now uses packaging.requirements instead of a custom regex
- Modules already installed at a version that meets the condition are skipped instead of reinstalled

## Version 2.1.2 - Stuart Strolin

- Added support for PEP 508 environment markers e.g. `picamera2; sys_platform == "linux"`
- Modules whose marker does not apply to the current platform are skipped
- Applies to entries in plugin.json and in requirements files

## Version 2.1.1 - Stuart Strolin

- Changed logger to initially output to console
- Then after arguments are parsed add the log file
