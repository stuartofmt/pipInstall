#!/usr/bin/env python

"""
Install python modules and create a virtual environment for the plugin.

# Copyright (C) 2023 Stuart Strolin all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT

Useage:
Usage pipInstall.py -m <manifest file> -p <plugin path>

Both <manifest file. and <plugin path> are fully qualified

A virtual environment will be created for python at
<plugin Path>/VENV_FOLDER   (see constant section)

A version condition can be supplied using any standard (PEP 440) comparison:
==  !=  >=  <=  >  <  ~=  ===
Several conditions can be combined with commas and spaces are allowed e.g.
numpy>=1.2,<2.0
pkg[extra] >= 1, != 1.3
numpy==1.*

Rules:
1) If module is built-in it will be ignored
2) If module is already installed and no version is requested it will be ignored (it is not upgraded)
3) If module is not installed it will be installed
	3a) If no version - it will be installed at the latest version
	3b) If version is requested it will be installed at a version that meets the condition
	3c) If module is already installed at a version that meets the condition it will be ignored
	If the installed version does not meet the condition (or cannot be determined) it will be installed

4) Installed modules will be placed in site-packages of the virtual environment
5) site-packages will be placed at the front of sys.path when the venv python interpreter is used
therefore installed modules will take precedence over system modules

Install steps:
a) pip install --dry-run (with --report) of all modules that need installing - logs what will actually be installed
	including dependencies. The report is kept at <plugin Path>/venv/pipInstall_report.json
b) a single pip install -r of all of them, so pip resolves them together (consistent versions)
c) if a) or b) fails, the modules are installed one at a time so the others still install,
	and each failure is reported with pip's error message
"--user" is ignored (with a warning) - all modules are installed in the plugin venv

Exit Codes:

See class ExitCodes below.

Release notes:

See release-notes.md
"""


import subprocess
import sys
import logging

import re
import os
import argparse
import importlib
import json

from enum import Enum
from typing import Optional


# CONSTANTS
THIS_VERSION = '2.3.3'
VENV_FOLDER = 'venv'
MANIFEST_KEY = 'sbcPythonDependencies'
NAME_KEY = 'name'
PIP = 'pip'
LOGNAME = 'pipInstall2.log'
FALLBACK_LOGFILENAME = os.path.normpath(os.path.join(os.getcwd(), LOGNAME))
PATHFILENAME = 'plugin_path_change'
IMPORTTESTFILE = 'import_test.py'
REQFILENAME = 'pipInstall_requirements.txt'  # combined requirements written to the venv folder
REPORTFILENAME = 'pipInstall_report.json'  # pip --dry-run report written to the venv folder
pipQuiet = '-qq' #Reduce pip output
COMMENT_RE = re.compile(r'(^|\s)#.*$') # '#' at start or preceded by whitespace (pip rule)

if os.name == 'nt':  # Windows
	BIN_DIR = 'Scripts'
	PYTHON_VERSION = 'python.exe'
else:
	BIN_DIR = 'bin' # Linux
	PYTHON_VERSION = 'python'

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

class modType(Enum):
	BUILTIN = 'Builtin'
	INSTALLEDWITHVERSION = 'already Installed with version'
	INSTALLEDNOVERSION = 'already installed with no version number'
	PIPWITHVERSION = 'previously installed by Pip with version'
	PIPNOVERSION = 'previously installed by Pip with no Version number'
	NOTINSTALLED = 'not previously installed'

class Dependency:
	# Parsing uses packaging.requirements (PEP 508) so names, extras and version
	# conditions (including ranges e.g. >=1.2,<2.0) follow the same rules as pip
	# git+ urls are handled separately
	# A leading --user (e.g. --user dsf-python) is ignored - modules are always installed in the venv

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
		from packaging.requirements import Requirement, InvalidRequirement

		text = text.strip()
		dep = Dependency()

		if text.startswith('git+'):
			# Git dependency
			dep.package = text
			dep.comparator = None
			dep.version = None
			return dep

		if text.startswith('--user'):  # modules are always installed in the venv
			text = text[len('--user'):].strip()
			logger.warning(f'"--user" ignored for "{text}" - it will be installed in the plugin venv')

		try:
			req = Requirement(text)
		except InvalidRequirement as e:
			logger.error(f"Could not find package name in \"{text}\"\n{e}")
			return None

		if req.url:
			logger.error(f"Unsupported url form in \"{text}\" - use git+<url> instead")
			return None

		# Standard PyPi dependency
		extras = f'[{",".join(sorted(req.extras))}]' if req.extras else ''
		dep.package = req.name + extras
		dep.comparator = str(req.specifier)  # e.g. '>=1.2,<2.0' or '' if none
		dep.version = ''  # full condition is held in comparator

		return dep

