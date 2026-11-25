# pipInstall2 2.4.1 - change notes

What changed since pipInstall2 2.1.0 ([2.1 documentation](../2.1/README.md)), newest first. The changes in versions 2.1.1 to 2.3.0 are included: they are part of 2.4. See [README.md](README.md) for what pipInstall2 does and how to use it.

## Version 2.4.1 - Stuart Strolin

- Security: commands (pip, venv creation, the import test) are no longer run through the shell. Previously a `git+` line in a requirements file was passed to the shell unchecked, so shell syntax in it (e.g. `$(...)` or `;`) ran as a command - when checking installed versions on every run, and again in the one-at-a-time fallback
- A `git+` URL must use `git+https://`, `git+ssh://` or `git+file://` and contain only URL characters (see [special_cases.md](special_cases.md#installing-from-a-git-repository)) - anything else stops with exit code 11
- A requirements file must be inside `<plugin path>/dsf` - a name that leads outside it (`../`, an absolute path or a symbolic link pointing outside) stops with exit code 13. Previously e.g. `../../other/requirements.txt` was read
- A pip option in a requirements file or `sbcPythonDependencies` (e.g. `--extra-index-url`, `-r`, `--pre`, `numpy --hash=...`) is reported with the option, the file and the line, and why (for package index options: set them in `/etc/pip.conf`). Previously the error was the parser's "Expected package name". It is checked before the venv is created, so the install stops straight away. Still exit code 11. [special_cases.md](special_cases.md#not-supported) lists each excluded option, why, and what to use instead
- `--user` is no longer accepted. It is treated as an unsupported pip option and stops with exit code 11 - remove it (e.g. `--user dsf-python` becomes `dsf-python`). Since 2.4.0 it was ignored with a warning; packages are always installed in the plugin's venv
- The result summary shows a git package as `installed from the git repository`, instead of "now Reinstalled with same version"
- Removed code that could never run (a "no version number" case in the pip freeze check, error paths for entries that were already checked, and replacing an already open log file)
- If `<plugin path>/venv` is a symbolic link (or leads outside the plugin folder), pipInstall2 stops with exit code 6 and changes nothing. Previously creating the venv emptied the folder the link pointed to. Files pipInstall2 writes in the venv (log, requirements, report) replace a symbolic link instead of writing through it
- An unexpected error exits with code 9 and the Python traceback in the log. Previously it exited with Python's code 1, which means "no manifest file"
- A requirements file that is not UTF-8 text, or a requirements file name containing a null character, stops with exit code 13 and a message instead of a traceback
- When the venv cannot be created, or `pip freeze` or the site-packages lookup fails, the log gives the reason. Previously it showed `False`, or nothing without `--verbose`
- The venv is created with the Python that runs pipInstall2, instead of whichever `python` is first on PATH, and pipInstall2.py starts with `#!/usr/bin/env python3`, so it works on systems with no `python` command
- The import test has a 60 second time limit - a package whose import hangs (e.g. waits for hardware) is treated as not installed, instead of holding up the install indefinitely
- `git+http://` is no longer allowed (unencrypted) - use `git+https://` or `git+ssh://`. A password in a git URL (`user:password@`) is shown as `***` in the log
- Modules that are part of Python (e.g. `json`, `os`, `shlex`) are recognised from Python's own list and reported as Ignored (built-in), as the readme describes. Previously only modules compiled into Python (e.g. `sys`) were, and others were imported and reported as "already Installed with version ..."
- The import test is replaced by a module search that does not run the module's code (`importlib.util.find_spec`, run with `python -I -c` with a 10 second limit) - no `import_test.py` file is written. A copy left in site-packages or the venv folder by an earlier version is removed (in site-packages the plugin could import it). Previously the module was imported, which ran its code: it could print, start threads, exit or hang, and dotted names (e.g. `pkg.sub`) were reported as not installed. The version comes from the package's metadata, so a module that pip has no information about (e.g. `libcamera` from apt) is found but has no version
- Package names are matched with `-`, `_` and `.` treated as the same (e.g. `zope-interface` finds an installed `zope.interface`), so such packages are no longer reinstalled on every run
- When the system has no `packaging` module, the copy installed in the venv by an earlier run is used, instead of installing it again (which needed the network) on every run
- A version condition with no version (e.g. `six ===`, `--python===`) stops with exit code 11. Previously `six ===` failed in pip with exit code 10
- A version condition on a module that pip does not know by that name (an import name such as `gi` or `serial`, or a module from apt such as `libcamera`) stops with exit code 11 before anything is installed, unless the module's known version already meets it. The log names the PyPI package to use where known, e.g. `serial>=4` → `pyserial>=4`. Previously the entry was sent to pip under the import name, which failed, or installed an unrelated PyPI package with that name (e.g. `gi`, `serial`) that hid the real module. Use the PyPI package name for version conditions (see [special_cases.md](special_cases.md#package-names-and-import-names))
- Every python and pip command is run with `python -I` from the root folder, so a module in the current folder (e.g. a `pip/` folder) or `PYTHONPATH` can no longer replace pip or a module the command uses. The manifest and plugin paths are made absolute first
- A token in a git URL (`git+https://token@github.com/...`) is also shown as `***` in the log. `pipInstall_requirements.txt` and `pipInstall_report.json`, which can contain the URL, can only be read by the user that runs pipInstall2
- A line ending in `.txt` in a requirements file stops with exit code 13 - previously it was looked up on PyPI as a package (e.g. `other.txt`). A requirements file entry in `sbcPythonDependencies` is recognised whatever the case of `.txt` (e.g. `REQS.TXT`)
- pip uses a cache of its own for each run, in a new folder in the venv folder that is deleted when pipInstall2 exits. A package downloaded by the dry run is no longer downloaded again by the install (or by the one-at-a-time fallback) - e.g. numpy, 15 MB, is now downloaded once instead of two or three times. The user's own pip cache is not used, and the pip cache purge step is removed - it emptied the whole pip cache of the user running pipInstall2, not just what the install had added. The cache is set with an environment variable, so it also applies to installing build dependencies (`--no-cache-dir` did not)
- The venv's site-packages folder is asked from the venv python, instead of read from `python -m site` output - a plugin path containing `'` gave the wrong folder, and if none was found, files with the names of old pipInstall2 files were removed from the current folder. If it cannot be found, pipInstall2 stops with exit code 12
- Entries and `--python` conditions are checked before the venv is created or changed (when the system python has `packaging`, as usual). Previously, e.g. a typo with `--clear` rebuilt the venv (removing every package) before stopping with exit code 11
- Unused-package removal counts the package behind an import name as needed (e.g. `yaml` keeps PyYAML in the venv)
- After installing, every entry's version condition is checked against the version now installed. An entry whose condition is no longer met is reported as failed (exit code 10), e.g. two entries for the same package with different conditions (`six<1.17` and `six>=1.17`), or a skipped `urllib3<2.4` after another entry installed urllib3 2.4.0. Previously both were reported as installed and pipInstall2 exited with 0
- If removing unused packages fails part way, the summary lists only the packages that were removed
- Faster runs: the installed packages are read from the package metadata instead of running `pip freeze`; facts about the python running pipInstall2 (its version, and the packages the venv upgrades) are no longer found by starting python again; pip's version is read from the venv instead of running `pip --version`; when nothing was installed, the installed versions are not looked up again after the install step. A re-run with nothing to change takes about 2.2 seconds instead of 3 on a Pi 5
- The final log line shows the exit code as a number and name, e.g. `Exiting with code 0 (SUCCESS)`
- A `git+` URL is no longer passed to the installed-version checks (pip freeze and the import test). It is reported as not installed, so it is always installed, as before
- A plugin path containing spaces no longer breaks venv creation and the import test
- The venv is created without `--upgrade-deps`, so creating it needs no network. pip (and setuptools on Python 3.11) is then upgraded as a separate step that makes one quick attempt: without a network it gives up after a few seconds, logs a warning, and the pip that came with Python is used. Previously pip retried for tens of seconds or longer, with nothing in the log
- If pip is configured not to use a package index (`no-index`, e.g. in `/etc/pip.conf` with `find-links` pointing at a folder of wheels), the log says so instead of saying pip is up to date
- pip retries a failed connection once instead of 5 times (`PIP_RETRIES=1`, which also applies to installing build dependencies). Without a network a failing install now takes seconds instead of about a minute
- A manifest without `sbcPythonDependencies` is treated as having nothing to install (exit code 0) - previously pipInstall2 crashed with a KeyError (exit code 1). A manifest with no `name`, that is not a json object, or whose `sbcPythonDependencies` is not a list of strings now stops with exit code 7
- The failure reason in the result summary includes errors from installing build dependencies (e.g. `No matching distribution found for setuptools`), instead of "pip reported an error"
- An existing venv is kept instead of being recreated on every run, so packages from an earlier run are not downloaded again and a re-run needs no network unless something new is needed. It is still created from scratch if it was made for a different Python version (e.g. after upgrading Bookworm to Trixie), its python does not run, or it cannot see the system packages
- A package with no version condition keeps the version an earlier run installed - it is no longer upgraded to the latest version on every run
- New `--clear` entry: creates the venv from scratch (the previous behaviour)
- A kept venv last built by pipInstall2 before 2.4.0 has the old sys.path hook files (`plugin_path_change.pth` / `.py`) removed, so its packages no longer come ahead of the standard library
- After a successful install, packages in the venv that nothing in the package list needs (e.g. left from an entry that has been removed) are uninstalled, and listed in the log and the summary
- The manifest is read before the venv is created, and messages from before the log file is created are now written to it (including a manifest error)

## Version 2.4.0 - Stuart Strolin

- After installing, `pip check` is run. If the plugin's packages are not compatible with each other (e.g. one needs `numpy>=2` but `numpy<2` was installed), they are listed and pipInstall2 exits with the new exit code 16
- When installing one module at a time, each module gets its own dry run first, so a build from source is reported (with the build tools check) before it starts
- The result summary gives pip's reason for each failed module, e.g. `No matching distribution found for json==2.0.0`, instead of its state before the install
- Packages that were already available are described as installed in the venv or found in the system packages, instead of "previously installed by Pip"
- pip's "Ignored the following versions that require a different python version" lines are only shown with `--verbose`
- An entry that looks like a mistyped requirements file name (e.g. `requirements.txt1`) now stops with exit code 13, instead of being looked up on PyPI as a package
- When the pip cache is disabled (normal under DSF), the cache purge no longer logs pip's warning and error - it is logged at debug level only
- pip is run with `--prefer-binary`, so a version with a ready-built wheel is chosen over building a newer version from source
- The dry run log marks packages that will be built from source, with a warning that building can take a long time, and checks for the basic build tools (C and C++ compilers, Python headers, pkg-config), logging any that are missing with the `apt` command to install them

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
