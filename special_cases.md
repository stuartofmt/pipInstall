# pipInstall2 - Special cases

Most plugins only need package names and version conditions, as described in [readme.md](readme.md). This page covers everything else.

- [Special entries](#special-entries)
- [Platform conditions (environment markers)](#platform-conditions-environment-markers)
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
| `--python<condition>` | The Python version the plugin needs, e.g. `--python>=3.11`. See [Requiring a Python version](#requiring-a-python-version). |
| `--user name` | `--user` is ignored with a warning. The package is installed in the plugin's venv like any other. |

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

## Installing from a git repository

```text
git+https://github.com/pallets/flask.git
git+https://github.com/x/y.git#egg=y
```

The `#` in a git URL is not a comment because there is no space before it. Version conditions and markers cannot be used with git URLs. A git package is always installed, because its version cannot be checked beforehand.

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
| `--user six` | `six` (with a warning) |
| `picamera2; sys_platform == "linux"` | `picamera2` on Linux, dropped elsewhere |

An entry that cannot be corrected stops pipInstall2 with exit code 11.

## Not supported

These pip requirements-file features are not supported. An entry using any of them stops pipInstall2 with exit code 11 (invalid entry):

- Options such as `-r other.txt`, `-c constraints.txt`, `-e .`, `--index-url`, `--extra-index-url`, `--pre`
- Per-package options such as `--hash=sha256:...`
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