def createVenvFiles(pythonFile, envPath):
	"""
	Creates a .pth file that executes a small python script
	whenever the venv python interpreter is used.
	The script changes the sys.path order so
	the site-packages path is at the front of sys.path
	"""

	cmd = f'{pythonFile} -m site'
	request = runsubprocess(cmd)
	if request is False:
		logger.critical('Aborting: Failed to get site info')
		shutDown(ExitCodes.PYTHON_SITE_ERROR)
	sitePackagesPath = ''
	for line in request.splitlines():
		if ('site-packages' in line) and (envPath in line):
			sitePackagesPath = line.strip()
			sitePackagesPath = sitePackagesPath.replace('(', '')
			sitePackagesPath = sitePackagesPath.replace(')', '')
			sitePackagesPath = sitePackagesPath.replace("'", '')
			sitePackagesPath = sitePackagesPath.replace(',', '')
			logger.debug(f'Found site-packages at: {sitePackagesPath}')
			break

	# Create the path change file to ensure site-packages is at the front of sys.path
	pyfile = (
			f'''import sys\n'''
			f'''sys.path.remove('{sitePackagesPath}')\n'''
			f'''sys.path.insert(0, '{sitePackagesPath}')\n'''
			)

	#.pth file just imports the above file
	pthfile=f'''import {PATHFILENAME}\n'''

	file = os.path.normpath(os.path.join(sitePackagesPath , f'{PATHFILENAME}.py'))
	logger.debug(f'Creating path change file at: {file}')
	with open(file, 'w+') as f:
		f.write(pyfile)

	file = os.path.normpath(os.path.join(sitePackagesPath , f'{PATHFILENAME}.pth'))
	logger.debug(f'Creating pth file at: {file}')
	with open(file, 'w+') as f:
		f.write(pthfile)

	return sitePackagesPath

def createImportTestFile(sitePackagesPath):
	"""
	Creates a small python script that can be called to test if a module
	can be imported and get its version
	This is installed in the venv so we can call it before and after 
	the the install to check if the module is installed and its version
	"""

	importtestfile = (
	f'''import sys\n'''
	f'''\n\n'''
	f'''def importTest(m):\n'''
	f'''\ttry:\n'''
	f'''\t\tglobals()[m] = __import__(m)\n'''
	f'''\t\tresult = globals()[m].__version__\n'''
	f'''\t\treturn result, 'INSTALLEDWITHVERSION'\n'''
	f'''\texcept (AttributeError): # No version information\n'''
	f'''\t\tif globals()[m].__name__ == m: # Module is installed so treat it as a builtin\n'''
	f'''\t\t\treturn 'No version information', 'INSTALLEDNOVERSION'\n'''
	f'''\t\telse:\n'''
	f'''\t\t\treturn 'Attribute error with no name match', 'NOTINSTALLED'\n'''
	f'''\texcept (ImportError, ModuleNotFoundError):\n'''
	f'''\t\treturn 'Module not able to be imported', 'NOTINSTALLED'\n'''
	f'''\texcept Exception as e:\n'''
	f'''\t\treturn f'Exception trying to import module: {{e}}', 'NOTINSTALLED'\n'''
	f'''\n\n'''
	f'''m = sys.argv[1]\n'''\
	f'''result, resultType = importTest(m)\n'''
	f'''print(f'{{result}}, {{resultType}}')\n'''
	)

	file = os.path.normpath(os.path.join(sitePackagesPath , f'{IMPORTTESTFILE}'))
	logger.debug(f'Creating Import Test file at: {file}')
	with open(file, 'w+') as f:
		f.write(importtestfile)



def createLogger(progname):  # Create a custom logger so messages go to journalctl
	global logger
	logger = logging.getLogger(progname)
	logger.propagate = False
	# Create handler for console output
	c_handler = logging.StreamHandler()
	c_format = logging.Formatter('%(message)s')
	c_handler.setFormatter(c_format)
	logger.addHandler(c_handler)
	logger.setLevel(logging.INFO) #Initial Setting


