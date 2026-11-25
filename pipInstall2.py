#!/usr/bin/env python3

"""
Install python modules and create a virtual environment for the plugin.

# Copyright (C) 2023 Stuart Strolin all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT

Usage:
pipInstall2.py -m <manifest file> -p <plugin path>

Both <manifest file> and <plugin path> are fully qualified

A virtual environment will be created for python at
<plugin Path>/VENV_FOLDER   (see constant section)

"""


import shlex
import shutil
import subprocess
import sys
import logging
import logging.handlers

import re
import os
import argparse
import importlib
import json
import platform
import tempfile
import functools

from enum import Enum
from typing import Optional


# CONSTANTS
THIS_VERSION = '2.4.1'
VENV_FOLDER = 'venv'
MANIFEST_KEY = 'sbcPythonDependencies'
NAME_KEY = 'name'
PIP = 'pip'
LOGNAME = 'pipInstall2.log'
FALLBACK_LOGFILENAME = os.path.normpath(os.path.join(os.getcwd(), LOGNAME))
IMPORTTESTFILE = 'import_test.py'  # written by earlier versions - removed if found
FINDTIMEOUT = 10  # seconds - a module search that takes longer is treated as not installed (a dotted name imports its parent package)
REQFILENAME = 'pipInstall_requirements.txt'  # combined requirements written to the venv folder
REPORTFILENAME = 'pipInstall_report.json'  # pip --dry-run report written to the venv folder
PYTHONREQ = '--python'  # e.g. --python>=3.11 - required python version for the plugin
CLEARVENV = '--clear'  # entry that forces the venv to be rebuilt from scratch
KEEPINVENV = {'pip', 'setuptools', 'wheel'}  # never removed from the venv as unused
pipQuiet = '-qq'  # Reduce pip output
PIPPREFERBINARY = '--prefer-binary'  # Prefer the newest version with a wheel over building a newer version from source
PIPRETRIES = '1'  # PIP_RETRIES for every pip run: one retry (pip's default is 5) - without a network pip gives up in seconds, not tens of seconds
buildToolsChecked = False  # The build tools are only checked (and logged) once
packagingInVenv = False  # True if packaging was installed in the venv for pipInstall2's own use
logFiles = None  # (log file, fallback log file) - set once the paths are known
runCache = None  # this run's pip cache folder (in the venv folder) - deleted when pipInstall2 exits
modulePackages = {}  # import name -> PyPI package name, for modules found by the module search
COMMENT_RE = re.compile(r'(^|\s)#.*$')  # '#' at start or preceded by whitespace (pip rule)
# A pip option at the start of an entry or after a space e.g. -r x.txt, --pre, numpy --hash=sha256:...
PIPOPTION_RE = re.compile(r'(?:^|\s)(--?[A-Za-z][A-Za-z0-9-]*)')
INDEXOPTIONS = ('-i', '--index-url', '--extra-index-url', '--no-index', '-f', '--find-links', '--trusted-host')
# git+ url forms allowed (not http - unencrypted), limited to the characters a url needs (no spaces, quotes, $, ` \ ; | < >)
GIT_URL_RE = re.compile(r'git\+(https|ssh|file)://[A-Za-z0-9._~:/?#\[\]@!&+,=%-]+')
PASSWORD_RE = re.compile(r'(://[^/@\s:]+):[^/@\s]+@')  # user:password@ in a url - hidden in the log
TOKEN_RE = re.compile(r'(https?://)[^/@\s:]+@')  # token@ in an https url (e.g. GitHub) - hidden in the log; ssh://git@ is only a user name

if os.name == 'nt':  # Windows
    BIN_DIR = 'Scripts'
    PYTHON_VERSION = 'python.exe'
else:
    BIN_DIR = 'bin'  # Linux
    PYTHON_VERSION = 'python'
# The python running pipInstall2 creates the venv, so the venv, the packaging check and the reuse check all use the same python
SYSTEM_PYTHON = sys.executable or PYTHON_VERSION


class ExitCodes(Enum):
    SUCCESS = 0
    NO_MANIFEST_PROVIDED = 1
    MANIFEST_DOES_NOT_EXIST = 2
    NO_PLUGIN_PROVIDED = 3
    PLUGIN_DOES_NOT_EXIST = 4
    PROBLEM_CREATING_VENV = 6
    MANIFEST_ERROR = 7
    PIP_LIST_ERROR = 8
    UNEXPECTED_ERROR = 9
    FAILED_TO_INSTALL_MODULE = 10
    INVALID_DEPENDENCY = 11
    PYTHON_SITE_ERROR = 12
    REQUIREMENTS_FILE_NOT_FOUND = 13
    PACKAGING_NOT_AVAILABLE = 14
    PYTHON_VERSION_NOT_SUPPORTED = 15
    DEPENDENCY_CONFLICT = 16


class modType(Enum):
    BUILTIN = 'Builtin'
    INSTALLEDWITHVERSION = 'already Installed with version'
    INSTALLEDNOVERSION = 'already installed with no version number'
    PIPWITHVERSION = 'installed in the venv with version'
    SYSTEMWITHVERSION = 'found in the system packages with version'
    NOTINSTALLED = 'not previously installed'


class Dependency:
    # Parsing uses packaging.requirements (PEP 508) so names, extras and version
    # conditions (including ranges e.g. >=1.2,<2.0) follow the same rules as pip
    # git+ urls are handled separately

    def __init__(self) -> None:
        self.package: str = None
        self.version: str = None
        self.comparator: str = None

    @classmethod
    def parse(cls, text: str) -> Optional['Dependency']:
        """Convert text from sbcPythonDependencies (or a requirements file) into object
        Args:
            text (str): line from sbcPythonDependencies
        """
        from packaging.requirements import Requirement

        text = text.strip()
        dep = Dependency()

        if text.startswith('git+'):
            # Git dependency
            dep.package = text
            dep.comparator = None
            dep.version = None
            return dep

        # text has already been checked by normaliseRequirement, so it is a valid requirement
        req = Requirement(text)

        # Standard PyPi dependency
        extras = f'[{",".join(sorted(req.extras))}]' if req.extras else ''
        dep.package = req.name + extras
        dep.comparator = str(req.specifier)  # e.g. '>=1.2,<2.0' or '' if none
        dep.version = ''  # full condition is held in comparator

        return dep


def findSitePackages(pythonFile, envPath):
    """
    Finds and returns the venv site-packages path (where pip installs packages), asked from the venv python
    Stops (PYTHON_SITE_ERROR) if it is not a folder inside the venv
    """
    ok, out, err = runPip([pythonFile, '-c', "import sysconfig; print(sysconfig.get_path('purelib'))"])
    sitePackagesPath = out.strip() if ok else ''
    real, venv = os.path.realpath(sitePackagesPath or os.sep), os.path.realpath(envPath)
    if not sitePackagesPath or not os.path.isdir(real) or os.path.commonpath([venv, real]) != venv:
        logger.critical(f'Aborting: could not find the venv site-packages folder ({sitePackagesPath or "none"})\n{err.strip()}')
        shutDown(ExitCodes.PYTHON_SITE_ERROR)
    logger.debug(f'Found site-packages at: {sitePackagesPath}')
    return sitePackagesPath


def removeOldFiles(venvPath, sitePackagesPath):
    """
    Files earlier versions of pipInstall2 wrote. The venv used to be rebuilt every run, so they were removed;
    now an existing venv is kept, so remove them from a venv last built by one of those versions
    - plugin_path_change.pth / .py in site-packages (before 2.4.0): a hook that put the venv's packages ahead of the standard library
    - import_test.py in site-packages (or the venv folder): modules are now looked for with python -c (FIND_SCRIPT)
    """
    old = [os.path.join(sitePackagesPath, name) for name in ('plugin_path_change.pth', 'plugin_path_change.py', IMPORTTESTFILE)]
    for file in old + [os.path.join(venvPath, IMPORTTESTFILE)]:
        if os.path.isfile(file):
            try:
                os.remove(file)
                logger.debug(f'Removed {file} (left by an earlier version of pipInstall2)')
            except OSError as e:
                logger.warning(f'Could not remove {file}: {e}')


def hidePasswords(record):
    # Logging filter - a url with user:password@ or token@ (e.g. a private git repository) is logged as user:***@ / ***@
    record.msg = TOKEN_RE.sub(r'\1***@', PASSWORD_RE.sub(r'\1:***@', str(record.msg)))
    return True


