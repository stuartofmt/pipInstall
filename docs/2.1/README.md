# pipInstall2 - Python package installer for DSF plugins

pipInstall2 installs the Python packages a DSF plugin needs on the SBC. Each plugin gets its own Python virtual environment (venv).

This is the documentation for pipInstall2 2.1.0, for DSF 3.6 and 3.7 ([other versions](../../Readme.md#versions)). For what changed in this version see [change-notes.md](change-notes.md).

DSF calls pipInstall2 when a plugin is installed, passing it the plugin's `plugin.json` and the plugin's folder. The packages to install come from the `sbcPythonDependencies` entry in `plugin.json`.

## Listing packages

Packages can be listed directly in `sbcPythonDependencies`, or in one or more requirements files:

```json
"sbcPythonDependencies": ["requests", "requirements.txt"]
```

- An entry ending in `.txt` that exists in `<plugin path>/dsf/` (the same folder as the plugin's python files) is read as a requirements file, one package per line. If the file does not exist, the entry is treated as a package name.
- In a requirements file, blank lines and lines starting with `#` are ignored.

## Package descriptions

| Example | Meaning |
| --- | --- |
| `requests` | Plain package name |
| `keyrings.alt` | Names may contain `.` |
| `uvicorn[standard]` | Extras in square brackets |
| `--user dsf-python` | Install with pip's `--user` option |
| `git+https://github.com/pallets/flask.git` | Install from a git repository |
| `numpy==1.26.4` | With a version condition (see below) |

### Version conditions

A version condition must use one of these comparisons:

| Comparison | Note |
| --- | --- |
| `==` | |
| `>=` | |
| `<=` | |
| `>` | |
| `<` | |
| `~=` | Converted to `>=` |

Only one condition is allowed per package. Ranges such as `numpy>=1.2,<2.0` are not supported: an entry containing a `,` stops pipInstall2 with exit code 5.

## What pipInstall2 does

1. **Creates the venv** at `<plugin path>/venv`. It is recreated from scratch each time, with pip upgraded, and can see the system's Python packages.
2. **Reads the package list** from `sbcPythonDependencies` and any requirements files.
3. **Installs each package in turn**, following these rules:
   1. If the module is built-in it is ignored.
   2. If the module is already installed and no version is requested it is ignored.
   3. If the module is not installed it is installed: at the latest version if no version is requested, or at the requested version.
4. **Reports** the packages that were ignored, skipped, installed and failed.

Packages are installed one at a time with `pip install --force-reinstall --no-cache-dir`, plus `--upgrade` when no version is requested.

A `.pth` file in the venv puts the venv's site-packages at the front of `sys.path` whenever the venv's Python starts, so installed modules take precedence over system modules.

## Logging

Log output goes to `journalctl` and to `<plugin path>/venv/pipInstall2.log`.

For more detail, add `--verbose` as the **very first** entry in `sbcPythonDependencies`:

```json
"sbcPythonDependencies": ["--verbose", "requirements.txt"]
```

## Usage

```bash
pipInstall2.py -m <manifest file> -p <plugin path>
```

Both paths should be fully qualified. DSF supplies these when it installs a plugin.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All modules installed or sensibly handled |
| 1 | No manifest file (`-m`) was provided |
| 2 | Manifest file does not exist |
| 3 | No plugin path (`-p`) was provided |
| 4 | Plugin path does not exist |
| 5 | Unsupported condition (e.g. a version range containing `,`) |
| 6 | Problem creating the virtual environment |
| 7 | Manifest is not a properly formatted json file |
| 8 | `pip freeze` failed |
| 9 | Unexpected error |
| 10 | One or more modules failed to install |
| 11 | Invalid package entry |
| 12 | Could not get site-packages information from the venv |

## Installing in DSF

Tested with DSF 3.6.x.

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
