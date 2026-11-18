# pipInstall2 - Python package installer for DSF plugins

pipInstall2 is a front-end for python pip that simplifies the installation of Python packages used with a DSF plugin.

Each plugin gets its own Python virtual environment (venv), so packages for one plugin cannot break another plugin or the system Python.

DSF calls pipInstall2 when a plugin is installed, passing it the plugin's `plugin.json` and the plugin's folder. The packages to install come from the `sbcPythonDependencies` entry in `plugin.json`.

This page covers the usual case: a list of packages, with or without versions. For everything else see [Special Cases](#special-cases).

For changes between versions see [release-notes.md](release-notes.md).

## List packages in a requirements file

The preferred way to declare packages is to put **one or more requirements files** in `sbcPythonDependencies`, rather than a long list of packages directly in `plugin.json`.

**`sbcPythonDependencies` - Several files can be listed, e.g. `["requirements.txt", "camera.txt"]`, and packages can be listed directly in plugin.json alongside them if needed.**

`plugin.json`:

```json
"sbcPythonDependencies": ["requirements.txt"]
```

`dsf/requirements.txt` (in the same folder as the plugin's python files):

```text
# Web server
uvicorn[standard] >= 0.35.0
requests

numpy >= 1.24, < 3      # 2.x tested
```

Why a requirements file is better:

- **Standard format.** It is the same file format pip uses, so the same file can be tested by hand with `pip install -r requirements.txt`.
- **Easier to read and maintain.** One package per line, with room for comments explaining why each package and version is needed. JSON does not allow comments.
- **Shorter plugin.json.** The manifest stays focused on the plugin itself.

Rules for requirements files:

- An entry in `sbcPythonDependencies` that ends in `.txt` is treated as a requirements file.
- The file is looked for in `<plugin path>/dsf/`. A subfolder can be given e.g. `extras/camera.txt`.
- If the file is not found, pipInstall2 stops with exit code 13. So does an entry that looks like a mistyped file name, e.g. `requirements.txt1`, instead of it being looked up on PyPI as a package.
- Requirements files cannot include other requirements files. Only `.txt` entries in plugin.json are expanded.

## Describing packages

The same package descriptions work in a requirements file and directly in `sbcPythonDependencies`.

### Package names

| Example | Meaning |
| --- | --- |
| `requests` | Plain package name |
| `PyGithub` | Names are not case sensitive |
| `keyrings.alt`, `dsf-python`, `dsf_python` | Names may contain `.`, `-` and `_` |
| `uvicorn[standard]`, `pkg[extra1,extra2]` | Extras (optional features of a package) in square brackets |

Modules that are part of Python itself (`sys`, `os`, `json`, `shlex` ...) are recognised and ignored. They do not need to be listed.

### Version conditions

Any standard (PEP 440) comparison can follow the name. Spaces around comparisons are allowed.

| Example | Meaning |
| --- | --- |
| `numpy==1.26.4` | Exactly this version |
| `numpy==1.*` | Any 1.x version |
| `numpy!=1.25.0` | Any version except this one |
| `numpy>=1.24`, `numpy>1.24` | At least / greater than |
| `numpy<=2.0`, `numpy<2` | At most / less than |
| `numpy~=1.26.0` | Compatible release: `>=1.26.0, <1.27` |
| `numpy>=1.24,<3` | A range: several conditions separated by commas |
| `pkg[extra] >= 1, != 1.3` | Extras, spaces and several conditions together |

How betas, release candidates and post-releases are treated is explained in [special_cases.md](special_cases.md#version-numbers-pre-releases-and-post-releases).

### Comments

Anything from a `#` that starts an entry, or that has a space or tab before it, to the end of the line is ignored:

```text
# this whole line is ignored
numpy==1.26  # needed for X
```

Comments also work in `sbcPythonDependencies`, e.g. `"requirements.txt  # main packages"`. An entry that is only a comment is ignored.

## What pipInstall2 does

### 1. Create the virtual environment

The venv is created at `<plugin path>/venv`:

- It is recreated from scratch every time pipInstall2 runs.
- pip in the venv is upgraded to the latest version.
- The venv can see the system's Python packages (e.g. packages installed with `apt`). Packages installed in the venv take priority over system packages with the same name.

### 2. Read the package list

- `sbcPythonDependencies` is read from `plugin.json`.
- The entries and the lines of any requirements files are combined into one list, and comments and blank lines are removed.
- Each entry is checked and tidied (e.g. extra spaces removed). An entry that cannot be understood stops pipInstall2 with exit code 11.
- The combined list is shown in the log.

### 3. Decide what needs installing

Each package is checked against what is already available, including the system's packages:

| Situation | Action |
| --- | --- |
| Part of Python itself (`sys`, `os` ...) | Ignored |
| Already installed, no version condition | Skipped (not upgraded) |
| Already installed at a version that meets the condition | Skipped |
| Installed at a version that does not meet the condition, or the version cannot be determined | Installed |
| Not installed | Installed - the latest version, or the latest version that meets the condition |

### 4. Install packages

1. **Dry run.** pip is asked what it would install for all the packages together (`pip install --dry-run`). The log lists each package and version that will be installed, marked as `requested` or `dependency`. Packages that have no ready-built wheel for the system are marked `will be built from source`, and are listed again with a warning that building can take a long time. pipInstall2 then checks for the basic build tools (C and C++ compilers, Python headers, pkg-config), logs any that are missing and the `apt` command to install them. The install carries on either way. Some packages need other tools or libraries as well; these cannot be checked, so see the package's own install documentation.
2. **Try to install everything together.** A single `pip install -r` tries to install all the packages at once, so pip chooses versions that work together.
3. **Fall back to one at a time.** If the dry run or the combined install fails (e.g. one package does not exist), each package is then tried separately, so that the log shows which packages succeed and which fail, each failure with pip's error message. Before each package is installed, a dry run of just that package is made, so a package that will be built from source is reported (with the build tools check) before the build starts. **If any package fails, the install as a whole fails** (exit code 10). The packages that did install are left in the venv, but the plugin's dependencies are incomplete. The venv is rebuilt from scratch the next time pipInstall2 runs.

pip is run with `--prefer-binary`: where the newest version that meets the condition is only available as source code, pip installs the newest version that has a ready-built wheel instead. Building from source on a Pi is slow and needs build tools (a C compiler, Python headers, and sometimes other libraries) that are often not installed. A package that has no wheel for any suitable version is still built from source.

### 5. Check the packages work together

`pip check` is run to find installed packages whose own requirements are not met, e.g. a package that needs `numpy>=2` when `numpy<2` was requested. This matters most after the one-at-a-time fallback, where each package is installed without regard to the others. Only problems involving the plugin's packages count: packages it requested, packages installed in its venv, and system packages that need a different version of a package installed in the venv. Problems only between system packages are logged with `--verbose` and otherwise ignored.

### 6. Report

A summary lists the packages that were ignored, skipped, installed (with old and new versions) and failed (with pip's reason), followed by any packages that are not compatible with each other. Packages that were already available are shown as installed in the venv or found in the system packages. pipInstall2 then exits with one of the [exit codes](#exit-codes): 0 only if every package was installed or did not need installing and they work together, 10 if any package failed, 16 if the installed packages are not compatible with each other.

## Logging and files

Log output goes to the console (and so to `journalctl` when run by DSF) and to `<plugin path>/venv/pipInstall2.log`. If the log file cannot be created there, it is created in the current folder instead. For more detail in the log, see [`--verbose`](special_cases.md#special-entries).

pipInstall2 also leaves these files in `<plugin path>/venv`:

| File | Purpose |
| --- | --- |
| `pipInstall2.log` | Log of the last run |
| `pipInstall_requirements.txt` | The combined list of packages that was passed to pip |
| `pipInstall_report.json` | pip's dry-run report: everything pip planned to install, including dependencies |
| `import_test.py` | Helper used to check whether a module is already installed |

## Special Cases

- [Special entries](special_cases.md#special-entries) - `--verbose`, `--python`, `--user`
- [Platform conditions](special_cases.md#platform-conditions-environment-markers) - packages for some systems only, e.g. `picamera2; sys_platform == "linux"`
- [Installing from a git repository](special_cases.md#installing-from-a-git-repository)
- [Requiring a Python version](special_cases.md#requiring-a-python-version)
- [How entries are corrected](special_cases.md#how-entries-are-corrected)
- [Not supported](special_cases.md#not-supported)
- [Version numbers: pre-releases and post-releases](special_cases.md#version-numbers-pre-releases-and-post-releases)

## Installation Notes

### Installing in DSF

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

### Usage

```bash
pipInstall2.py -m <manifest file> -p <plugin path>
```

Both paths should be fully qualified. DSF supplies these when it installs a plugin.

### Exit codes

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
| 13 | Requirements file not found in `<plugin path>/dsf`, or an entry looks like a mistyped requirements file name (e.g. `requirements.txt1`) |
| 14 | The Python `packaging` module is not available and could not be installed into the venv |
| 15 | The system's Python version does not meet the plugin's [`--python`](special_cases.md#requiring-a-python-version) condition |
| 16 | The installed packages are not compatible with each other (found by `pip check`) |
