# Python3 package installer for DSF

A python script to install python package dependencies for DSF plugins.

Reports success on built-in modules.

Provides logic to (hopefully) avoid version conflicts due to different plugin requirements by installing the latest versions.

Uses pip3 (expected to be on path) and accepts pip3 version requests.

Useage:
Usage pip3_installer `<module name>`

Expects a single module name with or without a version number condition.
If a version number condition is supplied it must use one of the following forms
`==` , `>=` , `<=` , `~=`

Note `~=` will be converted to `>=`.  Multiple conditionals as well as `>` and `<` are not supported.

Inbuild modules are checked and reported as successfully installed.

Logical rules are applied as follows:

Rule 1:  If requested version is > current version, install requested version.

Rule 2:  If requested version < current version, do nothing.

Logging is sent to journalctl with various messages indicating what was actually done.

Return Codes:

0 - Successfully installed or already installed.  Log provides details.

1 = Something nasty happened.

64 - No module was specified.

65 - Only one module can be specified.

66 - Unsupported Conditional.

67 - Pip3 could not handle the request.

Logging is sent to journalctl with various messages indicating what was actually done.

## Tested in the following DSF environment using DSF 3.5.3

Installed as:

/opt/dsf/bin/pip3_install.py

with

sudo chmod 744 /opt/dsf/bin/pip3_install.py

sudo chown dsf:dsf /opt/dsf/bin/pip3_install.py

The following entries are expected in `/opt/dfs/conf/plugins.json`

  ```
  "InstallPythonPackageCommand": "/opt/dsf/bin/pip3_install.py",
  "InstallPythonPackageArguments": "{package}",
  ```