def createLogfile(logfilename, fallback_logfilename): 
	global logger
	filehandler = None
	for handler in logger.handlers:
		if handler.__class__.__name__ == "FileHandler":
			filehandler = handler
			break # There is only ever one
	
	if filehandler != None:  #  Get rid of it
		filehandler.flush()
		filehandler.close()
		logger.removeHandler(filehandler)
	try:
		f_handler = logging.FileHandler(logfilename, mode='w', encoding='utf-8')
	except: # Could be permission issue etc
		f_handler = logging.FileHandler(fallback_logfilename, mode='w', encoding='utf-8')
		logfilename = fallback_logfilename

	f_format = logging.Formatter('%(message)s')
	f_handler.setFormatter(f_format)
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

	if dep is None:
		shutDown(ExitCodes.INVALID_DEPENDENCY)
	
	logger.debug(f'Parsed dependency: package="{dep.package}", comparator="{dep.comparator}"')

	if dep.comparator is None or dep.comparator == '':
		dep.comparator = 'None'
		dep.version = ''

	return dep.package, dep.comparator ,dep.version


def runsubprocess(cmd):
	try:
		result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True)
		if result.returncode != 0:
			if str(result.stderr) != '' and 'Error' in str(result.stderr):
				logger.info(f'Possible install failure: {cmd}')
				logger.info(f'Error = {result.stderr}')
				logger.info(f'Output = {result.stdout}')
				return False
		return result.stdout
	except subprocess.CalledProcessError as e1:
		logger.debug(f'ProcessError -- \n{e1}')
	except OSError as e2:
		logger.info(f'OSError -- \n{e2}')
	return False


def createPythonEnv(envPath):
	"""
	Uses --clear so no need to check pythonFile existence
	pythonFile = os.path.normpath(os.path.join(envPath, BIN_DIR, PYTHON_VERSION))
	if os.path.isfile(pythonFile):  # No need to recreate
		return
	"""
	# Create a new virtual environment with updated pip
	cmd = f'{PYTHON_VERSION} -m venv {envPath} --clear --system-site-packages --upgrade-deps'
	logger.info(f'Creating Python Virtual Environment at:\n{envPath}')
	result = runsubprocess(cmd)
	if result != '':
		logger.critical(f'Problem creating Virtual Environment\n{result}')
		shutDown(ExitCodes.PROBLEM_CREATING_VENV)
	return


def importPackaging():
	try:
		import packaging.requirements, packaging.markers, packaging.specifiers
		return True, ''
	except ImportError as e:
		return False, str(e)

def checkPackaging(pythonFile, sitePath):
	"""
	packaging is used to parse modules, markers and version conditions
	If it is not available in the system python, install it into the venv
	and add the venv site-packages to the end of this program's sys.path
	"""
	ok, err = importPackaging()
	if ok:
		return
	logger.info(f'The python "packaging" module is not available ({err}) - installing it into the venv')
	# --ignore-installed so a copy is put in the venv even if the venv can see another one
	cmd = f'{pythonFile} -m {PIP} install --ignore-installed packaging {pipQuiet}'
	installed, out, perr = runPip(cmd)
	if installed:
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
	with open(mFile) as jsonfile:
		try:
			config = json.load(jsonfile)
		except ValueError as e:
			logger.critical(f'"{mFile}" is not a properly formatted json file\n{e}')
			shutDown(ExitCodes.MANIFEST_ERROR)

	mList = [stripComment(m) for m in config[MANIFEST_KEY]]
	mList = [m for m in mList if m != '']  # drop blank and comment-only entries
	if mList and mList[0] == '--verbose':
		verbose = True
		mList = mList[1:]  # Remove the verbose flag
	else:
		verbose = False

	pluginname = config[NAME_KEY]

	return mList, verbose , pluginname

def stripComment(entry):
	# Remove trailing comment (pip rule: '#' at start or preceded by whitespace)
	return COMMENT_RE.sub('', entry).strip()