def createLogger(progname):  # Create a custom logger so messages go to journalctl
    global logger
    logger = logging.getLogger(progname)
    logger.propagate = False
    logger.addFilter(hidePasswords)
    # Create handler for console output
    c_handler = logging.StreamHandler()
    c_format = logging.Formatter('%(message)s')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)
    # Keep messages until the log file is created (the venv, where the log file goes, is created after the manifest is read)
    logger.addHandler(logging.handlers.MemoryHandler(capacity=100000, flushLevel=logging.CRITICAL + 1, target=None))
    logger.setLevel(logging.INFO)  # Initial Setting


def removeLink(path):
    # A file pipInstall2 writes must not be a symbolic link - writing would change the file it points to
    if os.path.islink(path):
        os.remove(path)


def createLogfile(logfilename, fallback_logfilename):
    try:
        removeLink(logfilename)
        f_handler = logging.FileHandler(logfilename, mode='w', encoding='utf-8')
    except Exception:  # Could be permission issue etc
        try:
            removeLink(fallback_logfilename)
            f_handler = logging.FileHandler(fallback_logfilename, mode='w', encoding='utf-8')
            logfilename = fallback_logfilename
        except Exception as e:
            logger.warning(f'Could not create a log file: {e}')
            return

    f_format = logging.Formatter('%(message)s')
    f_handler.setFormatter(f_format)
    # Write the messages logged before the log file existed
    for handler in list(logger.handlers):
        if isinstance(handler, logging.handlers.MemoryHandler):
            handler.setTarget(f_handler)
            handler.flush()
            logger.removeHandler(handler)
            handler.close()
    logger.addHandler(f_handler)
    logger.info(f'Log file created at:\n{logfilename}')


def validateParams():
    parser = argparse.ArgumentParser(
        description='pipInstall2')
    # Environment
    parser.add_argument('-m', type=str, nargs=1, default=[None],
                        help='manifest file')
    parser.add_argument('-p', type=str, nargs=1, default=[None], help='plugin path')

    args = vars(parser.parse_args())  # Save as a dict

    mFile = args['m'][0]
    pPath = args['p'][0]

    if mFile is None:
        print('Exiting: No manifest file (-m) was provided')
        shutDown(ExitCodes.NO_MANIFEST_PROVIDED)
    elif not os.path.isfile(mFile):
        print(f'Exiting: Manifest file "{mFile}" does not exist')
        shutDown(ExitCodes.MANIFEST_DOES_NOT_EXIST)

    if pPath is None:
        print('Exiting: No plugin path (-p) was provided')
        shutDown(ExitCodes.NO_PLUGIN_PROVIDED)
    elif not os.path.isdir(pPath):
        print(f'Exiting: Plugin path "{pPath}" does not exist')
        shutDown(ExitCodes.PLUGIN_DOES_NOT_EXIST)

    return mFile, pPath


def parseVersion(request) -> Dependency:
    # Get the module name and any conditional and version

    dep = Dependency.parse(request)

    if dep.comparator is None or dep.comparator == '':
        dep.comparator = 'None'
        dep.version = ''

    return dep.package, dep.comparator, dep.version


def showCmd(cmd):
    # A command (list of arguments) as text for logging
    return shlex.join(cmd)


def quietArgs():
    # pip's quiet option, unless --verbose turned it off
    return [pipQuiet] if pipQuiet else []


