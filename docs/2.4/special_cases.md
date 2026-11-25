# pipInstall2 - Special cases

Most plugins only need package names and version conditions, as described in [README.md](README.md). This page covers everything else.

- [Special entries](#special-entries)
- [Platform conditions (environment markers)](#platform-conditions-environment-markers)
- [Package names and import names](#package-names-and-import-names)
- [Installing from a git repository](#installing-from-a-git-repository)
- [Requiring a Python version](#requiring-a-python-version)
- [How entries are corrected](#how-entries-are-corrected)
- [Not supported](#not-supported)
- [Version numbers: pre-releases and post-releases](#version-numbers-pre-releases-and-post-releases)

## Special entries

These can be anywhere in `sbcPythonDependencies` or in a requirements file.

| Entry | Meaning |
| --- | --- |
| `--verbose` | Turns on detailed logging, including pip's own output. |
| `--clear` | Creates the venv from scratch instead of keeping the existing one, so every package is downloaded and installed again. Use it to get the latest versions of packages that have no version condition, or to start again if the venv is broken. Remove it afterwards, or every run starts from scratch. |
| `--python<condition>` | The Python version the plugin needs, e.g. `--python>=3.11`. See [Requiring a Python version](#requiring-a-python-version). |

## Platform conditions (environment markers)

A standard (PEP 508) environment marker after a `;` makes a package platform dependent:

```text
picamera2; sys_platform == "linux"
pygrabber==0.2; sys_platform == "win32"
numpy>=2; python_version >= "3.11"
some-arm-package; platform_machine == "aarch64"
```

- The marker is checked on the SBC that pipInstall2 is running on.
- If it matches, the marker is removed and the package is handled as normal.
- If it does not match, the package is dropped (and logged). It is not installed.
- If the marker cannot be understood, a warning is logged and the package is installed anyway.

Common markers:

| Marker | Example values |
| --- | --- |
| `sys_platform` | `linux`, `win32`, `darwin` |
| `platform_machine` | `aarch64` (64-bit Pi), `armv7l` (32-bit Pi), `x86_64` |
| `python_version` | `3.11` (Bookworm), `3.13` (Trixie) |
| `os_name` | `posix`, `nt` |

Markers choose what to install. They do not enforce anything: to require a Python version use [`--python`](#requiring-a-python-version).

## Package names and import names

A package's name on PyPI (what pip installs) can differ from the name used to import it in Python:

| PyPI package name | Import name |
| --- | --- |
| `opencv-python` | `cv2` |
| `Pillow` | `PIL` |
| `PyYAML` | `yaml` |
| `pyserial` | `serial` |
| `PyGObject` | `gi` |

**Use the PyPI package name.** It is what pip installs, and pipInstall2 finds its version in pip's list of installed packages.

If an entry is not in pip's list, pipInstall2 looks for a module with that name (without running it). If one is found:

- with no version condition, it is treated as installed and skipped
- with a version condition, pipInstall2 stops with exit code 11 before installing anything - unless the module's version is known (from the package that provides it) and already meets the condition, e.g. `serial>=3` with pyserial 3.5. Otherwise the entry would be sent to pip under the import name, and PyPI has unrelated packages with some of these names (e.g. `gi`, `serial`, `attr`), which would be installed in the venv and hide the real module. The log names the PyPI package to use where it is known:

```text
These entries are installed modules that pip does not know by that name (an import name, or a module installed with apt), so a version condition cannot be used with them:
    gi>=3.40 (version unknown) - use the PyPI package name, or remove the condition
    serial>=4 (version 3.5) - use the PyPI package name, e.g. pyserial>=4
```

The search is for modules that pip has no information about at all, usually from `apt`, e.g. `libcamera` (`python3-libcamera`) and `pykms` (`python3-kms++`), both used by picamera2. They can be listed, without a version condition, to state that the plugin needs them. They are not on PyPI, so if they are not installed the install fails (exit code 10) - install them with `apt`.

## Installing from a git repository

```text
git+https://github.com/pallets/flask.git
git+https://github.com/x/y.git#egg=y
```

The `#` in a git URL is not a comment because there is no space before it. Version conditions and markers cannot be used with git URLs. A git package is always installed, because its version cannot be checked beforehand.

A git URL must start with `git+https://`, `git+ssh://` or `git+file://` (for a repository on the SBC itself), and can only contain letters, digits and `. _ ~ : / ? # [ ] @ ! & + , = % -`. A branch, tag or commit goes after `@`, e.g. `git+https://github.com/x/y.git@v1.2`. Any other git URL (e.g. one with a space, quote or `$`) stops the install with exit code 11. `git+http://` is not allowed because the download is not encrypted, so the code could be changed on the way.

A URL for a private repository can include a user name and password or token, e.g. `git+https://user:token@github.com/x/y.git`. The password or token (also `git+https://token@github.com/...`) is shown as `***` in the log, but it is stored in plain text in plugin.json (or the requirements file), and in `pipInstall_requirements.txt` and `pipInstall_report.json` in the venv, which can only be read by the user that runs pipInstall2. `git+ssh://` with an SSH key for the `dsf` user avoids storing a password.

## Requiring a Python version

Add a `--python` entry to stop the install cleanly on a system whose Python is too old (or too new):

```text
--python>=3.11
```

- Any version condition can be used, e.g. `--python>=3.11,<3.14`.
- `==3.13` means exactly 3.13.0. Use `==3.13.*` for any 3.13 release.
- There can be several `--python` entries. Each one is tested in turn and its result is logged, and all of them must pass.
- The checks are made before anything is installed. If any condition is not met, nothing is installed and pipInstall2 exits with code 15.
- A `--python` entry with no condition, or one that cannot be understood, is logged as `Invalid` and stops pipInstall2 with exit code 11.

Example log, with `--python>=3.10`, `--python<3.13` and `--python==3.13.*` on a Trixie system:

```text
Checking the plugin's Python version requirements (this system has Python 3.13.5):
    --python>=3.10 ==> Passed
    --python<3.13 ==> Failed
    --python==3.13.* ==> Passed
Python 3.13.5 does not meet the plugin's Python version requirements. Nothing was installed
```

Platform markers (per-package conditions such as `; python_version >= "3.11"`) are not a substitute for `--python`. An entry whose marker does not match the installed Python version is silently left out, so the install would succeed without the package.

For reference, Raspberry Pi OS Bookworm has Python 3.11 and Trixie has Python 3.13.

## How entries are corrected

All entries from `sbcPythonDependencies` and requirements files are combined into one list (a virtual requirements file), which is shown in the log. Each entry is corrected to standard requirements syntax first:

| Entry | Becomes |
| --- | --- |
| `numpy >= 1.2 , < 3` | `numpy<3,>=1.2` |
| `jsonschema [format] >= 4` | `jsonschema[format]>=4` |
| `picamera2; sys_platform == "linux"` | `picamera2` on Linux, dropped elsewhere |

An entry that cannot be corrected stops pipInstall2 with exit code 11.

## Not supported

pip options are not supported, in requirements files or in `sbcPythonDependencies`. The only entries that start with `-` are pipInstall2's own [special entries](#special-entries) (`--verbose`, `--clear`, `--python...`).

An entry that contains a pip option, at the start (e.g. `-r other.txt`) or after a package (e.g. `numpy --hash=sha256:...`), stops pipInstall2 with exit code 11. This is checked while the entries are read, before the venv is created or anything is installed. The log names the option and where it was found, e.g.:

```text
"--extra-index-url https://www.piwheels.org/simple" (requirements.txt line 3):
pip option "--extra-index-url" is not supported - see "Not supported" in special_cases.md
Package sources (indexes) cannot be set by a plugin - they are set for the whole system in /etc/pip.conf (Raspberry Pi OS already adds piwheels there)
```

The options are excluded for these reasons:

| Option | Why it is not supported | Instead |
| --- | --- | --- |
| `-i` / `--index-url`, `--extra-index-url`, `--no-index`, `-f` / `--find-links`, `--trusted-host` | They would let a plugin make pip download packages from any server. With `--extra-index-url`, a package with the same name on another server can be installed instead of the real one (dependency confusion). | Package sources are set for the whole system in `/etc/pip.conf`. Raspberry Pi OS already adds piwheels there. |
| `-r other.txt` | Requirements files including other requirements files is not implemented. | List each requirements file in `sbcPythonDependencies`, e.g. `["requirements.txt", "camera.txt"]`. |
| `-c constraints.txt` | Not implemented. | Put the version condition on the package itself, e.g. `numpy<2`. |
| `-e .` / `--editable` | Would install the plugin's own source code (or any folder) as a package. | Not needed - the plugin's python files are run from its `dsf` folder. |
| `--pre` | Allows pre-releases of every package, including dependencies. | Write a pre-release in the condition of the one package that needs it, e.g. `dsf-python>=3.7.0b1` - pip then accepts pre-releases for that package. See [Version numbers](#version-numbers-pre-releases-and-post-releases). |
| `--hash=...` | If one package has a hash, pip requires a hash for every package, including dependencies, which breaks the combined install. | Use an exact version, e.g. `numpy==1.26.4`. |
| `--user` | Installs into the user's own folder outside the venv. pip refuses it inside a venv, and every package is installed in the plugin's venv anyway. | Remove it - e.g. `--user dsf-python` becomes `dsf-python`. |
| `--only-binary`, `--no-binary`, `--prefer-binary` | `--prefer-binary` is always used. The others would apply to every package. | - |
| Any other option (e.g. `--no-deps`, `--upgrade`, `--global-option`) | pipInstall2 decides how pip is run. | - |

These are not supported either, and also stop pipInstall2 with exit code 11:

- Direct URL references such as `name @ https://.../file.whl` (use `git+` for git repositories)
- Lines continued with `\`

## Version numbers: pre-releases and post-releases

Python package versions follow PEP 440. Pre-releases (alpha `a`, beta `b`, release candidate `rc`) sort **before** their release, and post-releases sort **after** it:

```text
3.7.0b1  <  3.7.0  <  3.7.0.post1
```

This is how each version condition treats a beta, the release and a post-release:

| Condition | 3.7.0b1 | 3.7.0 | 3.7.0.post1 |
| --- | --- | --- | --- |
| `<=3.7.0` | ✓ | ✓ | ✗ |
| `<3.7.0` | ✗ (special rule) | ✗ | ✗ |
| `==3.7.0` | ✗ | ✓ | ✗ |
| `==3.7.*` | ✓ | ✓ | ✓ |
| `>=3.7.0` | ✗ | ✓ | ✓ |
| `>3.7.0` | ✗ | ✗ | ✗ (special rule) |
| `~=3.7.0` | ✗ | ✓ | ✓ |
| `!=3.7.0` | ✓ | ✗ | ✓ |
| `<3.7.1` | ✓ | ✓ | ✓ |

Special rules (marked in the table):

- `<V` excludes pre-releases of V itself. `<3.7.0` rejects `3.7.0b1` even though it sorts lower. `<=3.7.0` has no such rule and accepts it.
- `>V` excludes post-releases of V itself. `>3.7.0` rejects `3.7.0.post1` even though it sorts higher. Use `>=3.7.0` to include post-releases.

Practical choices:

- **3.7.0 and its post-releases, nothing newer:** `>=3.7.0,<3.7.1`, or `==3.7.0.*`, which also accepts betas of 3.7.0. Avoid `<=3.7.0`, which shuts out post-releases.
- **Anything in 3.7, including betas:** `>=3.7.0b1,<3.8`, or `==3.7.*`, which also accepts betas.
- **A beta already installed should count as meeting the condition:** write the lower limit as a pre-release, e.g. `>=3.7.0b1` not `>=3.7.0`. Otherwise pipInstall2 sees that the beta does not meet the condition and installs the newest version that does.