def checkForRequirementsFiles(moduleList, pluginPath):
	updatedModuleList = []
	for module in moduleList:
		logger.debug(f'Checking module entry: {module}')
		if module.endswith('.txt'):
			# It's a requirements file
			reqfile = os.path.normpath(os.path.join(pluginPath,'dsf', module))
			if not os.path.isfile(reqfile):
				logger.critical(f'Requirements file "{module}" was not found at:\n{reqfile}')
				shutDown(ExitCodes.REQUIREMENTS_FILE_NOT_FOUND)
			logger.debug(f'Processing requirements file: {reqfile}')
			with open(reqfile, 'r') as f:
				for line in f:
					line = stripComment(line)
					if line == '':
						continue  # skip blank lines and comment-only lines
					updatedModuleList.append(line)
		else:
			updatedModuleList.append(module)
	return updatedModuleList

def applyEnvironmentMarkers(moduleList):
	# Handle PEP 508 environment markers e.g. picamera2; sys_platform == "linux"
	# Entries whose marker does not apply to this platform are dropped
	updatedModuleList = []
	for module in moduleList:
		if ';' not in module:
			updatedModuleList.append(module)
			continue
		req, marker = module.split(';', 1)
		req = req.strip()
		marker = marker.strip()
		try:
			from packaging.markers import Marker
			if not Marker(marker).evaluate():
				logger.info(f'Skipping "{module}" - marker does not apply to this platform')
				continue
			logger.debug(f'Marker "{marker}" applies - using "{req}"')
		except Exception as e:
			logger.warning(f'Could not evaluate marker in "{module}": {e} - installing "{req}" anyway')
		updatedModuleList.append(req)
	return updatedModuleList	


def getFreezeList(pythonFile) -> str:
	cmd = f'{pythonFile} -m {PIP} freeze --all {pipQuiet}' # Gives version prefixed by ==
	request = runsubprocess(cmd)
	if request is False:
		logger.critical('Aborting: Failed to get pip list')
		shutDown(ExitCodes.PIP_LIST_ERROR)
	# Normalise to lower case and underscore because installation names can vary
	# e.g. pyOpenSSL vs py_openssl could be installed by pyopenssl
	
	request = request.lower()
	request = request.replace('-', '_')

	return request

def getModuleVersion(m, pythonFile, sitePath, freezeList):
	# Remove any extras (stuff in square brackets)
	regex = r'(\[(.*?)\])'
	result = re.findall(regex, m, flags=re.IGNORECASE)
	if result:
		result = list(result[0])  # Convert tuple to list
		m = m.replace(str(result[0]),'')
	# SRS Swap import test with pip freeze test - makes more sense

	#Also check if module is installed in pip
	#Sometimes module cannot be imported with same name as pip package
	underscore_m = m.replace('-','_')
	freeze_m = underscore_m.lower() #  freezeList was normalized this way

	# Is the module already installed by PIP
	regex = f'^{freeze_m}==(.+)$' # format used for freeze
	result = re.findall(regex, freezeList, flags=re.MULTILINE)

	if result:  # The module exists
		if result[0] != '':  # version number found
			logger.debug(f'Pip: Version number "{result[0]}" was found for module "{m}"')
			return result[0], modType.PIPWITHVERSION.value
		else:
			logger.debug(f'Pip: Module "{m}" exists but does not have a version number.')
			return 'None', modType.PIPNOVERSION.value
	else:
		logger.debug(f'Pip: Module "{m}" was not found')

	# Check if module is a built-in
	if (underscore_m in sys.builtin_module_names): # Returns compiled modules. Will miss some std modules
		logger.debug(f'Module {m} is built-in')
		return 'None', modType.BUILTIN.value
			
	cmd = f'{pythonFile} {sitePath}/{IMPORTTESTFILE} {underscore_m}'
	request = runsubprocess(cmd)

	if not isinstance(request, str):
		logger.info(f'Unexpected type for import test result: {type(request)}')
		logger.info(f'Import test result for module "{m}" was ==> \n{request}')
	else:
		lines = request.splitlines()
		last_line = lines[-1] # Get last line only
		last_line = last_line.split(',')#comma separated values as list
		result = last_line[0].strip()
		resultType = last_line[1].strip()
		
		#Check if module can be imported (i.e. is installed)
		if  resultType == 'INSTALLEDWITHVERSION':
			logger.debug(f'Import: {m} imported with version {result}')
			return result, modType.INSTALLEDWITHVERSION.value
		elif resultType == 'INSTALLEDNOVERSION':
			logger.debug(f'Import: {m} imported (no version info)')
			return 'Installed', modType.INSTALLEDNOVERSION.value
		elif resultType == 'NOTINSTALLED':
			logger.debug(f'Import: {m} could not be imported because {result}')
	
	return 'None', modType.NOTINSTALLED.value


