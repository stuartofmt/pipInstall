# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

Verson:
1.0.0
Initial Release by Stuart Strolin

Version 1.1.0 - Modified by Andy at Duet3d

Version 1.1.1 - Modified by Stuart Strolin
- Fixed issue handling modules with no version number e.g shlex

Version 1.1.2 - Modified by Stuart Strolin
- Added flags so venv has upgraded pip and is cleared each time
- changed pip list to pip freeze to get version numbers
- added --force-reinstall to pip install command as a safety measure
- added quotes around module name in pip install to avoid redirects e.g. module>2
- added logfile
- added --verbose flag - first (dummy) entry in manifest file 'sbcPythonDependencies'
- replaced pkg_resources (deprecated) version parsing with packaging.version

Version 2.0.0 - Modified by Stuart Strolin
- Restructured for ease of maintenance
- Conditionally import version from packaging.version for python 3.13 and above
- logfile location is ./venv for the plugin with fallback to cwd (for testing)
- logfile name is pipInstall2.log
- added .pth and .py file to ensure site-packages is at front of sys.path
- externalize function to get updated module version from venv after install
- improved logging messages
- modules can be specified as one of more txt file(s) (e.g requirements.txt) in plugin.json
- requirements files need to be \located in the dsf folder (i.e. same folder as python files)
- supports modules from git e.g. git+https://github.com/pallets/flask.git

Version 2.0.1 - Modified by Stuart Strolin
- Added defensive code for unexpected error in output from import test script

Version 2.0.2 - Modified by Stuart Strolin
- Added support for extras in module names (use of square brackets) e.g. package[standard]

Version 2.0.3 - Modified by Stuart Strolin
Added support for period in name e.g. keyrings.alt
Added support for space in name and --user argument  e.g. --user dsf-python

Version 2.1.0 - Modified by Stuart Strolin
- Added support for control arguments e.g. --user in e.g. --user dsf-python
- Changed version determination to give better insight

Version 2.1.1 - Modified by Stuart Strolin
- changed logger to initially output to console
- then after arguments passed add logfile

Version 2.1.2 - Modified by Stuart Strolin
- Added support for PEP 508 environment markers e.g. `picamera2; sys_platform == "linux"`
- modules whose marker does not apply to the current platform are skipped
- applies to entries in plugin.json and in requirements files

Version 2.3.0 - Modified by Stuart Strolin
- Added support for version ranges and all PEP 440 comparisons e.g. `numpy>=1.2,<2.0`  `numpy!=1.3`  `numpy==1.*`
- spaces are allowed around comparisons e.g. `numpy >= 1.2`
- `~=` is no longer converted to `>=` (pip handles it correctly)
- module parsing now uses packaging.requirements instead of a custom regex
- modules already installed at a version that meets the condition are skipped instead of reinstalled

Version 2.3.1 - Modified by Stuart Strolin
- Trailing comments are ignored e.g. `numpy==1.26  # needed for X`
- a `#` is treated as a comment when at the start or preceded by whitespace (same rule as pip)
- applies to entries in plugin.json (including --verbose) and in requirements files

Version 2.3.2 - Modified by Stuart Strolin
- pip --dry-run (with --report) logs what will actually be installed, including dependencies
- modules are installed together with a single `pip install -r` so pip resolves them consistently
- if that fails, falls back to installing one module at a time and reports each failure with pip's error
- removed `--force-reinstall` and `--no-cache-dir` (dependencies were reinstalled and re-downloaded every time)
- already installed modules with no version requested are no longer upgraded (rule 2 now applies to pip modules too)

Version 2.3.3 - Modified by Stuart Strolin
- argument errors now exit with their exit codes (previously crashed with IndexError / NameError)
- the venv python no longer prints the site-packages path every time it starts
- a requirements file (.txt) that is not found in `<plugin Path>/dsf` now exits with code 13 (previously it was treated as a module name and looked up on PyPI)
- if the `packaging` module is not available in the system python it is installed into the venv and used from there - exits with code 14 if that fails
- `--user` is now ignored (with a warning) - all modules are installed in the plugin venv (previously they were installed in the user site-packages, outside the venv)
- removed pkg_resources import (deprecated and unused)
- a failed install is no longer reported as succeeded for modules that import without version information
- removed unused code
- log file lines are no longer wrapped in quotes


