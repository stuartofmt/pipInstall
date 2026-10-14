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


Useage:
Usage pipInstall -m `<manifesr name>` -p `< plugin path >`

Both `<manifest name>` and `<plugin path>` are fully qualified

A virtual environment will be created for python at
`<plugin Path>`/venv

If version number is supplied it must use one of the following comparisons:
`==`
`>=`
`<=`
`>`
`<`
`~=    Note ~= will be converted to >=`

Rules:
1. If module is built-in it will be ignored
2. If module is already installed and no version is requested it will be ignored
3. If module is not installed it will be installed
	3a. If no version - it will be installed at the latest version
	3b. If version is requested it will be installed at that version

4. Installed modules will be placed in site-packages of the virtual environment
5. site-packages will be placed at the front of sys.path when the venv python interpreter is used
therefore installed modules will take precedence over system modules

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

logging is sent to journalctl as well as a log file `<plugin Path>`/venv/pipInstall2.log

A special, dummy module "--verbose" can be included in plugin.json --> as the VERY FIRST module.  This enables verbose logging (see example in file verbose_test.json)

Return Codes:

0 - All modules successfully installed or sensibly handled.

Other than 0 --> Something nasty happened or one or more modules failed to install (see code for explicit values).
Usually this will be because pip could not handle the install request.

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