def runPip(cmd):
	# Run a pip command without raising - returns (ok, stdout, stderr)
	logger.debug(f'Running ==> {cmd}')
	try:
		result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
	except OSError as e:
		return False, '', str(e)
	return result.returncode == 0, result.stdout, result.stderr

def pipErrors(stderr):
	# Just the ERROR lines from pip output (or everything if there are none)
	lines = [line for line in stderr.splitlines() if line.startswith('ERROR')]
	return '\n'.join(lines) if lines else stderr.strip()

def requestString(mod, comp, val):
	return mod if comp == 'None' else f'{mod}{comp}{val}'

def installModule(mod, comp, val, pythonFile):
	request = requestString(mod, comp, val)

	logger.info(f'\nAttempting install of: {request}\n')

	cmd = f'{pythonFile} -m {PIP} install "{request}" {pipQuiet}'
	ok, out, err = runPip(cmd)

	if not ok:  # module could not be installed
		logger.info(f'Module: {request} could not be installed\n{pipErrors(err)}')
		return False
	logger.debug(f'Result was ==> \n{out}')
	return True

def dryRun(requests, pythonFile, venvPath):
	"""
	Write the requests to a requirements file and ask pip what it would install
	Logs the planned installs (requested modules and their dependencies)
	Returns (ok, reqfile)
	"""
	reqfile = os.path.normpath(os.path.join(venvPath, REQFILENAME))
	reportfile = os.path.normpath(os.path.join(venvPath, REPORTFILENAME))
	with open(reqfile, 'w') as f:
		f.write('\n'.join(requests) + '\n')
	logger.debug(f'Requirements written to {reqfile}:\n' + '\n'.join(requests))

	cmd = f'{pythonFile} -m {PIP} install --dry-run --report "{reportfile}" -r "{reqfile}" {pipQuiet}'
	ok, out, err = runPip(cmd)
	if not ok:
		logger.info(f'Dry run failed - pip could not resolve the requested modules together:\n{pipErrors(err)}')
		return False, reqfile

	try:
		with open(reportfile) as f:
			items = json.load(f).get('install', [])
	except (OSError, ValueError) as e:
		logger.info(f'Dry run succeeded but the report could not be read: {e}')
		return True, reqfile

	if not items:
		logger.info('Dry run: nothing needs to be installed - all requirements are already satisfied')
	else:
		logger.info('Dry run: pip will install the following:')
		for item in sorted(items, key=lambda x: (not x.get('requested', False), x.get('metadata', {}).get('name', '').lower())):
			md = item.get('metadata', {})
			kind = 'requested' if item.get('requested') else 'dependency'
			logger.info(f'\t{md.get("name", "?")}=={md.get("version", "?")}  ({kind})')
	logger.debug(f'Full dry run report: {reportfile}')
	return True, reqfile

def installRequirements(reqfile, pythonFile):
	# Install everything with a single pip call so pip resolves all modules together
	cmd = f'{pythonFile} -m {PIP} install -r "{reqfile}" {pipQuiet}'
	ok, out, err = runPip(cmd)
	if not ok:
		logger.info(f'Combined install failed:\n{pipErrors(err)}')
	else:
		logger.debug(f'Result was ==> \n{out}')
	return ok

def parseRequests(mList, pythonFile, sitePath,freezeList):
	modulerequests = []
	install_result, install_version = '', ''
	for module in mList:
		logger.debug(f'\nParsing request for module: {module}')
		mod_name, requested_version_comp, requested_version_val = parseVersion(module)
		current_version, current_type = getModuleVersion(mod_name, pythonFile, sitePath, freezeList)
		modulerequests.append([mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version])
	return modulerequests

def versionSatisfies(current_version, current_type, condition):
	# True if the installed version is known and meets the condition e.g. >=1.2,<2.0
	if current_type not in (modType.PIPWITHVERSION.value, modType.INSTALLEDWITHVERSION.value):
		return False
	try:
		from packaging.specifiers import SpecifierSet
		ok = SpecifierSet(condition).contains(current_version, prereleases=True)
	except Exception as e:
		logger.debug(f'Could not compare version "{current_version}" with "{condition}": {e}')
		return False
	logger.debug(f'Installed version "{current_version}" {"meets" if ok else "does not meet"} "{condition}"')
	return ok