Useage:
Usage pipInstall -m `<manifesr name>` -p `< plugin path >`

Both `<manifest name>` and `<plugin path>` are fully qualified

A virtual environment will be created for python at
`<plugin Path>`/venv

A version condition can be supplied using any standard (PEP 440) comparison:
`==` `!=` `>=` `<=` `>` `<` `~=` `===`

Several conditions can be combined with commas, and spaces are allowed e.g.

```
numpy>=1.2,<2.0
pkg[extra] >= 1, != 1.3
numpy==1.*
```

Rules:
1. If module is built-in it will be ignored
2. If module is already installed and no version is requested it will be ignored (it is not upgraded)
3. If module is not installed it will be installed
	3a. If no version - it will be installed at the latest version
	3b. If version is requested it will be installed at a version that meets the condition
	3c. If module is already installed at a version that meets the condition it will be ignored.
	If the installed version does not meet the condition (or cannot be determined) it will be installed

4. Installed modules will be placed in site-packages of the virtual environment
5. site-packages will be placed at the front of sys.path when the venv python interpreter is used
therefore installed modules will take precedence over system modules

Install steps:

1. `pip install --dry-run --report` of all modules that need installing. This logs what will actually be installed, including dependencies. The report is kept at `<plugin Path>/venv/pipInstall_report.json`
2. a single `pip install -r` of all of them, so pip resolves them together (consistent versions)
3. if 1 or 2 fails, the modules are installed one at a time so the others still install, and each failure is reported with pip's error message

`--user` is ignored (with a warning) - all modules are installed in the plugin venv

Environment markers:

A module can be made platform dependent by adding a standard (PEP 508) environment marker after a `;`
This works for modules listed directly in plugin.json and for lines in requirements files e.g.

```
picamera2; sys_platform == "linux"
pygrabber==0.2; sys_platform == "win32"
```

The marker is evaluated on the machine pipInstall is running on.
If it matches, the module is processed as normal (using the part before the `;`).
If it does not match, the module is skipped.
If the marker cannot be evaluated a warning is logged and the module is installed anyway.
Any standard marker can be used e.g. `platform_machine == "aarch64"` or `python_version >= "3.11"`

Comments:

Anything from a `#` that is at the start of an entry, or preceded by whitespace, to the end of the entry is ignored.
This works for modules listed directly in plugin.json and for lines in requirements files e.g.

```
numpy==1.26  # needed for X
picamera2; sys_platform == "linux"  # camera support
# this whole entry is ignored
```

A `#` with no whitespace before it is kept e.g. `git+https://github.com/x/y.git#egg=y`

logging is sent to journalctl as well as a log file `<plugin Path>`/venv/pipInstall2.log

A special, dummy module "--verbose" can be included in plugin.json --> as the VERY FIRST module.  This enables verbose logging (see example in file verbose_test.json)

Return Codes:

0 - All modules successfully installed or sensibly handled.

Other than 0 --> Something nasty happened or one or more modules failed to install.
Usually this will be because pip could not handle the install request.

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | No manifest file (-m) was provided |
| 2 | Manifest file does not exist |
| 3 | No plugin path (-p) was provided |
| 4 | Plugin path does not exist |
| 6 | Problem creating the virtual environment |
| 7 | Manifest is not a properly formatted json file |
| 8 | pip freeze failed |
| 9 | Unexpected error |
| 10 | One or more modules failed to install |
| 11 | Invalid module entry (could not be parsed) |
| 12 | Could not get site-packages information from the venv |
| 13 | Requirements file not found in `<plugin Path>/dsf` |
| 14 | The python `packaging` module is not available and could not be installed into the venv |

##  Note: python scripts in Duet3d plugins DO NOT need to have a shebang
Provided the calling program does so with a fully qualified path. If the plugin is itself a python script - this is done by the plugin manager. 

## Tested in the following DSF environment
DSF 3.6.x

Installed as:

/opt/dsf/bin/pipInstall2.py

with

sudo chmod 744 /opt/dsf/bin/pipInstall2.py

sudo chown dsf:dsf /opt/dsf/bin/pipInstall2.py

The following entry is expected in `/opt/dfs/conf/plugins.json`

  ```
  "InstallPythonPackageCommand": "/opt/dsf/bin/pipInstall2.py",
  ```
