# pipInstall2 - Special cases

Most plugins only need package names and version conditions, as described in [readme.md](readme.md). This page covers everything else.

- [Special entries](#special-entries)
- [Platform conditions (environment markers)](#platform-conditions-environment-markers)
- [Installing from a git repository](#installing-from-a-git-repository)
- [Requiring a Python version](#requiring-a-python-version)
- [Overriding a system package](#overriding-a-system-package)
- [How entries are corrected](#how-entries-are-corrected)
- [Not supported](#not-supported)
- [Version numbers: pre-releases and post-releases](#version-numbers-pre-releases-and-post-releases)

## Special entries

These can be anywhere in `sbcPythonDependencies` or in a requirements file.

| Entry | Meaning |
| --- | --- |
| `--verbose` | Turns on detailed logging, including pip's own output. |
| `--python<condition>` | The Python version the plugin needs, e.g. `--python>=3.11`. See [Requiring a Python version](#requiring-a-python-version). |
| `!name` | Always install the plugin's own copy in the venv, even if a system copy already meets the request. See [Overriding a system package](#overriding-a-system-package). |
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

Markers can be combined with `!`, e.g. `!simplejpeg; python_version < "3.13"` overrides the system copy on Bookworm only.

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

## Overriding a system package

This is very much an edge use case. The settings need to be tested by the plugin's author, on each OS release the plugin supports, to make sure the packages install and import as needed.

### When you need this

The venv can see the system's Python packages (e.g. packages installed with `apt`). A package the system already has at a suitable version is normally used as it is, and is not installed again in the venv.

That can go wrong when the system has a **compiled** package that was built against an older version of something the plugin installs into its venv. The venv's newer copy is loaded, the system's compiled package does not match it, and the import fails. Typical errors:

```text
ValueError: numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.x
```

Example: on Raspberry Pi OS Bookworm, `apt` installs `python3-picamera2` and `python3-numpy` 1.24, and the compiled helper `simplejpeg` is built against numpy 1. A plugin that also needs numpy 2 (e.g. through `opencv-python`) gets numpy 2 in its venv. `import picamera2` then loads apt's `simplejpeg`, which fails with the error above.

Prefixing a package with `!` makes pipInstall2 install the plugin's own copy in the venv, even though the system already has one. pip's copy is built for the newer version, so the two match.

### Step 1: Gather information

Do this on a system that shows the problem, with the plugin installed as normal (without any `!`).

**a. Find where each import is coming from.** Use the plugin's venv python, as the `dsf` user:

```bash
sudo -u dsf <plugin path>/venv/bin/python -c "import numpy, simplejpeg; print(numpy.__version__, numpy.__file__); print(simplejpeg.__file__)"
```

A path inside `<plugin path>/venv` is the venv's copy. A path in `/usr/lib/python3/dist-packages` is the system's copy.

**b. Find the apt package that a system copy comes from, and its version:**

```bash
dpkg -S /usr/lib/python3/dist-packages/simplejpeg     # -> python3-simplejpeg
dpkg -l python3-picamera2                            # installed version
```

**c. List the other packages it depends on.** The package that fails is often a dependency of the one the plugin uses:

```bash
apt-cache depends python3-picamera2 | grep python3
```

**d. Find which of those are compiled against numpy.** Only these need overriding. Pure Python packages and compiled packages that do not use numpy's C interface are not affected:

```bash
for p in python3-simplejpeg python3-pidng python3-av python3-openexr python3-pil; do
  n=$(dpkg -L $p | grep -E '\.so$' | xargs -r grep -l -a -E '_ARRAY_API|numpy\.core\.multiarray|numpy\._core' | wc -l)
  echo "$p: $n compiled files use numpy"
done
```

For example, on Raspberry Pi OS Trixie only `python3-simplejpeg` shows a non-zero count. `picamera2` itself is pure Python. Check on each OS release, because packages can change between releases.

**e. Check that pip can install each package to be overridden:**

```bash
pip download --only-binary=:all: --no-deps simplejpeg -d /tmp/wheelcheck
```

- A `.whl` file is downloaded: pip has a ready-built copy for this system.
- `No matching distribution found`: either the package is not on PyPI (e.g. `libcamera`, which can only come from `apt` and cannot be overridden), or pip will have to build it from source. A source build needs the system's build tools and `-dev` packages. pip's error message names what is missing (e.g. `python-prctl` needs `libcap-dev`), and these go in `sbcPackageDependencies` in `plugin.json`.

**f. Note which OS releases are affected.** E.g. Bookworm (Python 3.11) has the problem and Trixie (Python 3.13) does not. A [platform condition](#platform-conditions-environment-markers) can then limit the override to the releases that need it.

### Step 2: Write the requirements file

Mark only the packages found in step 1d, and limit them to the affected releases:

```text
opencv-python                           # needs numpy 2
!simplejpeg; python_version < "3.13"    # apt's copy is built for numpy 1 on Bookworm
```

On Bookworm this installs the venv's own `simplejpeg`, built for numpy 2. On Trixie the `!` entry is dropped and the system's copy is used.

If the whole package has to come from pip (e.g. the pure Python part also needs a newer version), mark it as well. Pin it to the version `apt` has (step 1b) when it has to work with other system components. For example, pip's `picamera2` still uses apt's `libcamera`:

```text
!picamera2==0.3.31; python_version < "3.13"
!simplejpeg; python_version < "3.13"
```

pip's `picamera2` depends on `python-prctl`, which is built from source, so also add to `plugin.json`:

```json
"sbcPackageDependencies": ["libcap-dev"]
```

### Step 3: Test

1. Add `--verbose` to the requirements file and reinstall the plugin, or run pipInstall2 by hand:

   ```bash
   sudo -u dsf /opt/dsf/bin/pipInstall2.py -m <path to plugin.json> -p <plugin path>
   ```

2. Check the summary at the end of the log. Each `!` package should be listed as installed, e.g. `!simplejpeg ==> was previously installed by Pip with version 1.8.1, now 1.9.0`.
3. Repeat step 1a. Each overridden package should now come from `<plugin path>/venv`, and there should be no import errors.
4. Run the plugin and exercise the code that uses these packages.

### How it works

1. The packages marked with `!` are installed first, with `pip install --ignore-installed --no-deps`: dry run, then all together, falling back to one at a time.
2. Everything is then installed as normal. The marked packages are now satisfied by their venv copies, so only their missing dependencies are installed.
3. A marked package that fails in step 1 is reported as failed and left out of step 2, so a system copy is not used in its place.

The files `pipInstall_venv_only_requirements.txt` and `pipInstall_venv_only_report.json` in `<plugin path>/venv` show what was requested and planned in step 1.

### Things to know

- pipInstall2 cannot tell which system packages need overriding. Every package that has to come from the venv must be marked.
- The system copies are not changed, so the system Python and other plugins are not affected.
- `!` is a pipInstall2 feature. A requirements file using it cannot be passed to `pip install -r` directly.

## How entries are corrected

All entries from `sbcPythonDependencies` and requirements files are combined into one list (a virtual requirements file), which is shown in the log. Each entry is corrected to standard requirements syntax first:

| Entry | Becomes |
| --- | --- |
| `numpy >= 1.2 , < 3` | `numpy<3,>=1.2` |
| `jsonschema [format] >= 4` | `jsonschema[format]>=4` |
| `--user six` | `six` (with a warning) |
| `! tqdm` | `!tqdm` |
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