def selectRequests(modulerequests):
	# Apply the rules - mark Builtin / Skipped and return the indices that need installing
	installedTypes = (modType.PIPWITHVERSION.value, modType.PIPNOVERSION.value,
				   modType.INSTALLEDWITHVERSION.value, modType.INSTALLEDNOVERSION.value)
	toInstall = []
	for idx, request in enumerate(modulerequests):
		mod_name, requested_version_comp, requested_version_val,\
		current_version, current_type, install_result, install_version \
		= unpackRequestList(request)

		if current_type == modType.BUILTIN.value:
			install_result = 'Builtin'
		elif current_type in installedTypes and requested_version_comp == 'None':
			install_result = 'Skipped'
		elif requested_version_comp != 'None' and versionSatisfies(current_version, current_type, requested_version_comp):
			install_result = 'Skipped'
		else:
			toInstall.append(idx)

		modulerequests[idx]= [mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version]
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
	oneAtATime = []

	if together:
		requests = [requestString(*modulerequests[i][0:3]) for i in together]
		logger.info('\n\nChecking what pip will install (dry run):')
		ok, reqfile = dryRun(requests, pythonFile, venvPath)
		if ok:
			logger.info('\nInstalling all modules together (single pip install -r):')
			ok = installRequirements(reqfile, pythonFile)
		if ok:
			for i in together:
				setResult(modulerequests, i, 'Succeeded')
		else:
			logger.info('\nFalling back to installing modules one at a time')
			oneAtATime = together

	for i in sorted(oneAtATime):
		mod_name, comp, val, current_version = modulerequests[i][0:4]
		install_ok = installModule(mod_name, comp, val, pythonFile)
		if install_ok:
			setResult(modulerequests, i, 'Succeeded')
		else:
			setResult(modulerequests, i, 'Failed')

	return modulerequests

def unpackRequestList(request):
	mod_name = request[0]
	requested_version_comp = request[1]
	requested_version_val = request[2]
	current_version = request[3]
	current_type = request[4]
	install_result = request[5]
	install_version = request[6]
	return mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version

def getUpdatedVersions(modulerequests,pythonFile, sitePath, freezeList):
	for idx, request in enumerate(modulerequests):
		mod_name, requested_version_comp, requested_version_val,\
		current_version, current_type, install_result, install_version \
		= unpackRequestList(request)

		#Rules to determine if we need to install
		if install_result == 'Succeeded':
			install_version, _ = getModuleVersion(mod_name, pythonFile, sitePath, freezeList)
		else:
			install_version = 'None'

		modulerequests[idx]= [mod_name, requested_version_comp, requested_version_val, current_version, current_type, install_result, install_version]

	return modulerequests

def sortResults(modulerequests):
	builtinList = []
	skippedList = []
	installedList = []
	failedList = []

	for req in modulerequests:
		mod_name, requested_version_comp, requested_version_val,\
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

def reportResults(builtinList, skippedList, installedList, failedList):
	logger.info('---------------------------------------')
	logger.info('Result Summary')
	logger.info('---------------------------------------')

	if (len(builtinList) > 0):
		logger.info('\nThese modules were Ignored (built-in):')
		for req in builtinList:
			mod_name, requested_version_comp, requested_version_val,\
			current_version, current_type, install_result, install_version \
			= unpackRequestList(req)
			if requested_version_comp == 'None':
				requested_version_comp = ''
			logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> Ignored')

	if (len(skippedList) > 0):	
		logger.info('\nThese modules were Skipped (Already installed - no version requested or version condition already met):')
		for req in skippedList:
			mod_name, requested_version_comp, requested_version_val,\
			current_version, current_type, install_result, install_version \
			= unpackRequestList(req)
			if current_version == 'None':
				current_version = ''
			if requested_version_comp == 'None':
				requested_version_comp = ''
			logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> {current_type} {current_version}')	

	if (len(installedList) > 0):
		logger.info('\nThese modules were successfully installed / updated:')
		for req in installedList:
			mod_name, requested_version_comp, requested_version_val,\
			current_version, current_type, install_result, install_version \
			= unpackRequestList(req)
			if requested_version_comp == 'None':
				requested_version_comp = ''
			if current_version == install_version:
				install_version = f'Reinstalled with same version'
			if current_version == 'None' or current_version == 'Installed':
				current_version = ''
			if install_version == 'None':	
				install_version = 'no Version'
			logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> was {current_type} {current_version}, now {install_version}')	

	if (len(failedList) > 0):
		logger.info('\nThese modules failed to install / update:')
		for req in failedList:		
			mod_name, requested_version_comp, requested_version_val,\
			current_version, current_type, install_result, install_version \
			= unpackRequestList(req)
			if requested_version_comp == 'None':
				requested_version_comp = ''
			if current_version == 'None':
				current_version = ''
			logger.info(f'\t{mod_name}{requested_version_comp}{requested_version_val} ==> was {current_type} {current_version}')

