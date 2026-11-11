# pipInstall2 - Python package installer for DSF plugins

pipInstall2 installs the Python packages a DSF plugin needs on the SBC. Each plugin gets its own Python virtual environment (venv), so packages for one plugin cannot break another plugin or the system Python.

DSF calls pipInstall2 when a plugin is installed, passing it the plugin's `plugin.json` and the plugin's folder. The packages to install come from the `sbcPythonDependencies` entry in `plugin.json`.

For changes between versions see [release-notes.md](release-notes.md).

## Recommended: list packages in a requirements file

The preferred way to declare packages is to put **one or more requirements files** in `sbcPythonDependencies`, rather than a long list of packages directly in `plugin.json`.

`plugin.json`:

```json
"sbcPythonDependencies": ["requirements.txt"]
```

`dsf/requirements.txt` (in the same folder as the plugin's python files):

```text
# Web server
uvicorn[standard] >= 0.35.0
requests

# Camera support - Linux only
picamera2; sys_platform == "linux"

numpy >= 1.24, < 3      # 2.x tested
```

Why a requirements file is better:

- **Standard format.** It is the same file format pip uses, so the same file can be tested by hand with `pip install -r requirements.txt`.
- **Easier to read and maintain.** One package per line, with room for comments explaining why each package and version is needed. JSON does not allow comments.
- **Shorter plugin.json.** The manifest stays focused on the plugin itself.
- **Can be split.** Several files can be listed, e.g. `["requirements.txt", "camera.txt"]`, and packages can be listed directly in plugin.json alongside them if needed.

Rules for requirements files:

- An entry in `sbcPythonDependencies` that ends in `.txt` is treated as a requirements file.
- The file is looked for in `<plugin path>/dsf/`. A subfolder can be given e.g. `extras/camera.txt`.
- If the file is not found, pipInstall2 stops with exit code 13.
- Requirements files cannot include other requirements files. Only `.txt` entries in plugin.json are expanded.

## Package descriptions that are handled

The same descriptions work in a requirements file and directly in `sbcPythonDependencies`.

### Package names

| Example | Meaning |
| --- | --- |
| `requests` | Plain package name |
| `PyGithub` | Names are not case sensitive |
| `keyrings.alt`, `dsf-python`, `dsf_python` | Names may contain `.`, `-` and `_` |
| `uvicorn[standard]`, `pkg[extra1,extra2]` | Extras (optional features of a package) in square brackets |
| `git+https://github.com/pallets/flask.git` | Install directly from a git repository |
| `git+https://github.com/x/y.git#egg=y` | git URL with a fragment (the `#` is not a comment because there is no space before it) |

### Version conditions

Any standard (PEP 440) comparison can follow the name. Spaces around comparisons are allowed.
See [Reference: version numbers and version conditions](#reference-version-numbers-and-version-conditions) for how betas and post-releases are treated.

| Example | Meaning |
| --- | --- |
| `numpy==1.26.4` | Exactly this version |
| `numpy==1.*` | Any 1.x version |
| `numpy!=1.25.0` | Any version except this one |
| `numpy>=1.24`, `numpy>1.24` | At least / greater than |
| `numpy<=2.0`, `numpy<2` | At most / less than |
| `numpy~=1.26.0` | Compatible release: `>=1.26.0, <1.27` |
| `pkg===1.0-custom` | Exact string match (rarely needed) |
| `numpy>=1.24,<3` | A range: several conditions separated by commas |
| `pkg[extra] >= 1, != 1.3` | Extras, spaces and several conditions together |
| `pkg>=1.0rc1` | Pre-release versions |

### Platform conditions (environment markers)

A standard (PEP 508) environment marker after a `;` makes a package platform dependent:

```text
picamera2; sys_platform == "linux"
pygrabber==0.2; sys_platform == "win32"
numpy>=2; python_version >= "3.11"
some-arm-package; platform_machine == "aarch64"
```

- The marker is checked on the SBC that pipInstall2 is running on.
- If it matches, the package is handled as normal.
- If it does not match, the package is skipped (and logged).
- If the marker cannot be understood, a warning is logged and the package is installed anyway.

### Comments

Anything from a `#` that starts an entry, or that has a space or tab before it, to the end of the line is ignored:

```text
# this whole line is ignored
numpy==1.26  # needed for X
picamera2; sys_platform == "linux"  # camera support
```

Comments also work in `sbcPythonDependencies`, e.g. `"requirements.txt  # main packages"`. An entry that is only a comment is ignored.

### Special entries

| Entry | Meaning |
| --- | --- |
| `--verbose` | Must be the **very first** entry in `sbcPythonDependencies`. Turns on detailed logging, including pip's own output. |
| `--user name` | `--user` is ignored with a warning. The package is installed in the plugin's venv like any other. |
| `!name` | Always install the plugin's own copy in the venv, even if a system copy (e.g. from `apt`) already meets the request. See [Overriding a system package](#overriding-a-system-package). |
| `sys`, `os`, `json`, `shlex` ... | Modules that are part of Python itself are recognised and ignored. They do not need to be listed. |

### Not supported

These pip requirements-file features are not supported. An entry using any of them stops pipInstall2 with exit code 11 (invalid entry):

- Options such as `-r other.txt`, `-c constraints.txt`, `-e .`, `--index-url`, `--extra-index-url`, `--pre`
- Per-package options such as `--hash=sha256:...`
- Direct URL references such as `name @ https://.../file.whl` (use `git+` for git repositories)
- Lines continued with `\`

## What pipInstall2 does

### 1. Create the virtual environment

The venv is created at `<plugin path>/venv`:

- It is recreated from scratch every time pipInstall2 runs.
- pip in the venv is upgraded to the latest version.
- The venv can see the system's Python packages (e.g. packages installed with `apt`). Packages installed in the venv take priority over system packages with the same name.

### 2. Read the package list

- `sbcPythonDependencies` is read from `plugin.json`.
- Comments are removed, and `--verbose` is acted on.
- Requirements files are read and their lines are added to the list.
- Packages whose platform condition does not match are dropped.

pipInstall2 needs the Python `packaging` module to read package descriptions. If the system Python does not have it, it is installed into the venv and used from there.

### 3. Decide what needs installing

Each package is checked against what is already available:

| Situation | Action |
| --- | --- |
| Part of Python itself (`sys`, `os` ...) | Ignored |
| Already installed, no version condition | Skipped (not upgraded) |
| Already installed at a version that meets the condition | Skipped |
| Installed at a version that does not meet the condition, or the version cannot be determined | Installed |
| Not installed | Installed - the latest version, or the latest version that meets the condition |
| Marked with `!` | Installed in the venv, whatever is already installed |

### 4. Install

0. **Packages marked `!` first.** They are installed with `pip install --ignore-installed --no-deps` (dry run, then all together, falling back to one at a time). Only the marked packages are installed in this step. Their dependencies are installed in the next steps, together with everything else. A marked package that fails here is reported as failed and left out of the next steps, so a system copy is not used in its place.
1. **Dry run.** pip is asked what it would install for all the remaining packages together (`pip install --dry-run`). The log lists each package and version that will be installed, marked as `requested` or `dependency`.
2. **Install everything together.** A single `pip install -r` installs all the packages at once, so pip chooses versions that work together.
3. **Fall back to one at a time.** If the dry run or the combined install fails (e.g. one package does not exist), each package is installed separately. The packages that can be installed still are, and each failure is logged with pip's error message.

### 5. Report

A summary lists the packages that were ignored, skipped, installed (with old and new versions) and failed. pipInstall2 then exits with one of the codes below.

### Overriding a system package

Because the venv can see the system's packages, a package that is already installed on the system (e.g. with `apt`) is normally used as it is. Mark a package with `!` when the plugin must have its own copy instead.

Example: on Raspberry Pi OS Bookworm, `apt` installs `python3-picamera2` with numpy 1.x, and its compiled helpers (`simplejpeg`, `pidng`, `av`) are built against numpy 1.x. A plugin that also needs numpy 2 (e.g. through `opencv-python`) gets numpy 2 in its venv, but `import picamera2` then fails with `numpy.dtype size changed, may indicate binary incompatibility`. Marking the camera packages installs venv copies built for numpy 2:

```text
opencv-python
!picamera2==0.3.31   # pin to the version apt has - it still uses apt's libcamera
!simplejpeg
!pidng
!av
```

- List **every** package that has to come from the venv. Marking only `picamera2` leaves apt's `simplejpeg` in use. pipInstall2 cannot tell which system packages were built against numpy 1.
- The system copies are not changed, so the system Python and other plugins are not affected.
- Packages that must be compiled need their build tools on the system. pip's `picamera2` needs `python-prctl`, which needs `libcap-dev`. Add such packages to `sbcPackageDependencies`.
- `!` is a pipInstall2 feature. A requirements file using it cannot be passed to `pip install -r` directly.

## Logging and files

Log output goes to the console (and so to `journalctl` when run by DSF) and to `<plugin path>/venv/pipInstall2.log`. If the log file cannot be created there, it is created in the current folder instead.

pipInstall2 also leaves these files in `<plugin path>/venv`:

| File | Purpose |
| --- | --- |
| `pipInstall2.log` | Log of the last run |
| `pipInstall_requirements.txt` | The combined list of packages that was passed to pip |
| `pipInstall_report.json` | pip's dry-run report: everything pip planned to install, including dependencies |
| `pipInstall_venv_only_requirements.txt`, `pipInstall_venv_only_report.json` | The same, for packages marked `!` (only present if any were marked) |
| `import_test.py` | Helper used to check whether a module is already installed |

## Usage

```bash
pipInstall2.py -m <manifest file> -p <plugin path>
```

Both paths should be fully qualified. DSF supplies these when it installs a plugin.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All packages installed or sensibly handled |
| 1 | No manifest file (`-m`) was provided |
| 2 | Manifest file does not exist |
| 3 | No plugin path (`-p`) was provided |
| 4 | Plugin path does not exist |
| 6 | Problem creating the virtual environment |
| 7 | Manifest is not a properly formatted json file |
| 8 | `pip freeze` failed |
| 9 | Unexpected error |
| 10 | One or more packages failed to install |
| 11 | Invalid package entry (could not be understood) |
| 12 | Could not get site-packages information from the venv |
| 13 | Requirements file not found in `<plugin path>/dsf` |
| 14 | The Python `packaging` module is not available and could not be installed into the venv |

## Installing pipInstall2 in DSF

Tested with DSF 3.7.x.

```bash
sudo cp pipInstall2.py /opt/dsf/bin/pipInstall2.py
sudo chmod 744 /opt/dsf/bin/pipInstall2.py
sudo chown dsf:dsf /opt/dsf/bin/pipInstall2.py
```

The following entry is expected in `/opt/dsf/conf/plugins.json`:

```text
"InstallPythonPackageCommand": "/opt/dsf/bin/pipInstall2.py",
```

Python scripts in DSF plugins do not need a shebang line, provided the calling program runs them with a fully qualified path. If the plugin is itself a Python script, the plugin manager does this.

## Reference: version numbers and version conditions

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