def pythonMinorVersion(python):
    # e.g. '3.11' for a python executable, or None if it cannot be run
    if python == SYSTEM_PYTHON:  # the python running pipInstall2
        return '%d.%d' % sys.version_info[:2]
    ok, out, err = runPip([python, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'])
    return out.strip() if ok and out.strip() else None


def venvReusable(envPath, pythonFile):
    """
    Can the existing venv be kept? Returns (reusable, reason it cannot be)
    It must have been made by the same Python version (major.minor) as the system's python - packages
    built for one version (e.g. 3.11 on Bookworm) do not work with another (e.g. 3.13 on Trixie) -
    its python must run, and it must see the system packages
    """
    cfgFile = os.path.join(envPath, 'pyvenv.cfg')
    if not os.path.isfile(cfgFile):
        return False, 'there is no existing venv'
    cfg = {}
    try:
        with open(cfgFile) as f:
            for line in f:
                if '=' in line:
                    key, value = line.split('=', 1)
                    cfg[key.strip().lower()] = value.strip()
    except OSError as e:
        return False, f'pyvenv.cfg could not be read ({e})'
    if cfg.get('include-system-site-packages', '').lower() != 'true':
        return False, 'the existing venv cannot see the system packages'
    systemVersion = pythonMinorVersion(SYSTEM_PYTHON)
    venvVersion = '.'.join((cfg.get('version') or cfg.get('version_info') or '').split('.')[:2])
    if systemVersion is None or venvVersion != systemVersion:
        return False, f'the existing venv was made for Python {venvVersion or "(unknown)"}, the system has Python {systemVersion}'
    if pythonMinorVersion(pythonFile) != systemVersion:
        return False, 'the existing venv\'s python does not run'
    return True, ''


def checkVenvPath(envPath, pluginPath):
    """
    The venv folder must be a real folder inside the plugin folder - if it were a symbolic link,
    creating the venv (venv --clear) would delete everything in the folder it points to
    """
    real = os.path.realpath(envPath)
    plugin = os.path.realpath(pluginPath)
    if os.path.islink(envPath) or os.path.commonpath([plugin, real]) != plugin:
        logger.critical(f'The venv folder must be a folder inside the plugin folder, not a symbolic link:\n{envPath} ==> {real}\n'
                        'Nothing was changed')
        shutDown(ExitCodes.PROBLEM_CREATING_VENV)


def createPythonEnv(envPath, pythonFile, clear):
    """
    Keep the existing venv if it can be reused, otherwise create it from scratch (--clear)
    Packages that are no longer needed are removed after installing (removeUnused)
    """
    if clear:
        reason = f'{CLEARVENV} was requested'
    else:
        reusable, reason = venvReusable(envPath, pythonFile)
        if reusable:
            logger.info(f'Using the existing Python Virtual Environment at:\n{envPath}')
            return
    # Create a new virtual environment - no network needed (pip comes from the python install)
    # pip is upgraded separately by upgradePip so that no network does not hold up or stop venv creation
    cmd = [SYSTEM_PYTHON, '-m', 'venv', envPath, '--clear', '--system-site-packages']
    logger.info(f'Creating Python Virtual Environment ({reason}) at:\n{envPath}')
    ok, out, err = runPip(cmd)
    if not ok:
        logger.critical(f'Problem creating Virtual Environment with {SYSTEM_PYTHON}\n{(err or out).strip()}')
        shutDown(ExitCodes.PROBLEM_CREATING_VENV)


def pipVersion(sitePath):
    # e.g. 'pip 26.3' - from the pip-<version>.dist-info folder in the venv (no need to run pip --version)
    try:
        versions = [e[len('pip-'):-len('.dist-info')] for e in os.listdir(sitePath) if re.fullmatch(r'pip-[^-]+\.dist-info', e)]
    except OSError:
        versions = []
    return f'pip {versions[0]}' if len(versions) == 1 else 'pip (version unknown)'


def upgradePip(pythonFile, sitePath):
    """
    Upgrade pip in the venv (and setuptools on Python 3.11 and earlier) - what venv --upgrade-deps does
    One quick attempt: without a network it gives up after a few seconds, logs a warning
    and the pip that came with the python install is used
    """
    # The packages venv --upgrade-deps would upgrade: pip, plus setuptools before Python 3.12
    # (the venv python is the same version as the python running pipInstall2)
    import venv
    deps = list(getattr(venv, 'CORE_VENV_DEPS', ('pip',)))

    # -vv so pip reports indexes it could not reach ("Could not fetch URL") - without a network
    # pip otherwise succeeds silently with "Requirement already satisfied"
    cmd = [pythonFile, '-m', PIP, 'install', '--upgrade', *deps,
           '--retries', '0', '--timeout', '5', '--disable-pip-version-check', '-vv']
    ok, out, err = runPip(cmd)
    unreachable = [line.strip() for line in (out + err).splitlines() if line.strip().startswith('Could not fetch URL')]
    for line in unreachable:
        logger.debug(f'\t{line}')
    version = pipVersion(sitePath)
    names = ' and '.join(deps)
    if not ok:
        logger.warning(f'Could not upgrade {names} in the venv - using {version} that came with Python\n{pipErrors(err)}')
    elif 'Successfully installed' in out:
        logger.info(f'Upgraded {names} in the venv - using {version}')
    elif 'Ignoring indexes:' in out + err:
        # pip is configured with no-index (e.g. in /etc/pip.conf) - it only installs from local folders (find-links)
        logger.info(f'{names} not upgraded - pip is configured not to use a package index (no-index)\n'
                    f'Using {version} that came with Python')
    elif unreachable:
        logger.warning(f'Could not upgrade {names} in the venv - the package index could not be reached (no network?)\n'
                       f'Using {version} that came with Python')
    else:
        logger.info(f'{names} in the venv {"is" if len(deps) == 1 else "are"} up to date - using {version}')


def importPackaging():
    try:
        import packaging.requirements
        import packaging.markers
        import packaging.specifiers
        return True, ''
    except ImportError as e:
        return False, str(e)


def checkPackaging(pythonFile, sitePath):
    """
    packaging is used to parse modules, markers and version conditions
    If it is not available in the system python, install it into the venv
    and add the venv site-packages to the end of this program's sys.path
    """
    global packagingInVenv
    ok, err = importPackaging()
    if ok:
        return
    # Installed in the venv by an earlier run (the venv is kept between runs)?
    if os.path.isdir(os.path.join(sitePath, 'packaging')):
        if sitePath not in sys.path:
            sys.path.append(sitePath)
        importlib.invalidate_caches()
        if importPackaging()[0]:
            packagingInVenv = True
            logger.info('The python "packaging" module is not in the system python - using the copy in the venv')
            return
    logger.info(f'The python "packaging" module is not available ({err}) - installing it into the venv')
    # --ignore-installed so a copy is put in the venv even if the venv can see another one
    cmd = [pythonFile, '-m', PIP, 'install', '--ignore-installed', 'packaging', *quietArgs()]
    installed, out, perr = runPip(cmd)
    if installed:
        packagingInVenv = True
        if sitePath not in sys.path:
            sys.path.append(sitePath)
        importlib.invalidate_caches()
        ok, err = importPackaging()
    else:
        err = pipErrors(perr)
    if not ok:
        logger.critical(f'The python "packaging" module is required but could not be installed or imported:\n{err}\n'
                        f'Install it e.g. sudo apt install python3-packaging')
        shutDown(ExitCodes.PACKAGING_NOT_AVAILABLE)
    logger.info('packaging installed in the venv and will be used from there')


def getModuleList(mFile):
    with open(mFile, encoding='utf-8') as jsonfile:
        try:
            config = json.load(jsonfile)
        except ValueError as e:
            logger.critical(f'"{mFile}" is not a properly formatted json file\n{e}')
            shutDown(ExitCodes.MANIFEST_ERROR)

    if not isinstance(config, dict):
        logger.critical(f'"{mFile}" is not a plugin manifest - expected a json object {{...}}')
        shutDown(ExitCodes.MANIFEST_ERROR)

    pluginname = config.get(NAME_KEY)
    if not isinstance(pluginname, str) or pluginname.strip() == '':
        logger.critical(f'"{mFile}" has no "{NAME_KEY}" entry')
        shutDown(ExitCodes.MANIFEST_ERROR)

    if MANIFEST_KEY not in config:
        logger.info(f'"{MANIFEST_KEY}" is not in the manifest - there are no python modules to install')
        return [], pluginname

    mList = config[MANIFEST_KEY]
    if not isinstance(mList, list) or not all(isinstance(entry, str) for entry in mList):
        logger.critical(f'"{MANIFEST_KEY}" must be a list of strings, e.g. ["requirements.txt"] or ["numpy", "requests>=2"]')
        shutDown(ExitCodes.MANIFEST_ERROR)

    return mList, pluginname


def stripComment(entry):
    # Remove trailing comment (pip rule: '#' at start or preceded by whitespace)
    return COMMENT_RE.sub('', entry).strip()


def checkPipOption(entry, where):
    """
    Stop on a pip option (e.g. --extra-index-url, -r, --hash=...) - pipInstall2 does not support them
    Checked while the entries are read, before the venv is created, so the install stops straight away
    where says where the entry came from e.g. "requirements.txt line 3"
    """
    if entry in ('--verbose', CLEARVENV) or entry.startswith(PYTHONREQ):
        return  # pipInstall2's own special entries
    option = PIPOPTION_RE.search(entry)
    if option is None:
        return
    name = option.group(1)
    logger.critical(f'"{entry}" ({where}):\n'
                    f'pip option "{name}" is not supported - see "Not supported" in special_cases.md')
    if name in INDEXOPTIONS:
        logger.critical('Package sources (indexes) cannot be set by a plugin - they are set for the whole system '
                        'in /etc/pip.conf (Raspberry Pi OS already adds piwheels there)')
    if name == '--user':
        logger.critical('Remove "--user" - packages are always installed in the plugin\'s venv')
    shutDown(ExitCodes.INVALID_DEPENDENCY)


def combineRequirements(moduleList, pluginPath):
    """
    Concatenate the sbcPythonDependencies entries and the lines of any requirements files (.txt)
    into one list. Comments and blank lines are removed.
    --verbose may appear anywhere (manifest or requirements file) - it is removed and reported
    --python<condition> (e.g. --python>=3.11) may appear anywhere - removed, conditions are combined
    --clear may appear anywhere - removed, the venv is rebuilt from scratch
    Returns (lines, verbose, clear, pythonConditions) - pythonConditions is a list, one item per --python entry
    """
    lines = []
    for entry in moduleList:
        entry = stripComment(entry)
        if entry == '':
            continue  # blank or comment-only entry
        if re.search(r'\.txt\S+$', entry, flags=re.IGNORECASE):
            # e.g. requirements.txt1 - a mistyped file name would otherwise be looked up on PyPI as a package
            logger.critical(f'"{entry}" looks like a requirements file name but does not end in ".txt"\n'
                            'Requirements files in sbcPythonDependencies must end in ".txt"')
            shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
        if entry.lower().endswith('.txt'):
            # It's a requirements file in <plugin path>/dsf
            if '\0' in entry:
                logger.critical(f'Requirements file name {entry!r} contains a null character')
                shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
            dsfPath = os.path.realpath(os.path.join(pluginPath, 'dsf'))
            reqfile = os.path.realpath(os.path.join(dsfPath, entry))
            # Must stay inside <plugin path>/dsf - no ../, absolute paths or symlinks leading out of it
            if os.path.commonpath([dsfPath, reqfile]) != dsfPath:
                logger.critical(f'Requirements file "{entry}" is outside the plugin\'s dsf folder:\n{reqfile}\n'
                                f'Requirements files must be in {dsfPath} or a subfolder of it')
                shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
            if not os.path.isfile(reqfile):
                logger.critical(f'Requirements file "{entry}" was not found at:\n{reqfile}')
                shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
            logger.info(f'Reading requirements file: {reqfile}')
            try:
                with open(reqfile, 'r', encoding='utf-8') as f:
                    fileLines = f.read().splitlines()
            except (OSError, UnicodeDecodeError) as e:
                logger.critical(f'Requirements file "{entry}" could not be read - it must be a UTF-8 text file\n{e}')
                shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
            for number, line in enumerate(fileLines, start=1):
                line = stripComment(line)
                if line != '':
                    checkPipOption(line, f'{entry} line {number}')
                    if re.search(r'\.txt\S*$', line, flags=re.IGNORECASE):
                        # it would otherwise be looked up on PyPI as a package called e.g. other.txt
                        logger.critical(f'"{line}" ({entry} line {number}): a requirements file cannot include another '
                                        f'requirements file - list each file in {MANIFEST_KEY} instead')
                        shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
                    lines.append(line)
        else:
            checkPipOption(entry, MANIFEST_KEY)
            lines.append(entry)

    verbose = '--verbose' in lines
    lines = [line for line in lines if line != '--verbose']

    clear = CLEARVENV in lines
    lines = [line for line in lines if line != CLEARVENV]

    pythonConditions = [line[len(PYTHONREQ):].strip() for line in lines if line.startswith(PYTHONREQ)]
    lines = [line for line in lines if not line.startswith(PYTHONREQ)]

    return lines, verbose, clear, pythonConditions


def checkPythonVersion(pythonConditions, pythonFile):
    """
    Test the venv python against each --python condition (e.g. >=3.11) in turn and log the result of each
    Stop if any condition cannot be understood (INVALID_DEPENDENCY) or is not met (PYTHON_VERSION_NOT_SUPPORTED)
    Needs packaging - call after checkPackaging
    """
    if not pythonConditions:
        return
    from packaging.specifiers import SpecifierSet, InvalidSpecifier

    if pythonFile == SYSTEM_PYTHON:  # the python running pipInstall2
        version = platform.python_version()
    else:
        ok, version, err = runPip([pythonFile, '-c', 'import platform; print(platform.python_version())'])
        if not ok:
            logger.critical(f'Could not get the python version of the venv\n{err.strip()}')
            shutDown(ExitCodes.UNEXPECTED_ERROR)
        version = version.strip()

    logger.info(f'\nChecking the plugin\'s Python version requirements (this system has Python {version}):')
    invalid = False
    failed = False
    for condition in pythonConditions:
        try:
            spec = SpecifierSet(condition)
            if len(spec) == 0 or any(s.version == '' for s in spec):
                raise InvalidSpecifier('no condition given')
        except InvalidSpecifier as e:
            logger.info(f'\t{PYTHONREQ}{condition} ==> Invalid - use e.g. {PYTHONREQ}>=3.11 ({e})')
            invalid = True
            continue
        if spec.contains(version, prereleases=True):
            logger.info(f'\t{PYTHONREQ}{condition} ==> Passed')
        else:
            logger.info(f'\t{PYTHONREQ}{condition} ==> Failed')
            failed = True

    if invalid:
        logger.critical('One or more --python conditions could not be understood. Nothing was installed')
        shutDown(ExitCodes.INVALID_DEPENDENCY)
    if failed:
        logger.critical(f'Python {version} does not meet the plugin\'s Python version requirements. Nothing was installed')
        shutDown(ExitCodes.PYTHON_VERSION_NOT_SUPPORTED)


def normaliseRequirement(line):
    """
    Correct the syntax of one entry so it is a valid requirements file line e.g.
        "numpy >= 1.2 , <2"          -> "numpy<2,>=1.2"
        "picamera2; sys_platform == 'linux'" -> "picamera2" on linux, dropped (None) elsewhere
    git+ urls are passed through unchanged
    An entry that cannot be corrected stops the install (INVALID_DEPENDENCY)
    """
    from packaging.requirements import Requirement, InvalidRequirement

    text = line.strip()

    if text.startswith('git+'):
        if not GIT_URL_RE.fullmatch(text):
            logger.critical(f'Invalid git url "{line}"\n'
                            'Use git+https://, git+ssh:// or git+file:// followed by the url (not git+http:// - it is not encrypted), '
                            'with no spaces, quotes or any of $ ` \\ ; | < > ( ) * \'')
            shutDown(ExitCodes.INVALID_DEPENDENCY)
        return text

    try:
        req = Requirement(text)
    except InvalidRequirement as e:
        logger.critical(f'Invalid entry "{line}"\n{e}')
        shutDown(ExitCodes.INVALID_DEPENDENCY)

    if req.url:
        logger.critical(f'Unsupported url form in "{line}" - use git+<url> instead')
        shutDown(ExitCodes.INVALID_DEPENDENCY)

    if any(spec.version == '' for spec in req.specifier):  # e.g. "six ===" - accepted by packaging, rejected by pip
        logger.critical(f'Invalid entry "{line}" - a version condition has no version')
        shutDown(ExitCodes.INVALID_DEPENDENCY)

    if req.marker is not None:
        try:
            if not req.marker.evaluate():
                logger.info(f'Skipping "{line}" - marker does not apply to this platform')
                return None
            logger.debug(f'Marker "{req.marker}" applies to "{line}"')
        except Exception as e:
            logger.warning(f'Could not evaluate marker in "{line}": {e} - installing it anyway')

    extras = f'[{",".join(sorted(req.extras))}]' if req.extras else ''
    return f'{req.name}{extras}{req.specifier}'


def normaliseRequirements(lines):
    # Correct the syntax of every entry - the result is a virtual requirements file
    result = []
    for line in lines:
        fixed = normaliseRequirement(line)
        if fixed is None:
            continue  # marker does not apply
        if fixed != line:
            logger.debug(f'"{line}" ==> "{fixed}"')
        result.append(fixed)
    return result


# Installed packages the venv python can see (venv first, then system packages) as {name: version} -
# what pip freeze lists, read from the package metadata directly (about twice as fast as running pip)
PACKAGES_SCRIPT = r"""
import importlib.metadata as md, json
found = {}
for dist in md.distributions():  # in sys.path order - the first of a name is the one that is used
    name = dist.metadata['Name']
    if name and dist.version and name not in found:
        found[name] = dist.version
print(json.dumps(found))
"""


def getFreezeList(pythonFile) -> dict:
    # {normalised package name: version} of everything the venv python can see (venv and system packages)
    ok, out, err = runPip([pythonFile, '-c', PACKAGES_SCRIPT])
    try:
        found = json.loads(out) if ok else None
    except ValueError:
        found = None
    if not isinstance(found, dict):
        logger.critical(f'Aborting: Failed to get the list of installed packages\n{err.strip()}')
        shutDown(ExitCodes.PIP_LIST_ERROR)
    # Names are normalised (case, - _ .) because they vary e.g. zope.interface / zope-interface, PyYAML / pyyaml
    versions = {}
    for name, version in found.items():
        versions.setdefault(normaliseName(name), version)
    return versions


# Module search - run by the venv python with -I -c: can the module be found, and what is its version?
# Used for names pip freeze does not know, e.g. modules from apt with no pip information (libcamera, pykms)
# or an import name (cv2) - the module is found with importlib.util.find_spec, which does not run its code
# (for a dotted name, e.g. a.b, the parent package a is imported). The version comes from the package metadata
# The result is one line "PIPINSTALL2_RESULT:[version, type, package name]" written straight to the output (os.write, not print,
# so anything a parent package prints cannot mix with it), then os._exit ends the process at once
FIND_SCRIPT = r"""
import importlib.util, json, os, sys

def answer(version, kind, package=''):
    os.write(1, ('\nPIPINSTALL2_RESULT:' + json.dumps([version, kind, package]) + '\n').encode())
    os._exit(0)

name = sys.argv[1]
try:
    spec = importlib.util.find_spec(name)
except BaseException as e:  # e.g. the parent of a dotted name is missing or fails to import
    answer('Could not look for the module: ' + repr(e), 'NOTINSTALLED')
if spec is None:
    answer('Module not found', 'NOTINSTALLED')

version, package = None, ''
try:  # the package that provides the module, and its version (Python 3.10+)
    import importlib.metadata as md
    dists = md.packages_distributions().get(name.split('.')[0], [])
    if dists:
        package = dists[0]
        version = md.version(package)
except Exception:
    version = None
if version:
    answer(version, 'INSTALLEDWITHVERSION', package)
answer('No version information', 'INSTALLEDNOVERSION', package)
"""
IMPORTRESULT = 'PIPINSTALL2_RESULT:'


def getModuleVersion(m, pythonFile, sitePath, freezeList):
    if m.startswith('git+'):
        # A url is not a package or module name, so it cannot be looked up - a git package is always installed
        logger.debug('\tgit url - version cannot be checked')
        return 'None', modType.NOTINSTALLED.value

    m = m.split('[')[0]  # Remove any extras (stuff in square brackets)
    # The module search tries the package name with - replaced by _ (a package's import name can differ)
    underscore_m = m.replace('-', '_')

    # Is the package installed (pip freeze)
    version = freezeList.get(normaliseName(m))
    if version:
        if normaliseName(m) in venvPackages(sitePath):
            logger.debug(f'\tin pip\'s installed packages (venv): version {version}')
            return version, modType.PIPWITHVERSION.value
        logger.debug(f'\tin pip\'s installed packages (system packages): version {version}')
        return version, modType.SYSTEMWITHVERSION.value
    logger.debug('\tnot in pip\'s installed packages')

    # Part of Python itself (the standard library) - nothing to install
    # stdlib_module_names is Python 3.10+; builtin_module_names (modules compiled into python) is the fallback
    stdlib = getattr(sys, 'stdlib_module_names', sys.builtin_module_names)
    if underscore_m.split('.')[0] in stdlib:
        logger.debug(f'\t{underscore_m} is part of Python')
        return 'None', modType.BUILTIN.value

    # Module search. -I: neither the current folder nor PYTHON* environment variables affect what is found
    ok, out, err = runPip([pythonFile, '-I', '-c', FIND_SCRIPT, underscore_m], timeout=FINDTIMEOUT)
    found = [line[len(IMPORTRESULT):] for line in out.splitlines() if line.startswith(IMPORTRESULT)]
    try:
        result, resultType, package = json.loads(found[-1])
    except (IndexError, ValueError):
        logger.info(f'Search for module "{underscore_m}" did not complete ({err.strip() or "no result"}) - treated as not installed')
    else:

        if package:
            modulePackages[m] = package  # for the message if a version condition is used with this import name
        # Check if module can be imported (i.e. is installed)
        if resultType == 'INSTALLEDWITHVERSION':
            logger.debug(f'\tfound as module {underscore_m}: version {result}')
            return result, modType.INSTALLEDWITHVERSION.value
        elif resultType == 'INSTALLEDNOVERSION':
            logger.debug(f'\tfound as module {underscore_m} (no version number)')
            return 'Installed', modType.INSTALLEDNOVERSION.value
        elif resultType == 'NOTINSTALLED':
            reason = '' if result == 'Module not found' else f' - {result}'
            logger.debug(f'\tnot found as module {underscore_m}{reason} (a package\'s import name can differ, e.g. cv2)')

    return 'None', modType.NOTINSTALLED.value


def runPip(cmd, timeout=None, input=None):
    """
    Run a python command (list of arguments, no shell, so entries cannot inject shell commands) without raising
    Returns (ok, stdout, stderr) - stderr holds the reason if the command could not be run or timed out
    - python is run with -I and from the root folder, so a module in the current folder (e.g. a pip/ folder)
      or PYTHONPATH cannot replace pip or a module the command uses
    - PIP_RETRIES and the pip cache are set with environment variables so they also apply to pip's own subprocesses
      (e.g. installing build dependencies) - command line options do not
    - pip uses this run's own cache (runCache), so a package downloaded by the dry run is not downloaded again
      by the install; the user's pip cache is not used or changed. Before the cache exists, pip runs with no cache
    """
    if cmd[1:2] != ['-I']:
        cmd = [cmd[0], '-I', *cmd[1:]]
    logger.debug(f'Running ==> {showCmd(cmd)}')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input, cwd=os.sep,
                                env={**os.environ, 'PIP_RETRIES': PIPRETRIES,
                                     **({'PIP_CACHE_DIR': runCache} if runCache else {'PIP_NO_CACHE_DIR': '1'})})
    except subprocess.TimeoutExpired:
        return False, '', f'timed out after {timeout} seconds'
    except OSError as e:
        return False, '', str(e)
    return result.returncode == 0, result.stdout, result.stderr


def errorLines(stderr):
    # pip's ERROR lines, including indented ones from a build subprocess (e.g. installing build dependencies)
    return [line.strip() for line in stderr.splitlines() if line.lstrip().startswith('ERROR')]


def pipErrors(stderr):
    # Just the ERROR lines from pip output (or everything if there are none)
    # pip's "Ignored the following versions that require a different python version" line is only shown with --verbose
    lines = errorLines(stderr)
    if not logger.isEnabledFor(logging.DEBUG):
        lines = [line for line in lines if not line.startswith('ERROR: Ignored the following')] or lines
    return '\n'.join(lines) if lines else stderr.strip()


def pipFailureReason(stderr):
    # A short reason for the result summary - pip's last top-level ERROR line,
    # or the last indented one (from a build subprocess) if there is none
    def useful(line):
        return not line.lstrip().startswith('ERROR: Ignored the following')
    top = [line for line in stderr.splitlines() if line.startswith('ERROR') and useful(line)]
    lines = top or [line for line in errorLines(stderr) if useful(line)]
    if not lines:
        return 'pip reported an error (see the log above)'
    return lines[-1].strip().replace('ERROR: ', '', 1).strip()


def normaliseName(name):
    # PEP 503 normalised package name, without extras e.g. Foo_Bar[x] -> foo-bar
    return re.sub(r'[-_.]+', '-', name.split('[')[0].strip()).lower()


@functools.lru_cache(maxsize=None)
def venvPackages(sitePath):
    # Normalised names of the packages installed in the venv itself (not the system packages it can see)
    names = set()
    try:
        for entry in os.listdir(sitePath):
            if entry.endswith('.dist-info'):
                names.add(normaliseName(entry[:-len('.dist-info')].rsplit('-', 1)[0]))
    except OSError:
        pass
    return names


def requestString(mod, comp, val):
    return mod if comp == 'None' else f'{mod}{comp}{val}'


def installModule(mod, comp, val, pythonFile, venvPath):
    # Returns (ok, reason) - reason is a short explanation when the install fails
    request = requestString(mod, comp, val)

    logger.info(f'\nAttempting install of: {request}\n')

    # Dry run of just this module so a slow build from source is reported before it starts
    reportfile = os.path.normpath(os.path.join(venvPath, REPORTFILENAME))
    removeLink(reportfile)
    cmd = [pythonFile, '-m', PIP, 'install', '--dry-run', '--report', reportfile, request, PIPPREFERBINARY, *quietArgs()]
    ok, out, err = runPip(cmd)
    if ok:
        logPlannedInstalls(reportfile, pythonFile)

    cmd = [pythonFile, '-m', PIP, 'install', request, PIPPREFERBINARY, *quietArgs()]
    ok, out, err = runPip(cmd)

    if not ok:  # module could not be installed
        logger.info(f'Module: {request} could not be installed\n{pipErrors(err)}')
        return False, pipFailureReason(err)
    logger.debug(f'Result was ==> \n{out}')
    return True, ''


def checkBuildTools(pythonFile):
    """
    Check for the basic tools that almost every source build needs and log any that are missing
    Packages may need other tools or libraries as well - these are not declared in a way that can be checked
    Only reports - the install carries on either way
    Only checked once per run
    """
    global buildToolsChecked
    if buildToolsChecked:
        return
    buildToolsChecked = True

    # The include folder of the venv's python is where Python.h should be
    ok, out, err = runPip([pythonFile, '-c', "import sysconfig; print(sysconfig.get_paths()['include'])"])
    pythonHeader = os.path.join(out.strip(), 'Python.h') if ok and out.strip() else ''

    # (description, found, apt package that provides it)
    checks = [
        ('C compiler (cc / gcc)', shutil.which('cc') or shutil.which('gcc'), 'build-essential'),
        ('C++ compiler (c++ / g++)', shutil.which('c++') or shutil.which('g++'), 'build-essential'),
        ('Python headers (Python.h)', pythonHeader and os.path.isfile(pythonHeader), 'python3-dev'),
        ('pkg-config', shutil.which('pkg-config'), 'pkg-config'),
    ]

    logger.info('Checking the basic build tools:')
    missing = []
    for description, found, aptPackage in checks:
        logger.info(f'\t{description} ==> {"Found" if found else "Missing"}')
        if not found and aptPackage not in missing:
            missing.append(aptPackage)
    if missing:
        logger.info(f'Missing build tools can be installed with: sudo apt install {" ".join(missing)}')
    logger.info('Some packages also need other tools or libraries - see the package\'s install documentation.')


def dryRun(requests, pythonFile, venvPath):
    """
    Write the requests to a requirements file and ask pip what it would install
    Logs the planned installs (requested modules and their dependencies)
    Returns (ok, reqfile)
    """
    reqfile = os.path.normpath(os.path.join(venvPath, REQFILENAME))
    reportfile = os.path.normpath(os.path.join(venvPath, REPORTFILENAME))
    removeLink(reqfile)
    removeLink(reportfile)
    # Owner-only: a git url may contain a token
    with open(os.open(reqfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f:
        f.write('\n'.join(requests) + '\n')
    os.chmod(reqfile, 0o600)  # if it already existed
    logger.debug(f'Requirements written to {reqfile}:\n' + '\n'.join(requests))

    cmd = [pythonFile, '-m', PIP, 'install', '--dry-run', '--report', reportfile, '-r', reqfile, PIPPREFERBINARY, *quietArgs()]
    ok, out, err = runPip(cmd)
    if not ok:
        logger.info(f'Dry run failed - pip could not resolve the requested modules together:\n{pipErrors(err)}')
        return False, reqfile

    logPlannedInstalls(reportfile, pythonFile)
    logger.debug(f'Full dry run report: {reportfile}')
    return True, reqfile


def logPlannedInstalls(reportfile, pythonFile):
    """
    Log what a pip --dry-run report says will be installed
    Modules that will be built from source are marked, followed by a warning and a check of the build tools
    """
    try:
        os.chmod(reportfile, 0o600)  # owner-only: a git url may contain a token
        with open(reportfile, encoding='utf-8') as f:
            items = json.load(f).get('install', [])
    except (OSError, ValueError) as e:
        logger.info(f'Dry run succeeded but the report could not be read: {e}')
        return

    if not items:
        logger.info('Dry run: nothing needs to be installed - all requirements are already satisfied')
    else:
        logger.info('Dry run: pip will install the following:')
        builds = []
        for item in sorted(items, key=lambda x: (not x.get('requested', False), x.get('metadata', {}).get('name', '').lower())):
            md = item.get('metadata', {})
            kind = 'requested' if item.get('requested') else 'dependency'
            name = f'{md.get("name", "?")}=={md.get("version", "?")}'
            # A download that is not a wheel (.whl) is source code (or a git repository) that pip has to build
            url = item.get('download_info', {}).get('url', '')
            if url and not url.lower().endswith('.whl'):
                builds.append(name)
                kind += ', will be built from source'
            logger.info(f'\t{name}  ({kind})')
        if builds:
            logger.info('\nThese modules have no ready-built wheel for this system and will be built from source:')
            for name in builds:
                logger.info(f'\t{name}')
            logger.info('Building can take a long time (sometimes tens of minutes on a Pi).')
            checkBuildTools(pythonFile)


def installRequirements(reqfile, pythonFile):
    # Install everything with a single pip call so pip resolves all modules together
    cmd = [pythonFile, '-m', PIP, 'install', '-r', reqfile, PIPPREFERBINARY, *quietArgs()]
    ok, out, err = runPip(cmd)
    if not ok:
        logger.info(f'Combined install failed:\n{pipErrors(err)}')
    else:
        logger.debug(f'Result was ==> \n{out}')
    return ok


def parseRequests(mList, pythonFile, sitePath, freezeList):
    modulerequests = []
    install_result, install_version = '', ''
    for module in mList:
        mod_name, requested_version_comp, requested_version_val = parseVersion(module)
        condition = 'no version condition' if requested_version_comp == 'None' else f'condition {requested_version_comp}'
        logger.debug(f'\nChecking {mod_name} ({condition}):')
        current_version, current_type = getModuleVersion(mod_name, pythonFile, sitePath, freezeList)
        logger.debug(f'\t==> {decide(requested_version_comp, current_version, current_type)[1]}')
        modulerequests.append([mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version])
    checkImportNameConditions(modulerequests)
    return modulerequests


def checkImportNameConditions(modulerequests):
    """
    An entry found only by the module search (not in pip's list - e.g. an import name such as gi or serial,
    or a module from apt) whose version condition is not known to be met would be sent to pip under that name.
    PyPI may have an unrelated package of that name (e.g. gi, serial), which would be installed in the venv and
    hide the real module, so stop before installing anything (INVALID_DEPENDENCY)
    """
    found = (modType.INSTALLEDWITHVERSION.value, modType.INSTALLEDNOVERSION.value)
    bad = [r for r in modulerequests
           if r[4] in found and r[1] != 'None' and not versionSatisfies(r[3], r[4], r[1])]
    if not bad:
        return
    logger.critical('\nThese entries are installed modules that pip does not know by that name '
                    '(an import name, or a module installed with apt), so a version condition cannot be used with them:')
    for mod_name, comp, val, current_version, current_type, *_ in bad:
        package = modulePackages.get(mod_name.split('[')[0])
        have = f'version {current_version}' if current_type == modType.INSTALLEDWITHVERSION.value else 'version unknown'
        use = f'use the PyPI package name, e.g. {package}{comp}' if package else 'use the PyPI package name, or remove the condition'
        logger.critical(f'\t{mod_name}{comp}{val} ({have}) - {use}')
    logger.critical('A version condition needs the PyPI package name (see "Package names and import names" in special_cases.md). '
                    'Nothing was installed')
    shutDown(ExitCodes.INVALID_DEPENDENCY)


def versionSatisfies(current_version, current_type, condition):
    # True if the installed version is known and meets the condition e.g. >=1.2,<2.0
    if current_type not in (modType.PIPWITHVERSION.value, modType.SYSTEMWITHVERSION.value, modType.INSTALLEDWITHVERSION.value):
        return False
    try:
        from packaging.specifiers import SpecifierSet
        ok = SpecifierSet(condition).contains(current_version, prereleases=True)
    except Exception as e:
        logger.debug(f'Could not compare version "{current_version}" with "{condition}": {e}')
        return False
    return ok


def decide(comp, current_version, current_type):
    """
    The rules for whether a module needs installing
    Returns (install_result, explanation) - install_result is 'Builtin', 'Skipped' or '' (needs installing)
    """
    installedTypes = (modType.PIPWITHVERSION.value, modType.SYSTEMWITHVERSION.value,
                      modType.INSTALLEDWITHVERSION.value, modType.INSTALLEDNOVERSION.value)
    if current_type == modType.BUILTIN.value:
        return 'Builtin', 'built into Python - ignored'
    if current_type in installedTypes and comp == 'None':
        return 'Skipped', 'already available, no version condition - skipped'
    if comp != 'None' and versionSatisfies(current_version, current_type, comp):
        return 'Skipped', f'version {current_version} meets {comp} - skipped'
    if current_type in installedTypes:
        if current_version in ('None', 'Installed'):
            return '', f'version unknown, so {comp} cannot be checked - will be installed'
        return '', f'version {current_version} does not meet {comp} - will be installed'
    return '', 'not installed - will be installed'


def selectRequests(modulerequests):
    # Apply the rules - mark Builtin / Skipped and return the indices that need installing
    toInstall = []
    for idx, request in enumerate(modulerequests):
        mod_name, requested_version_comp, requested_version_val, \
            current_version, current_type, install_result, install_version \
            = unpackRequestList(request)

        install_result = decide(requested_version_comp, current_version, current_type)[0]
        if not install_result:
            toInstall.append(idx)

        modulerequests[idx] = [mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version]
    return toInstall


def setResult(modulerequests, idx, install_result):
    modulerequests[idx][5] = install_result


def processRequests(modulerequests, pythonFile, venvPath):
    """
    1) Apply the rules to decide what needs installing
    2) pip --dry-run of everything together - logs what will actually be installed
    3) single pip install -r of everything together
    4) if 2) or 3) fails, install one module at a time so the others still get installed
    """
    together = selectRequests(modulerequests)
    if not together:
        return modulerequests

    requests = [requestString(*modulerequests[i][0:3]) for i in together]
    logger.info('\n\nChecking what pip will install (dry run):')
    ok, reqfile = dryRun(requests, pythonFile, venvPath)
    if ok:
        logger.info('\nInstalling all modules together (single pip install -r):')
        ok = installRequirements(reqfile, pythonFile)
    if ok:
        for i in together:
            setResult(modulerequests, i, 'Succeeded')
        return modulerequests

    logger.info('\nFalling back to installing modules one at a time')
    for i in sorted(together):
        mod_name, comp, val = modulerequests[i][0:3]
        ok, reason = installModule(mod_name, comp, val, pythonFile, venvPath)
        if ok:
            setResult(modulerequests, i, 'Succeeded')
        else:
            setResult(modulerequests, i, 'Failed')
            modulerequests[i][6] = reason  # install_version holds the reason for a failed module

    return modulerequests


# Run by the venv python (so it sees the venv and system packages in the same order the plugin does)
# Reads {"site": <venv site-packages>, "requests": [...], "keep": [...]} from stdin
# Prints a json list of [name, version, system version or null] for venv packages nothing requested needs
UNUSED_SCRIPT = r"""
import json, os, re, sys
import importlib.metadata as md
from packaging.requirements import Requirement

data = json.load(sys.stdin)
site = os.path.realpath(data['site'])

def norm(name):
    return re.sub(r'[-_.]+', '-', name).lower()

def inVenv(dist):
    return os.path.realpath(str(dist.locate_file(''))) == site

def gitUrl(url):
    # git+https://host/x/y.git@v1#egg=y -> https://host/x/y.git
    url = url[len('git+'):] if url.startswith('git+') else url
    url = url.split('#', 1)[0]
    head, sep, tail = url.rpartition('/')
    return (head + sep + tail.split('@', 1)[0]).rstrip('/')

found = {}  # name -> distributions in sys.path order (the first is the one that is used)
for dist in md.distributions():
    name = dist.metadata['Name']
    if name:
        found.setdefault(norm(name), []).append(dist)

todo = []
for request in data['requests']:
    if request.startswith('git+'):
        matches = []
        for name, dists in found.items():
            try:
                url = json.loads(dists[0].read_text('direct_url.json') or '{}').get('url', '')
            except ValueError:
                url = ''
            if url and gitUrl(url) == gitUrl(request):
                matches.append(name)
        if not matches:
            print(json.dumps({'error': 'no installed package came from ' + request}))
            sys.exit(0)
        todo += [(name, set()) for name in matches]
    else:
        req = Requirement(request)
        todo.append((norm(req.name), set(req.extras)))

needed = {}  # name -> extras followed
while todo:
    name, extras = todo.pop()
    if name in needed and extras <= needed[name]:
        continue
    needed[name] = needed.get(name, set()) | extras
    if name not in found:
        continue
    for line in found[name][0].requires or []:
        req = Requirement(line)
        if req.marker is not None and not any(req.marker.evaluate({'extra': e}) for e in [''] + sorted(needed[name])):
            continue
        todo.append((norm(req.name), set(req.extras)))

unused = []
for name, dists in sorted(found.items()):
    if inVenv(dists[0]) and name not in needed and name not in data['keep']:
        system = [d.version for d in dists[1:] if not inVenv(d)]
        unused.append([dists[0].metadata['Name'], dists[0].version, system[0] if system else None])
print(json.dumps({'unused': unused}))
"""


def removeUnused(modulerequests, pythonFile, sitePath):
    """
    Remove packages from the venv that nothing in this run's requests needs - i.e. ones installed
    by an earlier run for an entry that has since been removed from sbcPythonDependencies
    The requests' dependencies are followed through the venv and system packages
    Returns a list of removed packages for the summary
    """
    found = (modType.INSTALLEDWITHVERSION.value, modType.INSTALLEDNOVERSION.value)
    requests = []
    for r in modulerequests:
        if r[5] == 'Builtin':
            continue
        name, comp, val = r[0:3]
        base = name.split('[')[0]
        if r[4] in found and base in modulePackages:  # an import name (e.g. yaml) - its package (PyYAML) is needed
            name = modulePackages[base] + name[len(base):]
        requests.append(requestString(name, comp, val))
    keep = sorted(KEEPINVENV | ({'packaging'} if packagingInVenv else set()))
    data = json.dumps({'site': sitePath, 'requests': requests, 'keep': keep})
    ok, out, err = runPip([pythonFile, '-c', UNUSED_SCRIPT], input=data)
    try:
        answer = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        logger.warning(f'Could not check the venv for packages that are no longer needed - none removed\n{err.strip()}')
        return []
    if 'error' in answer:
        logger.warning(f'Could not check the venv for packages that are no longer needed ({answer["error"]}) - none removed')
        return []

    unused = answer['unused']
    if not unused:
        logger.debug('No packages in the venv are unused')
        return []
    logger.info('\nRemoving packages from the venv that are no longer needed:')
    removed = []
    for name, version, system in unused:
        note = f' - the system packages\' version {system} will be used instead' if system else ''
        logger.info(f'\t{name}=={version}{note}')
        removed.append(f'{name}=={version}{note}')
    ok, out, err = runPip([pythonFile, '-m', PIP, 'uninstall', '-y', *[u[0] for u in unused], *quietArgs()])
    venvPackages.cache_clear()
    if not ok:
        # Some may have been removed before the error - report only those that are gone
        left = venvPackages(sitePath)
        gone = [line for line, u in zip(removed, unused) if normaliseName(u[0]) not in left]
        logger.warning(f'Could not remove all the unused packages:\n{pipErrors(err)}')
        return gone
    return removed


def checkConflicts(modulerequests, pythonFile, sitePath):
    """
    pip check - find installed packages whose requirements are not met
    Only problems that involve the plugin are returned:
    - a package the plugin requested, or one installed in the venv (the plugin's dependencies), has an unmet requirement
    - a system package needs a different version of a package that was installed in the venv
    Problems that are only between system packages are logged with --verbose but ignored
    """
    venvNames = venvPackages(sitePath)
    pluginNames = venvNames | {normaliseName(r[0]) for r in modulerequests if not r[0].startswith('git+')}

    ok, out, err = runPip([pythonFile, '-m', PIP, 'check'])
    conflicts = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith('No broken requirements'):
            continue
        owner = normaliseName(line.split(' ', 1)[0])
        have = re.search(r'but you have (\S+) ', line)  # e.g. ... has requirement numpy>=2, but you have numpy 1.26.4.
        if owner in pluginNames or (have and normaliseName(have.group(1)) in venvNames):
            conflicts.append(line)
        else:
            logger.debug(f'pip check (system packages only - ignored): {line}')
    return conflicts


def unpackRequestList(request):
    mod_name = request[0]
    requested_version_comp = request[1]
    requested_version_val = request[2]
    current_version = request[3]
    current_type = request[4]
    install_result = request[5]
    install_version = request[6]
    return mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version


def getUpdatedVersions(modulerequests, pythonFile, sitePath, freezeList):
    for idx, request in enumerate(modulerequests):
        mod_name, requested_version_comp, requested_version_val, \
            current_version, current_type, install_result, install_version \
            = unpackRequestList(request)

        if install_result == 'Succeeded':
            logger.debug(f'{mod_name}:')
            install_version, install_type = getModuleVersion(mod_name, pythonFile, sitePath, freezeList)
            nowVersion = install_version
        elif install_result != 'Failed':  # a failed module keeps its failure reason
            install_version = 'None'
            # A skipped package may have been changed by installing another entry
            install_type = current_type
            nowVersion = freezeList.get(normaliseName(mod_name), current_version)
        # The entry's condition must still be met by the version now installed - e.g. two entries for the same
        # package with different conditions, or a later entry needing a different version of an earlier one
        if (install_result in ('Succeeded', 'Skipped') and requested_version_comp != 'None'
                and install_type in (modType.PIPWITHVERSION.value, modType.SYSTEMWITHVERSION.value, modType.INSTALLEDWITHVERSION.value)
                and not versionSatisfies(nowVersion, install_type, requested_version_comp)):
            install_result = 'Failed'
            install_version = (f'version {nowVersion} is now installed, which does not meet {requested_version_comp} - '
                               'another entry, or a package it needs, requires a different version')

        modulerequests[idx] = [mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version]

    return modulerequests


def sortResults(modulerequests):
    builtinList = []
    skippedList = []
    installedList = []
    failedList = []

    for req in modulerequests:
        mod_name, requested_version_comp, requested_version_val, \
            current_version, current_type, install_result, install_version \
            = unpackRequestList(req)

        if install_result == 'Builtin':
            builtinList.append(req)
        elif install_result == 'Skipped':
            skippedList.append(req)
        elif install_result == 'Succeeded':
            installedList.append(req)
        else:
            failedList.append(req)

    return builtinList, skippedList, installedList, failedList


def reportResults(builtinList, skippedList, installedList, failedList, conflicts, removed):
    logger.info('---------------------------------------')
    logger.info('Result Summary')
    logger.info('---------------------------------------')

    if (len(builtinList) > 0):
        logger.info('\nThese modules were Ignored (built-in):')
        for req in builtinList:
            mod_name, requested_version_comp, requested_version_val, \
                current_version, current_type, install_result, install_version \
                = unpackRequestList(req)
            if requested_version_comp == 'None':
                requested_version_comp = ''
            logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> Ignored')

    if (len(skippedList) > 0):
        logger.info('\nThese modules were Skipped (Already installed - no version requested or version condition already met):')
        for req in skippedList:
            mod_name, requested_version_comp, requested_version_val, \
                current_version, current_type, install_result, install_version \
                = unpackRequestList(req)
            if current_version in ('None', 'Installed'):
                current_version = ''
            if requested_version_comp == 'None':
                requested_version_comp = ''
            logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> {current_type} {current_version}'.rstrip())

    if (len(installedList) > 0):
        logger.info('\nThese modules were successfully installed / updated:')
        for req in installedList:
            mod_name, requested_version_comp, requested_version_val, \
                current_version, current_type, install_result, install_version \
                = unpackRequestList(req)
            if requested_version_comp == 'None':
                requested_version_comp = ''
            if mod_name.startswith('git+'):
                # The version of a git package cannot be looked up by its url
                logger.info(f'\t{mod_name} ==> installed from the git repository')
                continue
            if current_version == install_version and current_version not in ('None', 'Installed'):
                install_version = 'Reinstalled with same version'
            if current_version == 'None' or current_version == 'Installed':
                current_version = ''
            if install_version == 'None':
                install_version = 'no Version'
            was = f'{current_type} {current_version}'.strip()
            logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> was {was}, now {install_version}')

    if (len(failedList) > 0):
        logger.info('\nThese modules failed to install / update:')
        for req in failedList:
            mod_name, requested_version_comp, requested_version_val, \
                current_version, current_type, install_result, install_version \
                = unpackRequestList(req)
            if requested_version_comp == 'None':
                requested_version_comp = ''
            reason = install_version if install_version not in ('', 'None') else 'pip reported an error (see the log above)'
            logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> {reason}')
            if current_type != modType.NOTINSTALLED.value:
                before = current_type if current_version in ('None', 'Installed') else f'{current_type} {current_version}'
                logger.info(f'\t\t(before the install it was {before})')

    if removed:
        logger.info('\nThese packages were removed from the venv (no longer needed):')
        for line in removed:
            logger.info(f'\t{line}')

    if conflicts:
        logger.info('\nThese installed modules are not compatible with each other:')
        for line in conflicts:
            logger.info(f'\t{line}')


def createRunCache(venvPath):
    # This run's pip cache - a new owner-only folder in the venv folder (not /tmp, which can be in memory),
    # deleted by shutDown
    global runCache
    try:
        runCache = tempfile.mkdtemp(prefix='pip-cache-', dir=venvPath)
        logger.debug(f'pip cache for this run: {runCache}')
    except OSError as e:
        logger.debug(f'No pip cache for this run ({e}) - packages may be downloaded more than once')


def removeRunCache():
    global runCache
    if runCache:
        shutil.rmtree(runCache, ignore_errors=True)
        runCache = None


def shutDown(code):
    removeRunCache()
    # logger does not exist yet if called while validating arguments
    out = logger.info if 'logger' in globals() else print
    if 'logger' in globals() and logFiles and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        createLogfile(*logFiles)  # stopped before the log file was created (e.g. a manifest error)
    out('---------------------------------------')
    out(f'Exiting with code {code.value} ({code.name})')
    out('---------------------------------------')
    sys.exit(code.value)


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
def main(progName):
    global pipQuiet
    #  Validate calling arguments
    manifestFile, pluginPath = validateParams()
    # Absolute paths - commands are run from the root folder (see runPip), so a relative path would point elsewhere
    manifestFile, pluginPath = os.path.abspath(manifestFile), os.path.abspath(pluginPath)
    venvPath = os.path.normpath(os.path.join(pluginPath, VENV_FOLDER))
    pythonFile = os.path.normpath(os.path.join(venvPath, BIN_DIR, PYTHON_VERSION))
    logfilename = os.path.normpath(os.path.join(venvPath, LOGNAME))

    #  Set up consolelogging so journalc can be used
    createLogger(progName)
    logger.info('---------------------------------------------------')
    logger.info(f'{progName} Version {THIS_VERSION} is attempting to install python modules')

    # Before anything is written to the venv folder (including the log file)
    checkVenvPath(venvPath, pluginPath)

    global logFiles
    logFiles = (logfilename, FALLBACK_LOGFILENAME)

    # Read the manifest file
    moduleList, pluginName = getModuleList(manifestFile)

    logger.info(f'Plugin name is : {pluginName}')

    # One list of the manifest entries and the contents of any requirements files
    moduleList, verbose, clear, pythonConditions = combineRequirements(moduleList, pluginPath)

    # --verbose flag set adjust output level
    if verbose:
        logger.setLevel(logging.DEBUG)
        pipQuiet = ''
        logger.debug('--verbose found - debug logging on')

    # Check the entries and --python before the venv is changed (needs packaging in the system python - the usual case;
    # otherwise packaging is installed in the venv first and they are checked after that)
    checkedEarly = importPackaging()[0]
    if checkedEarly:
        checkPythonVersion(pythonConditions, SYSTEM_PYTHON)  # the venv is made by (or must match) this python
        moduleList = normaliseRequirements(moduleList)

    #  Create the virtual environment, or keep the existing one
    createPythonEnv(venvPath, pythonFile, clear)

    # add log file
    createLogfile(logfilename, FALLBACK_LOGFILENAME)

    # This run's pip cache - deleted when pipInstall2 exits
    createRunCache(venvPath)

    # Find the venv site-packages path
    sitePath = findSitePackages(pythonFile, venvPath)
    removeOldFiles(venvPath, sitePath)

    # Upgrade pip - not fatal if it cannot be done (e.g. no network)
    upgradePip(pythonFile, sitePath)

    # packaging is needed to parse the module list - installed into the venv if missing
    checkPackaging(pythonFile, sitePath)

    if not checkedEarly:
        # Stop before installing anything if the python version does not meet --python
        checkPythonVersion(pythonConditions, pythonFile)
        # Correct the syntax of every entry (drops entries whose platform marker does not apply)
        moduleList = normaliseRequirements(moduleList)
    logger.info('\nRequirements (manifest and requirements files combined):\n\t' + '\n\t'.join(moduleList))

    # Resolve the requested modules to a name and version
    # Create a list of modules to instal and their current versions
    logger.info('\n\nChecking installed versions before install:')
    freezeList = getFreezeList(pythonFile)  # Get initial freeze list
    moduleRequests = parseRequests(moduleList, pythonFile, sitePath, freezeList)

    # Process the requests and install modules as required
    moduleRequests = processRequests(moduleRequests, pythonFile, venvPath)
    venvPackages.cache_clear()  # the venv has changed

    if any(r[5] == 'Succeeded' for r in moduleRequests):  # nothing to look up if nothing was installed
        logger.info('\n\nChecking installed versions after install:')
        freezeList = getFreezeList(pythonFile)  # Get updated freeze list after parsing requests
        moduleRequests = getUpdatedVersions(moduleRequests, pythonFile, sitePath, freezeList)

    # Remove packages an earlier run installed that are no longer needed - only after a successful install,
    # so a partly installed list does not cause packages that are still needed to be removed
    removed = []
    if not any(r[5] == 'Failed' for r in moduleRequests):
        removed = removeUnused(moduleRequests, pythonFile, sitePath)
        venvPackages.cache_clear()

    # Check the installed modules work together (pip check)
    conflicts = checkConflicts(moduleRequests, pythonFile, sitePath)

    # Separate the results into lists for reporting
    builtinList, skippedList, installedList, failedList = sortResults(moduleRequests)

    # Report the results
    reportResults(builtinList, skippedList, installedList, failedList, conflicts, removed)

    if len(failedList) > 0:
        logger.info('---------------------------------------')
        logger.info('Some modules failed to install')
        logger.info('---------------------------------------')
        shutDown(ExitCodes.FAILED_TO_INSTALL_MODULE)

    if conflicts:
        logger.info('---------------------------------------')
        logger.info('The installed modules are not compatible with each other')
        logger.info('---------------------------------------')
        shutDown(ExitCodes.DEPENDENCY_CONFLICT)

    logger.info('---------------------------------------')
    logger.info('All modules were successfully installed')
    logger.info('---------------------------------------')
    shutDown(ExitCodes.SUCCESS)

# -------------------------------------------------------------------------------


if __name__ == "__main__":  # Do not run anything below if the file is imported by another program
    programName = os.path.basename(sys.argv[0])
    try:
        main(programName)
    except Exception:  # anything not handled - exit code 9, not Python's 1 (which means "no manifest file")
        import traceback
        if 'logger' in globals():
            logger.critical(f'Unexpected error:\n{traceback.format_exc()}')
        else:
            traceback.print_exc()
        shutDown(ExitCodes.UNEXPECTED_ERROR)