def shutDown(code):
	# logger does not exist yet if called while validating arguments
	out = logger.info if 'logger' in globals() else print
	out('---------------------------------------')
	out(f'Exiting with code {code}')
	out('---------------------------------------')
	sys.exit(code.value)


#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
def main(progName):
	global pipQuiet
	#  Validate calling arguments
	manifestFile, pluginPath = validateParams()
	venvPath = os.path.normpath(os.path.join(pluginPath, VENV_FOLDER))
	pythonFile = os.path.normpath(os.path.join(venvPath, BIN_DIR, PYTHON_VERSION))
	logfilename = os.path.normpath(os.path.join(venvPath, LOGNAME))

	#  Set up consolelogging so journalc can be used
	createLogger(progName)
	logger.info('---------------------------------------------------')
	logger.info(f'{progName} Version {THIS_VERSION} is attempting to install python modules')

	#  Create virtual environment
	createPythonEnv(venvPath)

	#add log file
	createLogfile(logfilename, FALLBACK_LOGFILENAME)
	
	# parse the manifestfile file
	verbose = True
	moduleList, verbose, pluginName = getModuleList(manifestFile)

	logger.info(f'Plugin name is : {pluginName}')

	#--verbose flag set adjust output level
	if verbose:
		logger.setLevel(logging.DEBUG)
		pipQuiet = ''

	# Ensure site-packages are at the front of sys.path in venv
	sitePath = createVenvFiles(pythonFile, venvPath)

	# python script to test if module is installed and get its version
	createImportTestFile(sitePath)

	# packaging is needed to parse the module list - installed into the venv if missing
	checkPackaging(pythonFile, sitePath)

	# Check moduleList for requirements files
	moduleList = checkForRequirementsFiles(moduleList, pluginPath)

	# Drop modules whose environment marker does not match this platform
	moduleList = applyEnvironmentMarkers(moduleList)

	# Resolve the requested modules to a name and version
	# Create a list of modules to instal and their current versions
	moduleRequests = []
	logger.info('\n\nChecking installed versions before install:')
	freezeList = getFreezeList(pythonFile) # Get initial freeze list
	moduleRequests = parseRequests(moduleList, pythonFile, sitePath,freezeList)

	# Process the requests and install modules as required
	moduleRequests = processRequests(moduleRequests, pythonFile, venvPath)

	logger.info('\n\nChecking installed versions after install:')	
	freezeList = getFreezeList(pythonFile)  # Get updated freeze list after parsing requests
	moduleRequests = getUpdatedVersions(moduleRequests,pythonFile, sitePath,freezeList)	


	# Separate the results into lists for reporting
	builtinList = []
	skippedList = []
	installedList = []
	failedList = []

	builtinList,skippedList,installedList,failedList = sortResults(moduleRequests)	


	# Report the results
	reportResults(builtinList, skippedList, installedList, failedList)

	if len(failedList) > 0:
		logger.info('---------------------------------------')
		logger.info('Some modules failed to install')
		logger.info('---------------------------------------')
		shutDown(ExitCodes.FAILED_TO_INSTALL_MODULE)

	logger.info('---------------------------------------')
	logger.info('All modules were successfully installed')
	logger.info('---------------------------------------')
	shutDown(ExitCodes.SUCCESS)

#-------------------------------------------------------------------------------

if __name__ == "__main__":  # Do not run anything below if the file is imported by another program
	programName = os.path.basename(sys.argv[0])
	main(programName)
