# -*- coding: utf-8 -*-

# stdlib
from __future__ import with_statement
import getpass
import gzip
import math
import os
import re
import shutil
import subprocess as sp
import sys
import tempfile
import textwrap
import traceback
from encodings.aliases import aliases
from hashlib import md5
from time import sleep, strftime, time
if sys.platform == "darwin":
	from platform import mac_ver
	from thread import start_new_thread
elif sys.platform == "win32":
	from ctypes import windll
	from win32com.shell import shell
	import pythoncom
	import win32con

# 3rd party
if sys.platform == "win32":
	import pywintypes
	import win32api

# custom
import CGATS
import ICCProfile as ICCP
import colormath
import config
import defaultpaths
import localization as lang
import wexpect
from argyll_cgats import (add_options_to_ti3, extract_fix_copy_cal, ti3_to_ti1, 
						  vcgt_to_cal, verify_cgats)
from argyll_instruments import instruments as all_instruments, remove_vendor_names
from argyll_names import (names as argyll_names, altnames as argyll_altnames, 
						  optional as argyll_optional, viewconds, intents)
from config import (autostart, autostart_home, script_ext, defaults, enc, exe,
					exe_ext, fs_enc, getcfg, geticon, get_ccxx_testchart,
					get_data_path, get_verified_path, isapp, isexe,
					is_ccxx_testchart, profile_ext, pydir, setcfg, writecfg)
from debughelpers import handle_error
if sys.platform not in ("darwin", "win32"):
	from defaultpaths import (iccprofiles_home, iccprofiles_display_home, 
							  xdg_config_home, xdg_config_dirs)
from edid import WMIError, get_edid
from log import log, safe_print
from meta import name as appname, version
from options import ascii, debug, test, test_require_sensor_cal, verbose
from ordereddict import OrderedDict
from trash import trash
from util_io import Files, StringIOu as StringIO
from util_list import intlist
if sys.platform == "darwin":
	from util_mac import (mac_app_activate, mac_terminal_do_script, 
						  mac_terminal_set_colors, osascript)
elif sys.platform == "win32":
	import util_win
else:
	try:
		import colord
	except ImportError:
		colord = None
from util_os import getenvu, is_superuser, putenvu, quote_args, which
from util_str import safe_str, safe_unicode
from wxaddons import wx
from wxwindows import ConfirmDialog, InfoDialog, ProgressDialog, SimpleTerminal
from wxDisplayAdjustmentFrame import DisplayAdjustmentFrame
import wx.lib.delayedresult as delayedresult

INST_CAL_MSGS = ["Do a reflective white calibration",
				 "Do a transmissive white calibration",
				 "Do a transmissive dark calibration",
				 "Place the instrument on its reflective white reference",
				 "Click the instrument on its reflective white reference",
				 "Place the instrument in the dark",
				 "Place cap on the instrument",  # i1 Pro
				 "place on the white calibration reference",  # i1 Pro
				 "Set instrument sensor to calibration position",  # ColorMunki
				 "Place the instrument on its transmissive white source",
				 "Use the appropriate tramissive blocking",
				 "Change filter on instrument to"]
USE_WPOPEN = 0

keycodes = {wx.WXK_NUMPAD0: ord("0"),
			wx.WXK_NUMPAD1: ord("1"),
			wx.WXK_NUMPAD2: ord("2"),
			wx.WXK_NUMPAD3: ord("3"),
			wx.WXK_NUMPAD4: ord("4"),
			wx.WXK_NUMPAD5: ord("5"),
			wx.WXK_NUMPAD6: ord("6"),
			wx.WXK_NUMPAD7: ord("7"),
			wx.WXK_NUMPAD8: ord("8"),
			wx.WXK_NUMPAD9: ord("9"),
			wx.WXK_NUMPAD_ADD: ord("+"),
			wx.WXK_NUMPAD_ENTER: ord("\n"),
			wx.WXK_NUMPAD_EQUAL: ord("="),
			wx.WXK_NUMPAD_DIVIDE: ord("/"),
			wx.WXK_NUMPAD_MULTIPLY: ord("*"),
			wx.WXK_NUMPAD_SUBTRACT: ord("-")}


def Property(func):
	return property(**func())


def check_argyll_bin(paths=None):
	""" Check if the Argyll binaries can be found. """
	prev_dir = None
	for name in argyll_names:
		exe = get_argyll_util(name, paths)
		if not exe:
			if name in argyll_optional:
				continue
			return False
		cur_dir = os.path.dirname(exe)
		if prev_dir:
			if cur_dir != prev_dir:
				if verbose: safe_print("Warning - the Argyll executables are "
									   "scattered. They should be in the same "
									   "directory.")
				return False
		else:
			prev_dir = cur_dir
	if verbose >= 3: safe_print("Argyll binary directory:", cur_dir)
	if debug: safe_print("[D] check_argyll_bin OK")
	if debug >= 2:
		if not paths:
			paths = getenvu("PATH", os.defpath).split(os.pathsep)
			argyll_dir = (getcfg("argyll.dir") or "").rstrip(os.path.sep)
			if argyll_dir:
				if argyll_dir in paths:
					paths.remove(argyll_dir)
				paths = [argyll_dir] + paths
		safe_print("[D] Searchpath:\n  ", "\n  ".join(paths))
	return True


def check_create_dir(path):
	"""
	Try to create a directory and show an error message on failure.
	"""
	if not os.path.exists(path):
		try:
			os.makedirs(path)
		except Exception, exception:
			return Error(lang.getstr("error.dir_creation", path) + "\n\n" + 
						 safe_unicode(exception))
	if not os.path.isdir(path):
		return Error(lang.getstr("error.dir_notdir", path))
	return True


def check_cal_isfile(cal=None, missing_msg=None, notfile_msg=None, 
					 silent=False):
	"""
	Check if a calibration file exists and show an error message if not.
	"""
	if not silent:
		if not missing_msg:
			missing_msg = lang.getstr("error.calibration.file_missing", cal)
		if not notfile_msg:
			notfile_msg = lang.getstr("error.calibration.file_notfile", cal)
	return check_file_isfile(cal, missing_msg, notfile_msg, silent)


def check_profile_isfile(profile_path=None, missing_msg=None, 
						 notfile_msg=None, silent=False):
	"""
	Check if a profile exists and show an error message if not.
	"""
	if not silent:
		if not missing_msg:
			missing_msg = lang.getstr("error.profile.file_missing", 
									  profile_path)
		if not notfile_msg:
			notfile_msg = lang.getstr("error.profile.file_notfile", 
									  profile_path)
	return check_file_isfile(profile_path, missing_msg, notfile_msg, silent)


def check_file_isfile(filename, missing_msg=None, notfile_msg=None, 
					  silent=False):
	"""
	Check if a file exists and show an error message if not.
	"""
	if not os.path.exists(filename):
		if not silent:
			if not missing_msg:
				missing_msg = lang.getstr("file.missing", filename)
			return Error(missing_msg)
		return False
	if not os.path.isfile(filename):
		if not silent:
			if not notfile_msg:
				notfile_msg = lang.getstr("file.notfile", filename)
			return Error(notfile_msg)
		return False
	return True


def check_set_argyll_bin():
	"""
	Check if Argyll binaries can be found, otherwise let the user choose.
	"""
	if check_argyll_bin():
		return True
	else:
		return set_argyll_bin()


def get_argyll_util(name, paths=None):
	""" Find a single Argyll utility. Return the full path. """
	if not paths:
		paths = getenvu("PATH", os.defpath).split(os.pathsep)
		argyll_dir = (getcfg("argyll.dir") or "").rstrip(os.path.sep)
		if argyll_dir:
			if argyll_dir in paths:
				paths.remove(argyll_dir)
			paths = [argyll_dir] + paths
	elif verbose >= 4:
		safe_print("Info: Searching for", name, "in", os.pathsep.join(paths))
	exe = None
	for path in paths:
		for altname in argyll_altnames[name]:
			exe = which(altname + exe_ext, [path])
			if exe:
				break
		if exe:
			break
	if verbose >= 4:
		if exe:
			safe_print("Info:", name, "=", exe)
		else:
			safe_print("Info:", "|".join(argyll_altnames[name]), 
					   "not found in", os.pathsep.join(paths))
	return exe


def get_argyll_utilname(name, paths=None):
	""" Find a single Argyll utility. Return the basename without extension. """
	exe = get_argyll_util(name, paths)
	if exe:
		exe = os.path.basename(os.path.splitext(exe)[0])
	return exe


def get_argyll_version(name, silent=False):
	"""
	Determine version of a certain Argyll utility.
	
	"""
	argyll_version = [0, 0, 0]
	if (silent and check_argyll_bin()) or (not silent and 
										   check_set_argyll_bin()):
		cmd = get_argyll_util(name)
		if sys.platform == "win32":
			startupinfo = sp.STARTUPINFO()
			startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = sp.SW_HIDE
		else:
			startupinfo = None
		p = sp.Popen([cmd.encode(fs_enc)], stdin=sp.PIPE, stdout=sp.PIPE, 
					 stderr=sp.STDOUT, startupinfo=startupinfo)
		for i, line in enumerate((p.communicate()[0] or "").splitlines()):
			if isinstance(line, basestring):
				line = line.strip()
				if i == 0 and "version" in line.lower():
					argyll_version_string = line[line.lower().find("version")+8:]
					argyll_version = re.findall("(\d+|[^.\d]+)", 
												argyll_version_string)
					for i, v in enumerate(argyll_version):
						try:
							argyll_version[i] = int(v)
						except ValueError:
							pass
					break
	return argyll_version


def parse_argument_string(args):
	""" Parses an argument string and returns a list of arguments. """
	return [arg.strip('"\'') for arg in re.findall('(?:^|\s+)(-[^\s]+|["\'][^"\']+?["\']|\S+)', args)]


def get_options_from_args(dispcal_args=None, colprof_args=None):
	"""
	Extract options used for dispcal and colprof from argument strings.
	"""
	re_options_dispcal = [
		"[moupHV]",
		"d\d+(?:,\d+)?",
		"[cv]\d+",
		"q(?:%s)" % "|".join(config.valid_values["calibration.quality"]),
		"y(?:%s)" % "|".join(filter(None, config.valid_values["measurement_mode"])),
		"[tT](?:\d+(?:\.\d+)?)?",
		"w\d+(?:\.\d+)?,\d+(?:\.\d+)?",
		"[bfakABF]\d+(?:\.\d+)?",
		"(?:g(?:240|709|l|s)|[gG]\d+(?:\.\d+)?)",
		"[pP]\d+(?:\.\d+)?,\d+(?:\.\d+)?,\d+(?:\.\d+)?",
		'X(?:\s*\d+|\s+["\'][^"\']+?["\'])',  # Argyll >= 1.3.0 colorimeter correction matrix / Argyll >= 1.3.4 calibration spectral sample
		"I[bw]{,2}"  # Argyll >= 1.3.0 drift compensation
	]
	re_options_colprof = [
		"q[lmh]",
		"a(?:%s)" % "|".join(config.valid_values["profile.type"]),
		'[sSMA]\s+["\'][^"\']+?["\']',
		"[cd](?:%s)" % "|".join(viewconds),
		"[tT](?:%s)" % "|".join(intents)
	]
	options_dispcal = []
	options_colprof = []
	if dispcal_args:
		options_dispcal = re.findall(" -(" + "|".join(re_options_dispcal) + 
									 ")", " " + dispcal_args)
	if colprof_args:
		options_colprof = re.findall(" -(" + "|".join(re_options_colprof) + 
									 ")", " " + colprof_args)
	return options_dispcal, options_colprof

def get_options_from_cprt(cprt):
	"""
	Extract options used for dispcal and colprof from profile copyright.
	"""
	if not isinstance(cprt, unicode):
		if isinstance(cprt, (ICCP.TextDescriptionType, 
							 ICCP.MultiLocalizedUnicodeType)):
			cprt = unicode(cprt)
		else:
			cprt = unicode(cprt, fs_enc, "replace")
	dispcal_args = cprt.split(" dispcal ")
	colprof_args = None
	if len(dispcal_args) > 1:
		dispcal_args[1] = dispcal_args[1].split(" colprof ")
		if len(dispcal_args[1]) > 1:
			colprof_args = dispcal_args[1][1]
		dispcal_args = dispcal_args[1][0]
	else:
		dispcal_args = None
		colprof_args = cprt.split(" colprof ")
		if len(colprof_args) > 1:
			colprof_args = colprof_args[1]
		else:
			colprof_args = None
	return dispcal_args, colprof_args


def get_options_from_cal(cal):
	if not isinstance(cal, CGATS.CGATS):
		cal = CGATS.CGATS(cal)
	if not cal or not "ARGYLL_DISPCAL_ARGS" in cal[0] or \
	   not cal[0].ARGYLL_DISPCAL_ARGS:
		return [], []
	dispcal_args = cal[0].ARGYLL_DISPCAL_ARGS[0].decode("UTF-7", "replace")
	return get_options_from_args(dispcal_args)


def get_options_from_profile(profile):
	""" Try and get options from profile. First, try the 'targ' tag and 
	look for the special dispcalGUI sections 'ARGYLL_DISPCAL_ARGS' and
	'ARGYLL_COLPROF_ARGS'. If either does not exist, fall back to the 
	copyright tag (dispcalGUI < 0.4.0.2) """
	if not isinstance(profile, ICCP.ICCProfile):
		profile = ICCP.ICCProfile(profile)
	dispcal_args = None
	colprof_args = None
	if "targ" in profile.tags:
		ti3 = CGATS.CGATS(profile.tags.targ)
		if len(ti3) > 1 and "ARGYLL_DISPCAL_ARGS" in ti3[1] and \
		   ti3[1].ARGYLL_DISPCAL_ARGS:
			dispcal_args = ti3[1].ARGYLL_DISPCAL_ARGS[0].decode("UTF-7", 
																"replace")
		if "ARGYLL_COLPROF_ARGS" in ti3[0] and \
		   ti3[0].ARGYLL_COLPROF_ARGS:
			colprof_args = ti3[0].ARGYLL_COLPROF_ARGS[0].decode("UTF-7", 
																"replace")
	if not dispcal_args and "cprt" in profile.tags:
		dispcal_args = get_options_from_cprt(profile.getCopyright())[0]
	if not colprof_args and "cprt" in profile.tags:
		colprof_args = get_options_from_cprt(profile.getCopyright())[1]
	return get_options_from_args(dispcal_args, colprof_args)


def get_options_from_ti3(ti3):
	if not isinstance(ti3, CGATS.CGATS):
		ti3 = CGATS.CGATS(ti3)
	dispcal_args = None
	colprof_args = None
	if len(ti3) > 1 and "ARGYLL_DISPCAL_ARGS" in ti3[1] and \
	   ti3[1].ARGYLL_DISPCAL_ARGS:
		dispcal_args = ti3[1].ARGYLL_DISPCAL_ARGS[0].decode("UTF-7", 
															"replace")
	if "ARGYLL_COLPROF_ARGS" in ti3[0] and \
	   ti3[0].ARGYLL_COLPROF_ARGS:
		colprof_args = ti3[0].ARGYLL_COLPROF_ARGS[0].decode("UTF-7", 
															"replace")
	return get_options_from_args(dispcal_args, colprof_args)


def get_arg(argmatch, args):
	""" Return first found entry beginning with the argmatch string or None """
	for arg in args:
		if arg.startswith(argmatch):
			return arg


def make_argyll_compatible_path(path):
	"""
	Make the path compatible with the Argyll utilities.
	
	This is currently only effective under Windows to make sure that any 
	unicode 'division' slashes in the profile name are replaced with 
	underscores.
	
	"""
	###Under Linux if the encoding is not UTF-8 everything is 
	###forced to ASCII to prevent problems when installing profiles.
	##if ascii or (sys.platform not in ("darwin", "win32") and 
				 ##fs_enc.upper() not in ("UTF8", "UTF-8")):
		##make_compat_enc = "ASCII"
	##else:
	make_compat_enc = fs_enc
	skip = -1
	if re.match(r'\\\\\?\\', path, re.I):
		# Don't forget about UNC paths: 
		# \\?\UNC\Server\Volume\File
		# \\?\C:\File
		skip = 2
	parts = path.split(os.path.sep)
	for i, part in enumerate(parts):
		if i > skip:
			parts[i] = unicode(part.encode(make_compat_enc, "safe_asciize"), 
							   make_compat_enc).replace("/", "_").replace("?", 
																		  "_")
	return os.path.sep.join(parts)


def normalize_manufacturer_name(vendor):
	""" Strip certain redundant info from vendor name """
	subs = {"Acer .+": "Acer",
			"Apple .+": "Apple",
			"Compaq .+": "Compaq",
			"Daewoo .+": "Daewoo",
			"Eizo .+": "EIZO",
			"Envision .+": "Envision",
			"Fujitsu( Siemens|) .+": "Fujitsu\\1",
			"Gateway .+": "Gateway",
			"Goldstar .+": "LG",  # GoldStar no longer exists
			"HannStar .+": "HannStar",
			"Hitachi .+": "Hitachi",
			"Lenovo .+": "Lenovo",
			"Liyama .+": "Iiyama",  # Typo in pnp.ids
			"Mitsubishi .+": "Mitsubishi",
			"Panasonic .+": "Panasonic",
			"Philips .+": "Philips",
			"Proview .+": "Proview",
			"Samsung .+": "Samsung",
			"Tatung .+": "Tatung",
			"Zalman .+": "Zalman"}
	for sub in subs.iteritems():
		vendor = re.sub(sub[0], sub[1], vendor)
	strings = ["AG", "KG", "[Ii][Nn][Cc]", "Asia", "Germany", "Spain",
			   "(?:North\s+)?America","\w?mbH", "[Cc]o(?:mpany)?", "CO(?:MPANY)?",
			   "[Ll]\.?[Tt]\.?[Dd]\.?(?:[Aa]\.?)?", "[Ll]imited", "LIMITED",
			   "CORP(?:ORATION)?", "[Cc]orp(?:oration)?", "[Ii]nt'l", "L\.P",
			   "[Pp]\.?[Tt]\.?[EeYy]", "[Ss]\.?[Pp]?\.?[Aa]", "K\.?K\.?", "AB",
			   "[Ss]\.?[Rr]\.?[Ll]", "[Pp]\.?[Ll]\.?[Cc]", "P/?L", "[Nn]\.[Vv]",
			   "A[/.]?S", "[Bb]\.?[Vv]", "[Ss]\.?[Aa]\.?[Ss]",
			   "[Dd]\.?[Bb]\.?[Aa]", "LLC", "S\.?A", "Sdn", "Bhd", "I[Nn][Dd]",
			   "[Ii]nternational", "INTERNATIONAL",
			   "GmbH\s*&\s*Co(?:\.|mpany)?\s*KG", "M[Ff][Gg]"]
	previous = None
	while previous != vendor:
		previous = vendor
		vendor = re.sub("\s*\([^)]+\)\s*$", "", vendor)
		vendor = re.sub("([,.\s])\s*(?:%s)(?:[,.]+|\s*$)" % "|".join(strings),
					    "\\1", vendor).strip(",").strip()
	return vendor


def printcmdline(cmd, args=None, fn=None, cwd=None):
	"""
	Pretty-print a command line.
	"""
	if args is None:
		args = []
	if cwd is None:
		cwd = os.getcwdu()
	safe_print("  " + cmd, fn=fn)
	i = 0
	lines = []
	for item in args:
		ispath = False
		if item.find(os.path.sep) > -1:
			if os.path.dirname(item) == cwd:
				item = os.path.basename(item)
			ispath = True
		item = quote_args([item])[0]
		##if not item.startswith("-") and len(lines) and i < len(args) - 1:
			##lines[-1] += "\n      " + item
		##else:
		lines.append(item)
		i += 1
	for line in lines:
		safe_print(textwrap.fill(line, 80, expand_tabs = False, 
				   replace_whitespace = False, initial_indent = "    ", 
				   subsequent_indent = "      "), fn = fn)


def set_argyll_bin(parent=None):
	if parent and not parent.IsShownOnScreen():
		parent = None # do not center on parent if not visible
	defaultPath = os.path.sep.join(get_verified_path("argyll.dir"))
	dlg = wx.DirDialog(parent, lang.getstr("dialog.set_argyll_bin"), 
					   defaultPath=defaultPath, style=wx.DD_DIR_MUST_EXIST)
	dlg.Center(wx.BOTH)
	result = False
	while not result:
		result = dlg.ShowModal() == wx.ID_OK
		if result:
			path = dlg.GetPath().rstrip(os.path.sep)
			result = check_argyll_bin([path])
			if result:
				if verbose >= 3:
					safe_print("Setting Argyll binary directory:", path)
				setcfg("argyll.dir", path)
				writecfg()
				break
			else:
				not_found = []
				for name in argyll_names:
					if not get_argyll_util(name, [path]):
						not_found.append((" " + 
										  lang.getstr("or") + 
										  " ").join(filter(lambda altname: not "argyll" in altname, 
														   [altname + exe_ext 
														    for altname in 
															argyll_altnames[name]])))
				InfoDialog(parent, msg=path + "\n\n" + 
								   lang.getstr("argyll.dir.invalid", 
											   ", ".join(not_found)), 
						   ok=lang.getstr("ok"), 
						   bitmap=geticon(32, "dialog-error"))
		else:
			break
	dlg.Destroy()
	return result


def show_result_dialog(result, parent=None, pos=None):
	msg = safe_unicode(result)
	if not pos:
		pos=(-1, -1)
	if isinstance(result, Info):
		bitmap = geticon(32, "dialog-information")
	elif isinstance(result, Warning):
		bitmap = geticon(32, "dialog-warning")
	else:
		bitmap = geticon(32, "dialog-error")
	InfoDialog(parent, pos=pos, msg=msg, ok=lang.getstr("ok"), bitmap=bitmap, 
			   log=not isinstance(result, UnloggedError))


class Error(Exception):
	pass


class Info(UserWarning):
	pass


class UnloggedError(Error):
	pass


class Warn(UserWarning):
	pass


class FilteredStream():
	
	""" Wrap a stream and filter all lines written to it. """
	
	# Discard progress information like ... or *** or %
	discard = ""
	
	# If one of the triggers is contained in a line, skip the whole line
	triggers = ["Place instrument on test window",
				"key to continue",
				"key to retry",
				"key to take a reading",
				" or Q to "] + INST_CAL_MSGS
	
	substitutions = {" peqDE ": " previous pass DE ",
					 "patch ": "Patch ",
					 re.compile("Point (\\d+ Delta E)", re.I): " point \\1"}
	
	def __init__(self, stream, data_encoding=None, file_encoding=None,
				 errors="replace", discard=None, linesep_in="\r\n", 
				 linesep_out="\n", substitutions=None,
				 triggers=None):
		self.stream = stream
		self.data_encoding = data_encoding
		self.file_encoding = file_encoding
		self.errors = errors
		if discard is not None:
			self.discard = discard
		self.linesep_in = linesep_in
		self.linesep_out = linesep_out
		if substitutions is not None:
			self.substitutions = substitutions
		if triggers is not None:
			self.triggers = triggers
	
	def __getattr__(self, name):
		return getattr(self.stream, name)
	
	def write(self, data):
		""" Write data to stream, stripping all unwanted output.
		
		Incoming lines are expected to be delimited by linesep_in.
		
		"""
		if not data:
			return
		lines = []
		for line in data.split(self.linesep_in):
			if line and not re.sub(self.discard, "", line):
				line = ""
			write = True
			for trigger in self.triggers:
				if trigger.lower() in line.lower():
					write = False
					break
			if write:
				if self.data_encoding and not isinstance(line, unicode):
					line = line.decode(self.data_encoding, self.errors)
				for search, sub in self.substitutions.iteritems():
					line = re.sub(search, sub, line)
				if self.file_encoding:
					line = line.encode(self.file_encoding, self.errors)
				lines.append(line)
		if lines:
			self.stream.write(self.linesep_out.join(lines))


class GzipFileProper(gzip.GzipFile):

	"""
	Proper GZIP file implementation, where the optional filename in the
	header has directory components removed, and is converted to ISO 8859-1
	(Latin-1). On Windows, the filename will also be forced to lowercase.
	
	See RFC 1952 GZIP File Format Specification	version 4.3
	
	"""

	def _write_gzip_header(self):
		self.fileobj.write('\037\213')             # magic header
		self.fileobj.write('\010')                 # compression method
		fname = os.path.basename(self.name)
		if fname.endswith(".gz"):
			fname = fname[:-3]
		flags = 0
		if fname:
			flags = gzip.FNAME
		self.fileobj.write(chr(flags))
		gzip.write32u(self.fileobj, long(time()))
		self.fileobj.write('\002')
		self.fileobj.write('\377')
		if fname:
			if sys.platform == "win32":
				# Windows is case insensitive by default (although it can be
				# set to case sensitive), so according to the GZIP spec, we
				# force the name to lowercase
				fname = fname.lower()
			self.fileobj.write(fname.encode("ISO-8859-1", "replace")
							   .replace("?", "_") + '\000')

	def __enter__(self):
		return self

	def __exit__(self, type, value, tb):
		self.close()


class LineBufferedStream():
	
	""" Buffer lines and only write them to stream if line separator is 
		detected """
		
	def __init__(self, stream, data_encoding=None, file_encoding=None,
				 errors="replace", linesep_in="\r\n", linesep_out="\n"):
		self.buf = ""
		self.data_encoding = data_encoding
		self.file_encoding = file_encoding
		self.errors = errors
		self.linesep_in = linesep_in
		self.linesep_out = linesep_out
		self.stream = stream
	
	def __del__(self):
		self.commit()
	
	def __getattr__(self, name):
		return getattr(self.stream, name)
	
	def close(self):
		self.commit()
		self.stream.close()
	
	def commit(self):
		if self.buf:
			if self.data_encoding:
				self.buf = self.buf.decode(self.data_encoding, self.errors)
			if self.file_encoding:
				self.buf = self.buf.encode(self.file_encoding, self.errors)
			self.stream.write(self.buf)
			self.buf = ""
	
	def write(self, data):
		data = data.replace(self.linesep_in, "\n")
		if self.data_encoding and isinstance(data, unicode):
			data = data.encode(self.data_encoding)
		for char in data:
			if char == "\r":
				while self.buf and not self.buf.endswith(self.linesep_out):
					self.buf = self.buf[:-1]
			else:
				if char == "\n":
					self.buf += self.linesep_out
					self.commit()
				else:
					self.buf += char


class LineCache():
	
	""" When written to it, stores only the last n + 1 lines and
		returns only the last n non-empty lines when read. """
	
	def __init__(self, maxlines=1):
		self.clear()
		self.maxlines = maxlines
	
	def clear(self):
		self.cache = [""]
	
	def flush(self):
		pass
	
	def read(self, triggers=None):
		lines = [""]
		for line in self.cache:
			read = True
			if triggers:
				for trigger in triggers:
					if trigger.lower() in line.lower():
						read = False
						break
			if read and line:
				lines.append(line)
		return "\n".join(filter(lambda line: line, lines)[-self.maxlines:])
	
	def write(self, data):
		for char in data:
			if char == "\r":
				self.cache[-1] = ""
			elif char == "\n":
				self.cache.append("")
			else:
				self.cache[-1] += char
		self.cache = (filter(lambda line: line, self.cache[:-1]) + 
					  self.cache[-1:])[-self.maxlines - 1:]


class WPopen(sp.Popen):
	
	def __init__(self, *args, **kwargs):
		sp.Popen.__init__(self, *args, **kwargs)
		self._seekpos = 0
		self._stdout = kwargs["stdout"]
		self.after = None
		self.before = None
		self.exitstatus = None
		self.logfile_read = None
		self.match = None
		self.maxlen = 80
		self.timeout = 30
	
	def isalive(self):
		self.exitstatus = self.poll()
		return self.exitstatus is None
	
	def expect(self, patterns, timeout=-1):
		if not isinstance(patterns, list):
			patterns = [patterns]
		if timeout == -1:
			timeout = self.timeout
		if timeout is not None:
			end = time() + timeout
		while timeout is None or time() < end:
			self._stdout.seek(self._seekpos)
			buf = self._stdout.read()
			self._seekpos += len(buf)
			if not buf and not self.isalive():
				self.match = wexpect.EOF("End Of File (EOF) in expect() - dead child process")
				if wexpect.EOF in patterns:
					return self.match
				raise self.match
			if buf and self.logfile_read:
				self.logfile_read.write(buf)
			for pattern in patterns:
				if isinstance(pattern, basestring) and pattern in buf:
					offset = buf.find(pattern)
					self.after = buf[offset:]
					self.before = buf[:offset]
					self.match = buf[offset:offset + len(pattern)]
					return self.match
			sleep(.01)
		if timeout is not None:
			self.match = wexpect.TIMEOUT("Timeout exceeded in expect()")
			if wexpect.TIMEOUT in patterns:
				return self.match
			raise self.match
	
	def send(self, s):
		self.stdin.write(s)
		self._stdout.seek(self._seekpos)
		buf = self._stdout.read()
		self._seekpos += len(buf)
		if buf and self.logfile_read:
			self.logfile_read.write(buf)
	
	def terminate(self, force=False):
		sp.Popen.terminate(self)


class Worker(object):

	def __init__(self, owner=None):
		"""
		Create and return a new worker instance.
		"""
		self.owner = owner # owner should be a wxFrame or similar
		if sys.platform == "win32":
			self.data_encoding = aliases.get(str(windll.kernel32.GetACP()), 
											 "ascii")
		else:
			self.data_encoding = enc
		self.dispcal_create_fast_matrix_shaper = False
		self.dispread_after_dispcal = False
		self.finished = True
		self.interactive = False
		self.lastmsg_discard = re.compile("[\\*\\.]+")
		self.options_colprof = []
		self.options_dispcal = []
		self.options_dispread = []
		self.options_targen = []
		self.recent_discard = re.compile("^\\s*(?:Adjusted )?(Current|[Tt]arget) (?:Brightness|50% Level|white|(?:Near )?[Bb]lack|(?:advertised )?gamma) .+|^Gamma curve .+|^Display adjustment menu:|^Press|^\\d\\).+|^(?:1%|Black|Red|Green|Blue|White)\\s+=.+|^\\s*patch \\d+ of \\d+.*|^\\s*point \\d+.*|^\\s*Added \\d+/\\d+|[\\*\\.]+|\\s*\\d*%?", re.I)
		self.subprocess_abort = False
		self.sudo_availoptions = None
		self.auth_timestamp = 0
		self.tempdir = None
		self.thread_abort = False
		self.triggers = []
		self.clear_argyll_info()
		self.clear_cmd_output()
		self._pwdstr = ""
	
	def add_measurement_features(self, args):
		if not get_arg("-d", args):
			args += ["-d" + self.get_display()]
		if not get_arg("-c", args):
			args += ["-c%s" % getcfg("comport.number")]
		measurement_mode = getcfg("measurement_mode")
		instrument_features = self.get_instrument_features()
		if (measurement_mode and (measurement_mode != "p" or
								  self.get_instrument_name() == "ColorHug") and
			not instrument_features.get("spectral") and not get_arg("-y", args)):
				# Always specify -y for colorimeters (won't be read from .cal 
				# when updating)
				# Only ColorHug supports -yp parameter
				args += ["-y" + measurement_mode[0]]
		if getcfg("measurement_mode.projector") and \
		   instrument_features.get("projector_mode") and \
		   self.argyll_version >= [1, 1, 0] and not get_arg("-p", args):
			# Projector mode, Argyll >= 1.1.0 Beta
			args += ["-p"]
		if getcfg("measurement_mode.adaptive") and \
		   instrument_features.get("adaptive_mode") and \
		   (self.argyll_version[0:3] > [1, 1, 0] or (
			self.argyll_version[0:3] == [1, 1, 0] and 
			not "Beta" in self.argyll_version_string and 
			not "RC1" in self.argyll_version_string and 
			not "RC2" in self.argyll_version_string)) and not get_arg("-V", args):
			# Adaptive mode, Argyll >= 1.1.0 RC3
			args += ["-V"]
		if ((self.argyll_version <= [1, 0, 4] and not get_arg("-p", args)) or 
			(self.argyll_version > [1, 0, 4] and not get_arg("-P", args))):
			args += [("-p" if self.argyll_version <= [1, 0, 4] else "-P") + 
					 getcfg("dimensions.measureframe")]
		if getcfg("measure.darken_background") and not get_arg("-F", args):
			args += ["-F"]
		if getcfg("measurement_mode.highres") and \
		   instrument_features.get("highres_mode") and not get_arg("-H", args):
			args += ["-H"]
		if (self.instrument_can_use_ccxx() and
		    not is_ccxx_testchart() and not get_arg("-X", args)):
			# Use colorimeter correction?
			# Special case: Spectrometer (not needed) and ColorHug
			# (only sensible in factory or raw measurement mode)
			ccmx = getcfg("colorimeter_correction_matrix_file").split(":", 1)
			if len(ccmx) > 1 and ccmx[1]:
				ccmx = ccmx[1]
			else:
				ccmx = None
			if ccmx and (not ccmx.lower().endswith(".ccss") or
						 self.instrument_supports_ccss()):
				result = check_file_isfile(ccmx)
				if isinstance(result, Exception):
					return result
				try:
					cgats = CGATS.CGATS(ccmx)
				except CGATS.CGATSError, exception:
					safe_print("%s:" % ccmx, exception)
					instrument = None
				else:
					instrument = str(cgats.queryv1("INSTRUMENT") or "")
				if ((instrument and
					 self.get_instrument_name().lower().replace(" ", "") in
					 instrument.lower().replace(" ", "").replace("eye-one", "i1")) or
					ccmx.lower().endswith(".ccss")):
					tempdir = self.create_tempdir()
					if isinstance(tempdir, Exception):
						return tempdir
					ccmxcopy = os.path.join(tempdir, 
											os.path.basename(ccmx))
					if not os.path.isfile(ccmxcopy):
						try:
							# Copy ccmx to profile dir
							shutil.copyfile(ccmx, ccmxcopy) 
						except Exception, exception:
							return Error(lang.getstr("error.copy_failed", 
													 (ccmx, ccmxcopy)) + 
													 "\n\n" + 
													 safe_unicode(exception))
						result = check_file_isfile(ccmxcopy)
						if isinstance(result, Exception):
							return result
					args += ["-X"]
					args += [os.path.basename(ccmxcopy)]
		if (getcfg("drift_compensation.blacklevel") or 
			getcfg("drift_compensation.whitelevel")) and \
		   self.argyll_version >= [1, 3, 0] and not get_arg("-I", args):
			args += ["-I"]
			if getcfg("drift_compensation.blacklevel"):
				args[-1] += "b"
			if getcfg("drift_compensation.whitelevel"):
				args[-1] += "w"
		return True
	
	def instrument_can_use_ccxx(self):
		"""
		Return boolean whether the instrument in its current measurement mode
		can use a CCMX or CCSS colorimeter correction
		
		"""
		return (self.argyll_version >= [1, 3, 0] and
				not self.get_instrument_features().get("spectral") and
				(self.get_instrument_name() != "ColorHug" or
				 getcfg("measurement_mode") in ("F", "R")))
	
	@Property
	def pwd():
		def fget(self):
			return self._pwdstr[10:].ljust(int(math.ceil(len(self._pwdstr[10:]) / 4.0) * 4),
										  "=").decode("base64").decode("UTF-8")
		
		def fset(self, pwd):
			self._pwdstr = "/tmp/%s%s" % (md5(getpass.getuser()).hexdigest().encode("base64")[:5],
										  pwd.encode("UTF-8").encode("base64").rstrip("=\n"))
		
		return locals()
	
	def get_needs_no_sensor_cal(self):
		instrument_features = self.get_instrument_features()
		# TTBD/FIXME: Skipping of sensor calibration can't be done in
		# emissive mode (see Argyll source spectro/ss.c, around line 40)
		return instrument_features and \
			   (not instrument_features.get("sensor_cal") or 
			    (getcfg("allow_skip_sensor_cal") and 
			     self.dispread_after_dispcal and 
			     (instrument_features.get("skip_sensor_cal") or test) and 
				 self.argyll_version >= [1, 1, 0]))
	
	def check_display_conf_oy_compat(self, display_no):
		""" Check the screen configuration for oyranos-monitor compatibility 
		
		oyranos-monitor works off screen coordinates, so it will not handle 
		overlapping screens (like separate X screens, which will usually 
		have the same x, y coordinates)!
		So, oyranos-monitor can only be used if:
		- The wx.Display count is > 1 which means NOT separate X screens
		  OR if we use the 1st screen
		- The screens don't overlap
		
		"""
		oyranos = False
		if wx.Display.GetCount() > 1 or display_no == 1:
			oyranos = True
			for display_rect_1 in self.display_rects:
				for display_rect_2 in self.display_rects:
					if display_rect_1 is not display_rect_2:
						if display_rect_1.Intersects(display_rect_2):
							oyranos = False
							break
				if not oyranos:
					break
		return oyranos
	
	def check_instrument_calibration(self):
		msgs = self.recent.read()
		if (not getattr(self, "instrument_calibration_complete", False) and
			"Calibration complete" in msgs and
			"key to continue" in self.lastmsg.read()):
			self.instrument_calibration_complete = True
			wx.CallAfter(self.instrument_calibration_finish)
		elif (not getattr(self, "instrument_calibration_complete", False) and
			  (not getattr(self, "instrument_calibration_started", False) or
			   "Calibration failed" in msgs)):
			if "Calibration failed" in msgs:
				self.recent.clear()
			for calmsg in INST_CAL_MSGS:
				if calmsg in msgs or "Calibration failed" in msgs:
					self.instrument_calibration_started = True
					wx.CallAfter(self.do_instrument_calibration)
					break
	
	def do_instrument_calibration(self):
		self.progress_wnd.Pulse(" " * 4)
		self.progress_wnd.MakeModal(False)
		if self.get_instrument_name() == "ColorMunki":
			lstr ="instrument.calibrate.colormunki"
		else:
			lstr = "instrument.calibrate"
		dlg = ConfirmDialog(self.progress_wnd, msg=lang.getstr(lstr), 
							ok=lang.getstr("ok"), 
							cancel=lang.getstr("cancel"), 
							bitmap=geticon(32, "dialog-information"))
		dlg_result = dlg.ShowModal()
		dlg.Destroy()
		self.progress_wnd.MakeModal(True)
		if dlg_result != wx.ID_OK:
			self.abort_subprocess()
			return False
		self.progress_wnd.Pulse(lang.getstr("please_wait"))
		if self.safe_send(" "):
			self.progress_wnd.Pulse(lang.getstr("instrument.calibrating"))
	
	def abort_subprocess(self):
		self.subprocess_abort = True
		self.thread_abort = True
		delayedresult.startWorker(lambda result: None, 
								  self.quit_terminate_cmd)
	
	def instrument_calibration_finish(self):
		self.progress_wnd.Pulse(" " * 4)
		self.progress_wnd.MakeModal(False)
		dlg = ConfirmDialog(self.progress_wnd, msg=lang.getstr("instrument.place_on_screen"), 
							ok=lang.getstr("ok"), 
							cancel=lang.getstr("cancel"), 
							bitmap=geticon(32, "dialog-information"))
		dlg_result = dlg.ShowModal()
		dlg.Destroy()
		self.progress_wnd.MakeModal(True)
		if dlg_result != wx.ID_OK:
			self.abort_subprocess()
			return False
		self.safe_send(" ")
	
	def clear_argyll_info(self):
		"""
		Clear Argyll CMS version, detected displays and instruments.
		"""
		self.argyll_bin_dir = None
		self.argyll_version = [0, 0, 0]
		self.argyll_version_string = ""
		self._displays = []
		self.display_edid = []
		self.display_manufacturers = []
		self.display_names = []
		self.display_rects = []
		self.displays = []
		self.instruments = []
		self.lut_access = []

	def clear_cmd_output(self):
		"""
		Clear any output from the last run command.
		"""
		self.retcode = -1
		self.output = []
		self.errors = []
		self.recent = FilteredStream(LineCache(maxlines=3), self.data_encoding, 
									 discard=self.recent_discard,
									 triggers=self.triggers)
		self.lastmsg = FilteredStream(LineCache(), self.data_encoding, 
									  discard=self.lastmsg_discard,
									  triggers=self.triggers)

	def create_3dlut(self, profile_in, profile_out, apply_cal=True, intent="r",
					 bpc=True, format="3dl", size=17, input_bits=10,
					 output_bits=12, maxval=1.0):
		""" Create a 3D LUT from two profiles. """
		# .cube: http://doc.iridas.com/index.php/LUT_Formats
		# .3dl: http://www.kodak.com/US/plugins/acrobat/en/motion/products/look/UserGuide.pdf
		#       http://download.autodesk.com/us/systemdocs/pdf/lustre_color_management_user_guide.pdf
		
		for profile in (profile_in, profile_out):
			if (profile.profileClass != "mntr" or 
				profile.colorSpace != "RGB"):
				raise NotImplementedError(lang.getstr("profile.unsupported", 
													  (profile.profileClass, 
													   profile.colorSpace)))
		
		# Create input RGB values
		RGB_triplets = []
		seen = {}
		step = 1.0 / (size - 1)
		RGB_triplet = [0.0, 0.0, 0.0]
		# Set the fastest and slowest changing columns, from right to left
		if format == "3dl":
			columns = (0, 1, 2)
		else:
			columns = (2, 1, 0)
		for i in xrange(0, size):
			# Red
			RGB_triplet[columns[0]] = step * i
			for j in xrange(0, size):
				# Green
				RGB_triplet[columns[1]] = step * j
				for k in xrange(0, size):
					# Blue
					RGB_triplet[columns[2]] = step * k
					RGB_triplets.append(list(RGB_triplet))

		# Convert RGB triplets to list of strings
		for i, RGB_triplet in enumerate(RGB_triplets):
			RGB_triplets[i] = " ".join(str(n) for n in RGB_triplet)
		if debug:
			safe_print(len(RGB_triplets), "RGB triplets")
			safe_print("\n".join(RGB_triplets))
		
		# Setup xicclu
		xicclu = get_argyll_util("xicclu").encode(fs_enc)
		cwd = self.create_tempdir()
		if isinstance(cwd, Exception):
			raise cwd
		if sys.platform == "win32":
			startupinfo = sp.STARTUPINFO()
			startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = sp.SW_HIDE
		else:
			startupinfo = None

		pcs = "x"

		# Prepare 'input' profile
		profile_in.write(os.path.join(cwd, "profile_in.icc"))

		# Lookup RGB -> XYZ values through 'input' profile using xicclu
		stderr = tempfile.SpooledTemporaryFile()
		p = sp.Popen([xicclu, "-ff", "-i" + intent, "-p" + pcs, "profile_in.icc"], 
					 stdin=sp.PIPE, stdout=sp.PIPE, stderr=stderr, 
					 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
		self.subprocess = p
		if p.poll() not in (0, None):
			stderr.seek(0)
			raise Error(stderr.read().strip())
		try:
			odata = p.communicate("\n".join(RGB_triplets))[0].splitlines()
		except IOError:
			stderr.seek(0)
			raise Error(stderr.read().strip())
		if p.wait() != 0:
			raise IOError(''.join(odata))
		stderr.close()

		# Convert xicclu output to XYZ triplets
		XYZ_triplets = []
		for line in odata:
			line = "".join(line.strip().split("->")).split()
			XYZ_triplets.append(" ".join([n for n in line[5:8]]))
		if debug:
			safe_print(len(XYZ_triplets), "XYZ triplets")
			safe_print("\n".join(XYZ_triplets))

		# Prepare 'output' profile
		profile_out.write(os.path.join(cwd, "profile_out.icc"))
		
		# Apply calibration?
		if apply_cal:
			if not profile_out.tags.get("vcgt", None):
				raise Error(lang.getstr("profile.no_vcgt"))
			try:
				cgats = vcgt_to_cal(profile_out)
			except (CGATS.CGATSInvalidError, 
					CGATS.CGATSInvalidOperationError, CGATS.CGATSKeyError, 
					CGATS.CGATSTypeError, CGATS.CGATSValueError), exception:
				raise Error(lang.getstr("cal_extraction_failed"))
			cgats.write(os.path.join(cwd, "profile_out.cal"))
			applycal = get_argyll_util("applycal")
			if not applycal:
				raise NotImplementedError(lang.getstr("argyll.util.not_found",
													  "applycal"))
			safe_print(lang.getstr("3dlut.output.profile.apply_cal"))
			result = self.exec_cmd(applycal, ["-v",
											  "profile_out.cal",
											  "profile_out.icc",
											  "profile_out.icc"],
								   capture_output=True, skip_scripts=True,
								   working_dir=cwd)
			if isinstance(result, Exception):
				raise result
			elif not result:
				raise Error("\n\n".join(lang.getstr("3dlut.output.profile.apply_cal.error"),
										"\n".join(self.errors)))
			profile_out = ICCP.ICCProfile(os.path.join(cwd,
													   "profile_out.icc"))

		if bpc:
			# Black point compensation
			
			# Get 'input' profile black point
			bp_in = [float(n) for n in XYZ_triplets[0].split()]
			if debug:
				safe_print("bp_in", bp_in)

			# Lookup 'output' profile black point
			stderr = tempfile.SpooledTemporaryFile()
			p = sp.Popen([xicclu, "-ff", "-i" + intent, "-p" + pcs, "profile_out.icc"], 
						 stdin=sp.PIPE, stdout=sp.PIPE, stderr=stderr, 
						 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
			self.subprocess = p
			if p.poll() not in (0, None):
				stderr.seek(0)
				raise Error(stderr.read().strip())
			try:
				odata = p.communicate("0 0 0\n1 1 1")[0].splitlines()
			except IOError:
				stderr.seek(0)
				raise Error(stderr.read().strip())
			if p.wait() != 0:
				# error
				raise IOError(''.join(odata))
			stderr.close()

			bp_out = [float(n) for n in "".join(odata[0].strip().split("->")).split()[5:8]]
			if debug:
				safe_print("bp_out", bp_out)

			# Get 'output' profile white point
			wp_out = [float(n) for n in "".join(odata[1].strip().split("->")).split()[5:8]]
			if debug:
				safe_print("wp_out", wp_out)
			
			# Apply black point compensation
			for i, XYZ_triplet in enumerate(XYZ_triplets):
				X, Y, Z = [float(n) for n in XYZ_triplet.split()]
				XYZ_triplets[i] = " ".join(str(n) for n in
										   colormath.apply_bpc(X, Y, Z, bp_in,
															   bp_out, wp_out))
		if debug:
			safe_print(len(XYZ_triplets), "XYZ triplets")
			safe_print("\n".join(XYZ_triplets))

		# Lookup XYZ -> RGB values through 'output' profile using xicclu
		stderr = tempfile.SpooledTemporaryFile()
		p = sp.Popen([xicclu, "-fb", "-i" + intent, "-p" + pcs, "profile_out.icc"], 
					 stdin=sp.PIPE, stdout=sp.PIPE, stderr=stderr, 
					 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
		self.subprocess = p
		if p.poll() not in (0, None):
			stderr.seek(0)
			raise Error(stderr.read().strip())
		try:
			odata = p.communicate("\n".join(XYZ_triplets))[0].splitlines()
		except IOError:
			stderr.seek(0)
			raise Error(stderr.read().strip())
		if p.wait() != 0:
			# error
			raise IOError(''.join(odata))
		stderr.close()

		# Remove temporary files
		self.wrapup(False)
		
		# Convert xicclu output to RGB triplets
		RGB_triplets = []
		for line in odata:
			line = "".join(line.strip().split("->")).split()
			RGB_triplets.append(" ".join([n for n in line[5:8]]))
		if debug:
			safe_print(len(RGB_triplets), "RGB triplets")
			safe_print("\n".join(RGB_triplets))

		lut = [["# Created with %s %s" % (appname, version)]]
		if format == "3dl":
			if maxval is None:
				maxval = 1023
			if output_bits is None:
				output_bits = math.log(maxval + 1) / math.log(2)
			if input_bits is None:
				input_bits = output_bits
			maxval = math.pow(2, output_bits) - 1
			pad = len(str(maxval))
			lut.append(["# INPUT RANGE: %i" % input_bits])
			lut.append(["# OUTPUT RANGE: %i" % output_bits])
			lut.append([])
			for i in xrange(0, size):
				lut[-1] += ["%i" % int(round(i * step * (math.pow(2, input_bits) - 1)))]
			for RGB_triplet in RGB_triplets:
				lut.append([])
				RGB_triplet = RGB_triplet.split()
				for component in (0, 1, 2):
					lut[-1] += [("%i" % int(round(float(RGB_triplet[component]) * maxval))).rjust(pad, " ")]
		elif format == "cube":
			if maxval is None:
				maxval = 1.0
			lut.append(["LUT_3D_SIZE %i" % size])
			lut.append(["DOMAIN_MIN 0.0 0.0 0.0"])
			fp_offset = str(maxval).find(".")
			domain_max = "DOMAIN_MAX %s %s %s" % (("%%.%if" % len(str(maxval)[fp_offset + 1:]), ) * 3)
			lut.append([domain_max % ((maxval ,) * 3)])
			lut.append([])
			for RGB_triplet in RGB_triplets:
				lut.append([])
				RGB_triplet = RGB_triplet.split()
				for component in (0, 1, 2):
					lut[-1] += ["%.6f" % (float(RGB_triplet[component]) * maxval)]
		lut.append([])
		for i, line in enumerate(lut):
			lut[i] = " ".join(line)
		return "\n".join(lut)

	def create_tempdir(self):
		""" Create a temporary working directory and return its path. """
		if not self.tempdir or not os.path.isdir(self.tempdir):
			# we create the tempdir once each calibrating/profiling run 
			# (deleted by 'wrapup' after each run)
			if verbose >= 2:
				if not self.tempdir:
					msg = "there is none"
				else:
					msg = "the previous (%s) no longer exists" % self.tempdir
				safe_print(appname + ": Creating a new temporary directory "
						   "because", msg)
			try:
				self.tempdir = tempfile.mkdtemp(prefix=appname + u"-")
			except Exception, exception:
				self.tempdir = None
				return Error("Error - couldn't create temporary directory: " + 
							 safe_str(exception))
		return self.tempdir

	def enumerate_displays_and_ports(self, silent=False, check_lut_access=True,
									 enumerate_ports=True):
		"""
		Enumerate the available displays and ports.
		
		Also sets Argyll version number, availability of certain options
		like black point rate, and checks LUT access for each display.
		
		"""
		if (silent and check_argyll_bin()) or (not silent and 
											   check_set_argyll_bin()):
			displays = []
			lut_access = []
			if verbose >= 1 and not silent:
				safe_print(lang.getstr("enumerating_displays_and_comports"))
			if getattr(wx.GetApp(), "progress_dlg", None) and \
			   wx.GetApp().progress_dlg.IsShownOnScreen():
				wx.GetApp().progress_dlg.Pulse(
					lang.getstr("enumerating_displays_and_comports"))
			instruments = []
			if enumerate_ports:
				cmd = get_argyll_util("dispcal")
			else:
				cmd = get_argyll_util("dispwin")
				for instrument in getcfg("instruments").split(os.pathsep):
					if instrument.strip():
						instruments.append(instrument)
			argyll_bin_dir = os.path.dirname(cmd)
			if (argyll_bin_dir != self.argyll_bin_dir):
				self.argyll_bin_dir = argyll_bin_dir
				safe_print(self.argyll_bin_dir)
			result = self.exec_cmd(cmd, ["-?"], capture_output=True, 
								   skip_scripts=True, silent=True, 
								   log_output=False)
			if isinstance(result, Exception):
				safe_print(result)
			arg = None
			defaults["calibration.black_point_rate.enabled"] = 0
			n = -1
			self.display_rects = []
			for line in self.output:
				if isinstance(line, unicode):
					n += 1
					line = line.strip()
					if n == 0 and "version" in line.lower():
						argyll_version = line[line.lower().find("version")+8:]
						argyll_version_string = argyll_version
						if (argyll_version_string != self.argyll_version_string):
							self.argyll_version_string = argyll_version_string
							safe_print("Argyll CMS " + self.argyll_version_string)
						config.defaults["copyright"] = ("No copyright. Created "
														"with %s %s and Argyll "
														"CMS %s" % 
														(appname, version, 
														 argyll_version))
						argyll_version = re.findall("(\d+|[^.\d]+)", 
													argyll_version)
						for i, v in enumerate(argyll_version):
							try:
								argyll_version[i] = int(v)
							except ValueError:
								pass
						self.argyll_version = argyll_version
						if argyll_version > [1, 0, 4]:
							# Rate of blending from neutral to black point.
							defaults["calibration.black_point_rate.enabled"] = 1
						continue
					line = line.split(None, 1)
					if len(line) and line[0][0] == "-":
						arg = line[0]
						if arg == "-A":
							# Rate of blending from neutral to black point.
							defaults["calibration.black_point_rate.enabled"] = 1
					elif len(line) > 1 and line[1][0] == "=":
						value = line[1].strip(" ='")
						if arg == "-d":
							match = re.findall("(.+?),? at (-?\d+), (-?\d+), "
											   "width (\d+), height (\d+)", 
											   value)
							if len(match):
								display = "%s @ %s, %s, %sx%s" % match[0]
								if " ".join(value.split()[-2:]) == \
								   "(Primary Display)":
									display += u" [PRIMARY]"
								displays.append(display)
								self.display_rects.append(
									wx.Rect(*[int(item) for item in match[0][1:]]))
						elif arg == "-c":
							if ((value.startswith("/dev/tty") or
								 value.startswith("COM")) and 
								getcfg("skip_legacy_serial_ports")):
								# Skip all legacy serial ports (this means we 
								# deliberately don't support DTP92 and
								# Spectrolino, although they may work when
								# used with a serial to USB adaptor)
								continue
							value = value.split(None, 1)
							if len(value) > 1:
								value = value[1].strip("()")
							else:
								value = value[0]
							value = remove_vendor_names(value)
							instruments.append(value)
			if test:
				inames = all_instruments.keys()
				inames.sort()
				for iname in inames:
					if not iname in instruments:
						instruments.append(iname)
			if verbose >= 1 and not silent: safe_print(lang.getstr("success"))
			if getattr(wx.GetApp(), "progress_dlg", None) and \
			   wx.GetApp().progress_dlg.IsShownOnScreen():
				wx.GetApp().progress_dlg.Pulse(
					lang.getstr("success"))
			if instruments != self.instruments:
				self.instruments = instruments
				setcfg("instruments", os.pathsep.join(instruments))
			if displays != self._displays:
				self._displays = list(displays)
				self.display_edid = []
				self.display_manufacturers = []
				self.display_names = []
				if sys.platform == "win32":
					# The ordering will work as long
					# as Argyll continues using
					# EnumDisplayMonitors
					monitors = util_win.get_real_display_devices_info()
				for i, display in enumerate(displays):
					display_name = displays[i].split("@")[0].strip()
					# Make sure we have nice descriptions
					desc = []
					if sys.platform == "win32" and i < len(monitors):
						# Get monitor description using win32api
						device = util_win.get_active_display_device(
									monitors[i]["Device"])
						if device:
							desc.append(device.DeviceString.decode(fs_enc, 
																   "replace"))
					# Get monitor descriptions from EDID
					try:
						# Important: display_name must be given for get_edid
						# under Mac OS X, but it doesn't hurt to always
						# include it
						edid = get_edid(i, display_name)
					except (TypeError, ValueError, WMIError):
						edid = {}
					self.display_edid.append(edid)
					if edid:
						manufacturer = edid.get("manufacturer", "").split()
						monitor = edid.get("monitor_name",
										   edid.get("ascii",
													str(edid["product_id"] or
														"")))
						if monitor and not monitor in "".join(desc):
							desc = [monitor]
						if (manufacturer and 
							"".join(desc).lower().startswith(manufacturer[0].lower())):
							manufacturer = []
					else:
						manufacturer = []
					if desc and desc[-1] not in display:
						# Only replace the description if it not already
						# contains the monitor model
						displays[i] = " @".join([" ".join(desc), 
												 display.split("@")[1]])
					self.display_manufacturers.append(" ".join(manufacturer))
					self.display_names.append(displays[i].split("@")[0].strip())
				self.displays = displays
				setcfg("displays", os.pathsep.join(displays))
				if check_lut_access:
					dispwin = get_argyll_util("dispwin")
					for i, disp in enumerate(displays):
						if verbose >= 1 and not silent:
							safe_print(lang.getstr("checking_lut_access", (i + 1)))
						if getattr(wx.GetApp(), "progress_dlg", None) and \
						   wx.GetApp().progress_dlg.IsShownOnScreen():
							wx.GetApp().progress_dlg.Pulse(
								lang.getstr("checking_lut_access", (i + 1)))
						test_cal = get_data_path("test.cal")
						if not test_cal:
							safe_print(lang.getstr("file.missing", "test.cal"))
							return
						# Load test.cal
						result = self.exec_cmd(dispwin, ["-d%s" % (i +1), "-c", 
														 test_cal], 
											   capture_output=True, 
											   skip_scripts=True, 
											   silent=True)
						if isinstance(result, Exception):
							safe_print(result)
						# Check if LUT == test.cal
						result = self.exec_cmd(dispwin, ["-d%s" % (i +1), "-V", 
														 test_cal], 
											   capture_output=True, 
											   skip_scripts=True, 
											   silent=True)
						if isinstance(result, Exception):
							safe_print(result)
						retcode = -1
						for line in self.output:
							if line.find("IS loaded") >= 0:
								retcode = 0
								break
						# Reset LUT & load profile cal (if any)
						result = self.exec_cmd(dispwin, ["-d%s" % (i + 1), "-c", 
														 self.get_dispwin_display_profile_argument(i)], 
											   capture_output=True, 
											   skip_scripts=True, 
											   silent=True)
						if isinstance(result, Exception):
							safe_print(result)
						lut_access += [retcode == 0]
						if verbose >= 1 and not silent:
							if retcode == 0:
								safe_print(lang.getstr("success"))
							else:
								safe_print(lang.getstr("failure"))
						if getattr(wx.GetApp(), "progress_dlg", None) and \
						   wx.GetApp().progress_dlg.IsShownOnScreen():
							wx.GetApp().progress_dlg.Pulse(
								lang.getstr("success" if retcode == 0 else
											"failure"))
				self.lut_access = lut_access
		elif silent or not check_argyll_bin():
			self.clear_argyll_info()

	def exec_cmd(self, cmd, args=[], capture_output=False, 
				 display_output=False, low_contrast=True, skip_scripts=False, 
				 silent=False, parent=None, asroot=False, log_output=True,
				 title=appname, shell=False, working_dir=None):
		"""
		Execute a command.
		
		cmd is the full path of the command.
		args are the arguments, if any.
		capture_output (if True) swallows any output from the command and
		sets the 'output' and 'errors' properties of the Worker instance.
		display_output shows any captured output if the Worker instance's 
		'owner' window has a 'LogWindow' child called 'infoframe'.
		low_contrast (if True) sets low contrast shell colors while the 
		command is run.
		skip_scripts (if True) skips the creation of shell scripts that allow 
		re-running the command which are created by default.
		silent (if True) skips most output and also most error dialogs 
		(except unexpected failures)
		parent sets the parent window for any message dialogs.
		asroot (if True) on Linux runs the command using sudo.
		log_output (if True) logs any output if capture_output is also set.
		title = Title for sudo dialog
		working_dir = Working directory. If None, will be determined from
		absulte path of last argument and last argument will be set to only 
		the basename. If False, no working dir will be used and file arguments
		not changed.
		"""
		progress_dlg = getattr(self, "progress_wnd",
							   getattr(wx.GetApp(), "progress_dlg", None))
		if parent is None:
			if progress_dlg and progress_dlg.IsShownOnScreen():
				parent = progress_dlg
			else:
				parent = self.owner
		if not capture_output:
			capture_output = not sys.stdout.isatty()
		fn = None
		self.clear_cmd_output()
		if None in [cmd, args]:
			if verbose >= 1 and not silent:
				safe_print(lang.getstr("aborted"), fn=fn)
			return False
		cmdname = os.path.splitext(os.path.basename(cmd))[0]
		if cmdname == get_argyll_utilname("dispwin"):
			if "-Sl" in args or "-Sn" in args or (sys.platform == "darwin" and
												  not "-I" in args and
												  mac_ver()[0] >= '10.7'):
				# Mac OS X 10.7 Lion needs root privileges if loading/clearing 
				# calibration
				# In all other cases, root is only required if installing a
				# profile to a system location
				asroot = True
		if args and args[-1].find(os.path.sep) > -1:
			working_basename = os.path.basename(args[-1])
			if cmdname in (get_argyll_utilname("dispwin"),
						   "oyranos-monitor"):
				# Last arg is without extension, only for dispwin we need to 
				# strip it
				working_basename = os.path.splitext(working_basename)[0]
			if working_dir is None:
				working_dir = os.path.dirname(args[-1])
		if working_dir is None:
			working_dir = self.tempdir
		if working_dir and not os.path.isdir(working_dir):
			working_dir = None
		if verbose >= 1:
			if not silent or verbose >= 3:
				safe_print("", fn=fn)
				if working_dir:
					safe_print(lang.getstr("working_dir"), fn=fn)
					indent = "  "
					for name in working_dir.split(os.path.sep):
						safe_print(textwrap.fill(name + os.path.sep, 80, 
												 expand_tabs=False, 
												 replace_whitespace=False, 
												 initial_indent=indent, 
												 subsequent_indent=indent), 
								   fn=fn)
						indent += " "
					safe_print("", fn=fn)
				safe_print(lang.getstr("commandline"), fn=fn)
				printcmdline(cmd if verbose >= 2 else os.path.basename(cmd), 
							 args, fn=fn, cwd=working_dir)
				safe_print("", fn=fn)
		cmdline = [cmd] + args
		if working_dir:
			for i, item in enumerate(cmdline):
				if i > 0 and (item.find(os.path.sep) > -1 and 
							  os.path.dirname(item) == working_dir):
					# Strip the path from all items in the working dir
					if sys.platform == "win32" and \
					   re.search("[^\x20-\x7e]", 
								 os.path.basename(item)) and os.path.exists(item):
						# Avoid problems with encoding
						item = win32api.GetShortPathName(item) 
					cmdline[i] = os.path.basename(item)
			if (sys.platform == "win32" and 
				re.search("[^\x20-\x7e]", working_dir) and 
				os.path.exists(working_dir)):
				# Avoid problems with encoding
				working_dir = win32api.GetShortPathName(working_dir)
		sudo = None
		# Run commands through wexpect.spawn instead of subprocess.Popen if
		# all of these conditions apply:
		# - command is dispcal, dispread or spotread
		# - arguments are not empty
		# - actual user interaction in a terminal is not needed OR
		#   we are on Windows and running without a console
		measure_cmds = (get_argyll_utilname("dispcal"), 
						get_argyll_utilname("dispread"), 
						get_argyll_utilname("spotread"))
		process_cmds = (get_argyll_utilname("colprof"),
						get_argyll_utilname("targen"))
		interact = args and not "-?" in args and cmdname in measure_cmds + process_cmds
		self.measure = not "-?" in args and cmdname in measure_cmds
		if self.measure:
			# TTBD/FIXME: Skipping of sensor calibration can't be done in
			# emissive mode (see Argyll source spectro/ss.c, around line 40)
			skip_sensor_cal = not self.get_instrument_features().get("sensor_cal") ##or \
							  ##"-N" in args
		self.dispcal = cmdname == get_argyll_utilname("dispcal")
		self.needs_user_interaction = args and (self.dispcal and not "-?" in args and 
									   not "-E" in args and not "-R" in args and 
									   not "-m" in args and not "-r" in args and 
									   not "-u" in args) or (self.measure and 
															 not skip_sensor_cal)
		if asroot and ((sys.platform != "win32" and os.geteuid() != 0) or 
					   (sys.platform == "win32" and 
					    sys.getwindowsversion() >= (6, ))):
			if sys.platform == "win32":
				# Vista and later
				pass
			else:
				sudo = which("sudo")
		if sudo:
			if not self.pwd:
				# Determine available sudo options
				if not self.sudo_availoptions:
					man = which("man")
					if man:
						manproc = sp.Popen([man, "sudo"], stdout=sp.PIPE, 
											stderr=sp.PIPE)
						# Strip formatting
						stdout = re.sub(".\x08", "", manproc.communicate()[0])
						self.sudo_availoptions = {"E": bool(re.search("-E", stdout)),
												  "l [command]": bool(re.search("-l(?:\[l\])?\s+\[command\]", stdout)),
												  "n": bool(re.search("-n", stdout))}
					else:
						self.sudo_availoptions = {"E": False, 
												  "l [command]": False, 
												  "n": False}
					if debug:
						safe_print("[D] Available sudo options:", 
								   ", ".join(filter(lambda option: self.sudo_availoptions[option], 
													self.sudo_availoptions.keys())))
				# Set sudo args based on available options
				if self.sudo_availoptions["l [command]"]:
					sudo_args = ["-l", "-n" if self.sudo_availoptions["n"] else "-S", cmd]
				else:
					sudo_args = ["-l", "-S"]
				# Set stdin based on -n option availability
				if "-S" in sudo_args:
					stdin = tempfile.SpooledTemporaryFile()
					stdin.write((self.pwd or "").encode(enc, "replace") + os.linesep)
					stdin.seek(0)
				else:
					stdin = None
				sudoproc = sp.Popen([sudo] + sudo_args, stdin=stdin, stdout=sp.PIPE, 
									stderr=sp.PIPE)
				stdout, stderr = sudoproc.communicate()
				if stdin and not stdin.closed:
					stdin.close()
				if not stdout.strip():
					# ask for password
					dlg = ConfirmDialog(
						parent, title=title, 
						msg=lang.getstr("dialog.enter_password"), 
						ok=lang.getstr("ok"), cancel=lang.getstr("cancel"), 
						bitmap=geticon(32, "dialog-question"))
					dlg.pwd_txt_ctrl = wx.TextCtrl(dlg, -1, "", 
												   size=(320, -1), 
												   style=wx.TE_PASSWORD | 
														 wx.TE_PROCESS_ENTER)
					dlg.pwd_txt_ctrl.Bind(wx.EVT_TEXT_ENTER, 
										  lambda event: dlg.EndModal(wx.ID_OK))
					dlg.sizer3.Add(dlg.pwd_txt_ctrl, 1, 
								   flag=wx.TOP | wx.ALIGN_LEFT, border=12)
					dlg.ok.SetDefault()
					dlg.pwd_txt_ctrl.SetFocus()
					dlg.sizer0.SetSizeHints(dlg)
					dlg.sizer0.Layout()
					sudo_args = ["-l", "-S"]
					if self.sudo_availoptions["l [command]"]:
						sudo_args.append(cmd)
					while True:
						if parent and parent is progress_dlg:
							progress_dlg.MakeModal(False)
						result = dlg.ShowModal()
						if parent and parent is progress_dlg:
							progress_dlg.MakeModal(True)
						pwd = dlg.pwd_txt_ctrl.GetValue()
						if result != wx.ID_OK:
							safe_print(lang.getstr("aborted"), fn=fn)
							return None
						stdin = tempfile.SpooledTemporaryFile()
						stdin.write(pwd.encode(enc, "replace") + os.linesep)
						stdin.seek(0)
						sudoproc = sp.Popen([sudo] + sudo_args, stdin=stdin, 
											stdout=sp.PIPE, stderr=sp.PIPE)
						stdout, stderr = sudoproc.communicate()
						if not stdin.closed:
							stdin.close()
						if stdout.strip():
							# password was accepted
							self.auth_timestamp = time()
							self.pwd = pwd
							break
						else:
							errstr = unicode(stderr, enc, "replace")
							if not silent:
								safe_print(errstr)
							else:
								log(errstr)
							dlg.message.SetLabel(
								lang.getstr("auth.failed") + "\n" + 
								errstr)
							dlg.sizer0.SetSizeHints(dlg)
							dlg.sizer0.Layout()
					dlg.Destroy()
			cmdline.insert(0, sudo)
			if (cmdname == get_argyll_utilname("dispwin")
				and sys.platform != "darwin"
				and self.sudo_availoptions["E"]
				and getcfg("sudo.preserve_environment")):
				# Preserve environment so $DISPLAY is set
				cmdline.insert(1, "-E")
			if not interact:
				cmdline.insert(1, "-S")
		if working_dir and not skip_scripts:
			try:
				cmdfilename = os.path.join(working_dir, working_basename + 
										   "." + cmdname + script_ext)
				allfilename = os.path.join(working_dir, working_basename + 
										   ".all" + script_ext)
				first = not os.path.exists(allfilename)
				last = cmdname == get_argyll_utilname("dispwin")
				cmdfile = open(cmdfilename, "w")
				allfile = open(allfilename, "a")
				cmdfiles = Files((cmdfile, allfile))
				if first:
					context = cmdfiles
				else:
					context = cmdfile
				if sys.platform == "win32":
					context.write("@echo off\n")
					context.write(('PATH %s;%%PATH%%\n' % 
								   os.path.dirname(cmd)).encode(enc, 
																"safe_asciize"))
					cmdfiles.write('pushd "%~dp0"\n'.encode(enc, "safe_asciize"))
					if cmdname in (get_argyll_utilname("dispcal"), 
								   get_argyll_utilname("dispread")):
						cmdfiles.write("color 07\n")
				else:
					context.write(('PATH=%s:$PATH\n' % 
								   os.path.dirname(cmd)).encode(enc, 
																"safe_asciize"))
					if sys.platform == "darwin" and config.mac_create_app:
						cmdfiles.write('pushd "`dirname '
										'\\"$0\\"`/../../.."\n')
					else:
						cmdfiles.write('pushd "`dirname \\"$0\\"`"\n')
					if cmdname in (get_argyll_utilname("dispcal"), 
								   get_argyll_utilname("dispread")) and \
					   sys.platform != "darwin":
						cmdfiles.write('echo -e "\\033[40;2;37m" && clear\n')
					os.chmod(cmdfilename, 0755)
					os.chmod(allfilename, 0755)
				cmdfiles.write(u" ".join(quote_args(cmdline)).replace(cmd, 
					cmdname).encode(enc, "safe_asciize") + "\n")
				if sys.platform == "win32":
					cmdfiles.write("set exitcode=%errorlevel%\n")
					if cmdname in (get_argyll_utilname("dispcal"), 
								   get_argyll_utilname("dispread")):
						# Reset to default commandline shell colors
						cmdfiles.write("color\n")
					cmdfiles.write("popd\n")
					cmdfiles.write("if not %exitcode%==0 exit /B %exitcode%\n")
				else:
					cmdfiles.write("exitcode=$?\n")
					if cmdname in (get_argyll_utilname("dispcal"), 
								   get_argyll_utilname("dispread")) and \
					   sys.platform != "darwin":
						# reset to default commandline shell colors
						cmdfiles.write('echo -e "\\033[0m" && clear\n')
					cmdfiles.write("popd\n")
					cmdfiles.write("if [ $exitcode -ne 0 ]; "
								   "then exit $exitcode; fi\n")
				cmdfiles.close()
				if sys.platform == "darwin":
					if config.mac_create_app:
						# Could also use .command file directly, but using 
						# applescript allows giving focus to the terminal 
						# window automatically after a delay
						script = mac_terminal_do_script() + \
								 mac_terminal_set_colors(do=False) + \
								 ['-e', 'set shellscript to quoted form of '
								  '(POSIX path of (path to resource '
								  '"main.command"))', '-e', 'tell app '
								  '"Terminal"', '-e', 'do script shellscript '
								  'in first window', '-e', 'delay 3', '-e', 
								  'activate', '-e', 'end tell', '-o']
						# Part 1: "cmdfile"
						appfilename = os.path.join(working_dir, 
												   working_basename + "." + 
												   cmdname + 
												   ".app").encode(fs_enc)
						cmdargs = ['osacompile'] + script + [appfilename]
						p = sp.Popen(cmdargs, stdin=sp.PIPE, stdout=sp.PIPE, 
									 stderr=sp.PIPE)
						p.communicate()
						shutil.move(cmdfilename, appfilename + 
									"/Contents/Resources/main.command")
						os.chmod(appfilename + 
								 "/Contents/Resources/main.command", 0755)
						# Part 2: "allfile"
						appfilename = os.path.join(
							working_dir,  working_basename + ".all.app")
						cmdargs = ['osacompile'] + script + [appfilename]
						p = sp.Popen(cmdargs, stdin=sp.PIPE, stdout=sp.PIPE, 
									 stderr=sp.PIPE)
						p.communicate()
						shutil.copyfile(allfilename, appfilename + 
										"/Contents/Resources/main.command")
						os.chmod(appfilename + 
								 "/Contents/Resources/main.command", 0755)
						if last:
							os.remove(allfilename)
			except Exception, exception:
				safe_print("Warning - error during shell script creation:", 
						   safe_unicode(exception))
		cmdline = [arg.encode(fs_enc) for arg in cmdline]
		working_dir = None if not working_dir else working_dir.encode(fs_enc)
		try:
			if not self.measure and self.argyll_version >= [1, 2]:
				# Argyll tools will no longer respond to keys
				if debug:
					safe_print("[D] Setting ARGYLL_NOT_INTERACTIVE 1")
				putenvu("ARGYLL_NOT_INTERACTIVE", "1")
			elif "ARGYLL_NOT_INTERACTIVE" in os.environ:
				del os.environ["ARGYLL_NOT_INTERACTIVE"]
			if debug:
				safe_print("[D] argyll_version", self.argyll_version)
				safe_print("[D] ARGYLL_NOT_INTERACTIVE", 
						   os.environ.get("ARGYLL_NOT_INTERACTIVE"))
			if sys.platform not in ("darwin", "win32"):
				putenvu("ENABLE_COLORHUG", "1")
			if sys.platform == "win32":
				startupinfo = sp.STARTUPINFO()
				startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
				startupinfo.wShowWindow = sp.SW_HIDE
			else:
				startupinfo = None
			if not interact:
				if silent:
					stderr = sp.STDOUT
				else:
					stderr = tempfile.SpooledTemporaryFile()
				if capture_output:
					stdout = tempfile.SpooledTemporaryFile()
				elif sys.stdout.isatty():
					stdout = sys.stdout
				else:
					stdout = sp.PIPE
				if sudo:
					stdin = tempfile.SpooledTemporaryFile()
					stdin.write((self.pwd or "").encode(enc, "replace") + os.linesep)
					stdin.seek(0)
				elif sys.stdin.isatty():
					stdin = None
				else:
					stdin = sp.PIPE
			else:
				kwargs = dict(timeout=30, cwd=working_dir,
							  env=os.environ)
				if sys.platform == "win32":
					kwargs["codepage"] = windll.kernel32.GetACP()
				stderr = StringIO()
				stdout = StringIO()
				if log_output:
					if sys.stdout.isatty():
						logfile = LineBufferedStream(
								  FilteredStream(safe_print, self.data_encoding,
												 discard="", 
												 linesep_in="\n", 
												 triggers=[]))
					else:
						logfile = LineBufferedStream(
								  FilteredStream(log, self.data_encoding,
												 discard="",
												 linesep_in="\n", 
												 triggers=[]))
					logfile = Files((logfile, stdout, self.recent,
									 self.lastmsg))
				else:
					logfile = Files((stdout, self.recent,
									 self.lastmsg))
				if ((self.interactive or (test and not "-?" in args)) and 
					getattr(self, "terminal", None)):
					logfile = Files((FilteredStream(self.terminal,
													discard="",
													triggers=self.triggers), 
									logfile))
			logfn = log
			tries = 1
			while tries > 0:
				if interact:
					if self.argyll_version >= [1, 2] and USE_WPOPEN and \
					   os.environ.get("ARGYLL_NOT_INTERACTIVE"):
						self.subprocess = WPopen(" ".join(cmdline) if shell else
												 cmdline, stdin=sp.PIPE, 
												 stdout=tempfile.SpooledTemporaryFile(), 
												 stderr=sp.STDOUT, 
												 shell=shell, cwd=working_dir, 
												 startupinfo=startupinfo)
					else:
						self.subprocess = wexpect.spawn(cmdline[0], cmdline[1:], 
														**kwargs)
						if debug >= 9 or (test and not "-?" in args):
							self.subprocess.interact()
					self.subprocess.logfile_read = logfile
					if self.subprocess.isalive():
						try:
							if self.measure:
								self.subprocess.expect([" or Q to "])
								msg = self.recent.read()
								lastmsg = self.lastmsg.read().strip()
								if "key to continue" in lastmsg.lower() and \
								   "place instrument on test window" in \
								   "".join(msg.splitlines()[-2:-1]).lower():
									self.recent.clear()
									if "-F" in args:
										# Allow the user to move the terminal 
										# window if using black background, 
										# otherwise send space key to start
										# measurements right away
										sleep(3)
									if sys.platform != "win32":
										sleep(.5)
									if self.subprocess.isalive():
										if debug or test:
											safe_print('Sending SPACE key')
										self.subprocess.send(" ")
								if self.needs_user_interaction and \
								   sys.platform == "darwin":
									# On the Mac dispcal's test window
									# hides the cursor and steals focus
									start_new_thread(mac_app_activate, 
													 (1, appname if isapp 
													 	 else "Python"))
								retrycount = 0
								while self.subprocess.isalive():
									# Automatically retry on error, user can 
									# cancel via progress dialog
									self.subprocess.expect("key to retry:", 
														   timeout=None)
									if sys.platform != "win32":
										sleep(.5)
									if (self.subprocess.isalive() and
									    not "Sample read stopped at user request!"
									    in self.recent.read() and
									    ("Sample read failed due to misread"
									     in self.recent.read() or 
									     "Sample read failed due to communication problem"
									     in self.recent.read()) and
									    not self.subprocess_abort):
										retrycount += 1
										logfile.write("\r\n%s: Retrying (%s)..." % 
													  (appname, retrycount))
										self.subprocess.send(" ")
							else:
								self.subprocess.expect(wexpect.EOF, 
													   timeout=None)
						except (wexpect.EOF, wexpect.TIMEOUT), exception:
							pass
					if self.subprocess.after not in (wexpect.EOF, 
													 wexpect.TIMEOUT):
						self.subprocess.expect(wexpect.EOF, timeout=None)
					# We need to call isalive() to set the exitstatus.
					# We can't use wait() because it might block in the
					# case of a timeout
					while self.subprocess.isalive():
						sleep(.1)
					self.retcode = self.subprocess.exitstatus
				else:
					self.subprocess = sp.Popen(" ".join(cmdline) if shell else
											   cmdline, stdin=stdin, 
											   stdout=stdout, stderr=stderr, 
											   shell=shell, cwd=working_dir, 
											   startupinfo=startupinfo)
					self.retcode = self.subprocess.wait()
					if stdin and not getattr(stdin, "closed", True):
						stdin.close()
				if self.is_working() and self.subprocess_abort and \
				   self.retcode == 0:
					self.retcode = -1
				self.subprocess = None
				tries -= 1
				if not silent:
					stderr.seek(0)
					errors = stderr.readlines()
					if not capture_output or stderr is not stdout:
						stderr.close()
					if len(errors):
						for line in errors:
							if "Instrument Access Failed" in line and \
							   "-N" in cmdline[:-1]:
								cmdline.remove("-N")
								tries = 1
								break
							if line.strip() and \
							   line.find("User Aborted") < 0 and \
							   line.find("XRandR 1.2 is faulty - falling back "
										 "to older extensions") < 0:
								self.errors += [line.decode(enc, "replace")]
						if len(self.errors):
							errstr = "".join(self.errors).strip()
							safe_print(errstr, fn=fn)
					if tries > 0 and not interact:
						stderr = tempfile.SpooledTemporaryFile()
				if capture_output or interact:
					stdout.seek(0)
					self.output = [re.sub("^\.{4,}\s*$", "", 
										  line.decode(enc, "replace")) 
								   for line in stdout.readlines()]
					stdout.close()
					if len(self.output) and log_output:
						if not interact:
							logfn = log if silent else safe_print
							logfn("".join(self.output).strip())
						if display_output and self.owner and \
						   hasattr(self.owner, "infoframe"):
							wx.CallAfter(self.owner.infoframe.Show)
					if tries > 0 and not interact:
						stdout = tempfile.SpooledTemporaryFile()
		except Exception, exception:
			if debug:
				safe_print('[D] working_dir:', working_dir)
			errmsg = (" ".join(cmdline).decode(fs_enc) + "\n" + 
					  safe_unicode(traceback.format_exc()))
			self.retcode = -1
			return Error(errmsg)
		if debug and not silent:
			safe_print("*** Returncode:", self.retcode)
		if self.retcode != 0:
			if interact and verbose >= 1 and not silent:
				safe_print(lang.getstr("aborted"), fn=fn)
			if interact and len(self.output):
				for i, line in enumerate(self.output):
					if line.startswith(cmdname + ": Error") and \
					   not "failed with 'User Aborted'" in line and \
					   not "test_crt returned error code 1" in line:
						# "test_crt returned error code 1" == user aborted
						if (sys.platform == "win32" and
							("config 1 failed (Operation not supported or "
							 "unimplemented on this platform) (Permissions ?)")
							in line):
							self.output.insert(i, lang.getstr("argyll.instrument.driver.missing") +
															  "\n\n" +
															  lang.getstr("argyll.error.detail") +
															  " ")
						return UnloggedError("".join(self.output[i:]))
			return False
		return True

	def generic_consumer(self, delayedResult, consumer, continue_next, *args, 
						 **kwargs):
		# consumer must accept result as first arg
		result = None
		exception = None
		try:
			result = delayedResult.get()
		except Exception, exception:
			result = Error(u"Error - delayedResult.get() failed: " + 
						   safe_unicode(traceback.format_exc()))
		if self.progress_start_timer.IsRunning():
			self.progress_start_timer.Stop()
		if hasattr(self, "progress_wnd") and (not continue_next or 
											  isinstance(result, Exception) or 
											  not result):
			self.progress_wnd.stop_timer()
			self.progress_wnd.MakeModal(False)
			# under Linux, destroying it here causes segfault
			if sys.platform == "win32" and wx.VERSION >= (2, 9):
				self.progress_wnd.Destroy()
			else:
				self.progress_wnd.Hide()
		self.finished = True
		self.subprocess_abort = False
		self.thread_abort = False
		wx.CallAfter(consumer, result, *args, **kwargs)
	
	def get_device_id(self):
		""" Get org.freedesktop.ColorManager device key """
		if colord:
			edid = self.display_edid[max(0, min(len(self.displays) - 1, 
												getcfg("display.number") - 1))]
			return colord.device_id_from_edid(edid)

	def get_display(self):
		display_no = min(len(self.displays), getcfg("display.number")) - 1
		display = str(display_no + 1)
		if (self.has_separate_lut_access() or 
			getcfg("use_separate_lut_access")) and (
		   		not getcfg("display_lut.link") or 
		   		(display_no > -1 and not self.lut_access[display_no])):
			display_lut_no = min(len(self.displays), 
									 getcfg("display_lut.number")) - 1
			if display_lut_no > -1 and not self.lut_access[display_lut_no]:
				for display_lut_no, disp in enumerate(self.lut_access):
					if disp:
						break
			display += "," + str(display_lut_no + 1)
		return display
	
	def get_display_edid(self):
		""" Return EDID of currently configured display """
		n = getcfg("display.number") - 1
		if n >= 0 and n < len(self.display_edid):
			return self.display_edid[n]
		return {}
	
	def get_display_name(self, prepend_manufacturer=False, prefer_edid=False):
		""" Return name of currently configured display """
		n = getcfg("display.number") - 1
		if n >= 0 and n < len(self.display_names):
			display = []
			manufacturer = None
			display_name = None
			if prefer_edid:
				edid = self.get_display_edid()
				manufacturer = edid.get("manufacturer")
				display_name = edid.get("monitor_name",
										edid.get("ascii",
												 str(edid.get("product_id") or
													 "")))
			if not manufacturer:
				manufacturer = self.display_manufacturers[n]
			if not display_name:
				display_name = self.display_names[n]
			if manufacturer:
				if prepend_manufacturer:
					if manufacturer.lower() not in display_name.lower():
						display.append(normalize_manufacturer_name(manufacturer))
				else:
					start = display_name.lower().find(manufacturer.lower())
					if start > -1:
						display_name = (display_name[:start] +
										display_name[start + len(manufacturer):]).replace("  ", " ")
			display.append(display_name)
			return " ".join(display)
		return ""

	def get_display_name_short(self, prepend_manufacturer=False, prefer_edid=False):
		display_name = self.get_display_name(prepend_manufacturer, prefer_edid)
		if len(display_name) > 10:
			maxweight = 0
			for part in re.findall('[^\s_]+(?:\s*\d+)?', re.sub("\([^)]+\)", "", 
																display_name)):
				digits = re.search("\d+", part)
				if digits:
					# Weigh parts with digits higher than those without
					chars = re.sub("\d+", "", part)
					weight = len(chars) + len(digits.group()) * 5
				else:
					# Weigh parts with uppercase letters higher than those without
					chars = ""
					for char in part:
						if char.lower() != char:
							chars += char
					weight = len(chars)
				if chars and weight >= maxweight:
					# Weigh parts further to the right higher
					display_name = part
					maxweight = weight
		return display_name
	
	def get_dispwin_display_profile_argument(self, display_no=0):
		arg = "-L"
		try:
			profile = ICCP.get_display_profile(display_no)
		except Exception, exception:
			safe_print("Error - couldn't get profile for display %s" % 
					   getcfg("display.number"))
		else:
			if profile and profile.fileName:
				arg = profile.fileName
		return arg
	
	def update_display_name_manufacturer(self, ti3, display_name=None,
										 display_manufacturer=None, 
										 write=True):
		options_colprof = []
		if not display_name and not display_manufacturer:
			# Note: Do not mix'n'match display name and manufacturer from 
			# different sources
			for option in get_options_from_ti3(ti3)[1]:
				if option[0] == "M":
					display_name = option.split(None, 1)[-1][1:-1]
				elif option[0] == "A":
					display_manufacturer = option.split(None, 1)[-1][1:-1]
		if not display_name and not display_manufacturer:
			# Note: Do not mix'n'match display name and manufacturer from 
			# different sources
			edid = self.display_edid[max(0, min(len(self.displays), 
												getcfg("display.number") - 1))]
			display_name = edid.get("monitor_name",
									edid.get("ascii",
											 str(edid.get("product_id") or "")))
			display_manufacturer = edid.get("manufacturer")
		if not display_name and not display_manufacturer:
			# Note: Do not mix'n'match display name and manufacturer from 
			# different sources
			display_name = self.get_display_name()
		if display_name:
			options_colprof.append("-M")
			options_colprof.append(display_name)
		if display_manufacturer:
			options_colprof.append("-A")
			options_colprof.append(display_manufacturer)
		if write:
			# Add dispcal and colprof arguments to ti3
			ti3 = add_options_to_ti3(ti3, self.options_dispcal, options_colprof)
			if ti3:
				ti3.write()
		return options_colprof
	
	def get_instrument_features(self):
		""" Return features of currently configured instrument """
		features = all_instruments.get(self.get_instrument_name(), {})
		if test_require_sensor_cal:
			features["sensor_cal"] = True
			features["skip_sensor_cal"] = False
		return features
	
	def get_instrument_name(self):
		""" Return name of currently configured instrument """
		n = getcfg("comport.number") - 1
		if n >= 0 and n < len(self.instruments):
			return self.instruments[n]
		return ""
	
	def has_separate_lut_access(self):
		""" Return True if separate LUT access is possible and needed. """
		return (len(self.displays) > 1 and False in 
				self.lut_access and True in 
				self.lut_access)
	
	def import_edr(self, args=None):
		""" Import X-Rite .edr files """
		if not args:
			args = []
		cmd = get_argyll_util("i1d3ccss")
		needroot = sys.platform != "win32"
		if is_superuser() or needroot:
			# If we are root or need root privs anyway, install to local
			# system scope
			args.insert(0, "-Sl")
		return self.exec_cmd(cmd, ["-v"] + args, capture_output=True, 
							 skip_scripts=True, silent=False,
							 asroot=needroot)
	
	def import_spyd4cal(self, args=None):
		""" Import Spyder4 calibrations to spy4cal.bin """
		if not args:
			args = []
		cmd = get_argyll_util("spyd4en")
		needroot = sys.platform != "win32"
		if is_superuser() or needroot:
			# If we are root or need root privs anyway, install to local
			# system scope
			args.insert(0, "-Sl")
		return self.exec_cmd(cmd, ["-v"] + args, capture_output=True, 
							 skip_scripts=True, silent=False,
							 asroot=needroot)

	def install_profile(self, profile_path, capture_output=True,
						skip_scripts=False, silent=False):
		result = True
		colord_install = False
		gcm_import = False
		oy_install = False
		if sys.platform not in ("darwin", "win32"):
			device_id = self.get_device_id()
			if device_id:
				# FIXME: This can block, so should really be run in separate
				# thread with progress dialog in 'indeterminate' mode
				result = self._install_profile_colord(profile_path, device_id)
				colord_install = result
			if (not device_id or not colord or
				isinstance(result, Exception) or not result):
				gcm_import = bool(which("gcm-import"))
				if (isinstance(result, Exception) or not result) and gcm_import:
					# Fall back to gcm-import if colord profile install failed
					result = gcm_import
		if (not isinstance(result, Exception) and result and
			which("oyranos-monitor") and
			self.check_display_conf_oy_compat(getcfg("display.number"))):
			if device_id:
				profile_name = re.sub("[- ]", "_", device_id.lower()) + ".icc"
			else:
				profile_name = None
			result = self._install_profile_oy(profile_path, profile_name,
											  capture_output, skip_scripts,
											  silent)
			oy_install = result
		if not isinstance(result, Exception) and result:
			result = self._install_profile_argyll(profile_path, capture_output,
												  skip_scripts, silent)
			if isinstance(result, Exception) or not result:
				# Fedora's Argyll cannot install profiles using dispwin
				# Check if profile installation via colord or oyranos-monitor
				# was successful and continue
				if not isinstance(colord_install, Exception) and colord_install:
					result = colord_install
				elif not isinstance(oy_install, Exception) and oy_install:
					result = oy_install
		if not isinstance(result, Exception) and result:
			if getcfg("profile.install_scope") == "l":
				# We need a system-wide config file to store the path to 
				# the Argyll binaries
				result = config.makecfgdir("system", self)
				if result:
					result = config.writecfg("system", self)
				if not result:
					return Error(lang.getstr("error.autostart_system"))
			if sys.platform == "win32":
				if getcfg("profile.load_on_login"):
					result = self._install_profile_loader_win32(silent)
			elif sys.platform != "darwin":
				if getcfg("profile.load_on_login"):
					result = self._install_profile_loader_xdg(silent)
				if gcm_import:
					self._install_profile_gcm(profile_path)
			if not isinstance(result, Exception) and result and not gcm_import:
				if verbose >= 1: safe_print(lang.getstr("success"))
				if sys.platform == "darwin" and False:  # NEVER
					# If installing the profile by just copying it to the
					# right location, tell user to select it manually
					msg = lang.getstr("profile.install.osx_manual_select")
				else:
					msg = lang.getstr("profile.install.success")
				result = Info(msg)
		else:
			if result is not None:
				if verbose >= 1: safe_print(lang.getstr("failure"))
				result = Error(lang.getstr("profile.install.error"))
		return result
	
	def _install_profile_argyll(self, profile_path, capture_output=False,
								skip_scripts=False, silent=False):
		""" Install profile using dispwin """
		if (sys.platform == "darwin" and False):  # NEVER
			# Alternate way of 'installing' the profile under OS X by just
			# copying it
			profiles = os.path.join("Library", "ColorSync", "Profiles")
			profile_install_path = os.path.join(profiles,
												os.path.basename(profile_path))
			network = os.path.join(os.path.sep, "Network", profiles)
			if getcfg("profile.install_scope") == "l":
				profile_install_path = os.path.join(os.path.sep,
													profile_install_path)
			elif (getcfg("profile.install_scope") == "n" and
				  os.path.isdir(network)):
				profile_install_path = os.path.join(network,
													profile_install_path)
			else:
				profile_install_path = os.path.join(os.path.expanduser("~"),
													profile_install_path)
			cmd, args = "cp", ["-f", profile_path, profile_install_path]
			result = self.exec_cmd(cmd, args, capture_output, 
								   low_contrast=False, 
								   skip_scripts=skip_scripts, 
								   silent=silent,
								   asroot=getcfg("profile.install_scope") in ("l", "n"),
								   title=lang.getstr("profile.install"))
			if not isinstance(result, Exception) and result:
				self.output = ["Installed"]
		else:
			if (sys.platform == "win32" and
				sys.getwindowsversion() >= (6, ) and
				not util_win.per_user_profiles_isenabled()):
					# Enable per-user profiles under Vista / Windows 7
					try:
						util_win.enable_per_user_profiles(True,
														  getcfg("display.number") - 1)
					except Exception, exception:
						safe_print("util_win.enable_per_user_profiles(True, %s): %s" %
								   (getcfg("display.number") - 1,
									safe_unicode(exception)))
			cmd, args = self.prepare_dispwin(None, profile_path, True)
			if not isinstance(cmd, Exception):
				if "-Sl" in args and (sys.platform != "darwin" or 
									  intlist(mac_ver()[0].split(".")) >= [10, 6]):
					# If a 'system' install is requested under Linux,
					# Mac OS X >= 10.6 or Windows, 
					# install in 'user' scope first because a system-wide install 
					# doesn't also set it as current user profile on those systems 
					# (on Mac OS X < 10.6, we can use ColorSyncScripting to set it).
					# It has the small drawback under Linux and OS X 10.6 that 
					# it will copy the profile to both the user and system-wide 
					# locations, though, which is not a problem under Windows as 
					# they are the same.
					args.remove("-Sl")
					result = self.exec_cmd(cmd, args, capture_output, 
												  low_contrast=False, 
												  skip_scripts=skip_scripts, 
												  silent=silent,
												  title=lang.getstr("profile.install"))
					args.insert(0, "-Sl")
				else:
					result = True
				if not isinstance(result, Exception) and result:
					result = self.exec_cmd(cmd, args, capture_output, 
										   low_contrast=False, 
										   skip_scripts=skip_scripts, 
										   silent=silent,
										   title=lang.getstr("profile.install"))
			else:
				result = cmd
		if not isinstance(result, Exception) and result is not None:
			result = False
			for line in self.output:
				if "Installed" in line:
					if (sys.platform == "darwin" and "-Sl" in args and
					    intlist(mac_ver()[0].split(".")) < [10, 6]):
						# The profile has been installed, but we need a little 
						# help from AppleScript to actually make it the default 
						# for the current user. Only works under Mac OS < 10.6
						n = getcfg("display.number")
						path = os.path.join(os.path.sep, "Library", 
											"ColorSync", "Profiles", 
											os.path.basename(args[-1]))
						applescript = ['tell app "ColorSyncScripting"',
										   'set displayProfile to POSIX file "%s" as alias' % path,
										   'set display profile of display %i to displayProfile' % n,
									   'end tell']
						try:
							retcode, output, errors = osascript(applescript)
						except Exception, exception:
							safe_print(exception)
						else:
							if errors.strip():
								safe_print("osascript error: %s" % errors)
							else:
								result = True
						break
					elif (sys.platform == "darwin" and False):  # NEVER
						# After 'installing' a profile under Mac OS X by just
						# copying it, show system preferences
						applescript = ['tell application "System Preferences"',
										   'activate',
										   'set current pane to pane id "com.apple.preference.displays"',
										   'reveal (first anchor of current pane whose name is "displaysColorTab")',
										   # This needs access for assistive devices enabled
										   #'tell application "System Events"',
											   #'tell process "System Preferences"',
												   #'select row 2 of table 1 of scroll area 1 of group 1 of tab group 1 of window "<Display name from EDID here>"',
											   #'end tell',
										   #'end tell',
									   'end tell']
						try:
							retcode, output, errors = osascript(applescript)
						except Exception, exception:
							safe_print(exception)
						else:
							if errors.strip():
								safe_print("osascript error: %s" % errors)
							else:
								result = True
					else:
						result = True
					break
		self.wrapup(False)
		return result
	
	def _install_profile_colord(self, profile_path, device_id):
		""" Install profile using colord """
		try:
			colord.install_profile(device_id, profile_path)
		except Exception, exception:
			safe_print(exception)
			return exception
		return True
	
	def _install_profile_gcm(self, profile_path):
		""" Install profile using gcm-import """
		# Remove old profile so gcm-import can work
		profilename = os.path.basename(profile_path)
		for dirname in iccprofiles_home:
			profile_install_path = os.path.join(dirname, profilename)
			if os.path.isfile(profile_install_path) and \
			   profile_install_path != profile_path:
				try:
					trash([profile_install_path])
				except Exception, exception:
					safe_print(exception)
		# Run gcm-import
		cmd, args = which("gcm-import"), [profile_path]
		args = " ".join('"%s"' % arg for arg in args)
		safe_print('%s %s &' % (cmd, args))
		sp.call(('%s %s &' % (cmd,  args)).encode(fs_enc), shell=True)
	
	def _install_profile_oy(self, profile_path, profile_name=None,
							capture_output=False, skip_scripts=False,
							silent=False):
		""" Install profile using oyranos-monitor """
		display = self.displays[max(0, min(len(self.displays) - 1,
										   getcfg("display.number") - 1))]
		x, y = [pos.strip() for pos in display.split(" @")[1].split(",")[0:2]]
		if getcfg("profile.install_scope") == "l":
			# If system-wide install, copy profile to 
			# /var/lib/color/icc/devices/display
			var_icc = "/var/lib/color/icc/devices/display"
			if not profile_name:
				profile_name = os.path.basename(profile_path)
			profile_install_path = os.path.join(var_icc, profile_name)
			result = self.exec_cmd("mkdir", 
								   ["-p", os.path.dirname(profile_install_path)], 
								   capture_output=True, low_contrast=False, 
								   skip_scripts=True, silent=True, asroot=True)
			if not isinstance(result, Exception) and result:
				result = self.exec_cmd("cp", ["-f", profile_path, 
											  profile_install_path], 
									   capture_output=True, low_contrast=False, 
									   skip_scripts=True, silent=True, 
									   asroot=True)
		else:
			result = True
			dirname = None
			for dirname in iccprofiles_display_home:
				if os.path.isdir(dirname):
					# Use the first one that exists
					break
				else:
					dirname = None
			if not dirname:
				# Create the first one in the list
				dirname = iccprofiles_display_home[0]
				try:
					os.makedirs(dirname)
				except Exception, exception:
					safe_print(exception)
					result = False
			if result is not False:
				profile_install_path = os.path.join(dirname,
													os.path.basename(profile_path))
				try:
					shutil.copyfile(profile_path, 
									profile_install_path)
				except Exception, exception:
					safe_print(exception)
					result = False
		if not isinstance(result, Exception) and result is not False:
			cmd = which("oyranos-monitor")
			args = ["-x", x, "-y", y, profile_install_path]
			result = self.exec_cmd(cmd, args, capture_output, 
								  low_contrast=False, skip_scripts=skip_scripts, 
								  silent=silent, working_dir=False)
			##if getcfg("profile.install_scope") == "l":
				##result = self.exec_cmd(cmd, args, 
											  ##capture_output, 
											  ##low_contrast=False, 
											  ##skip_scripts=skip_scripts, 
											  ##silent=silent,
											  ##asroot=True,
											  ##working_dir=False)
		return result
	
	def _install_profile_loader_win32(self, silent=False):
		""" Install profile loader """
		if (sys.platform == "win32" and sys.getwindowsversion() >= (6, 1) and
			util_win.calibration_management_isenabled()):
			self._uninstall_profile_loader_win32()
			return True
		# Must return either True on success or an Exception object on error
		result = True
		# Remove outdated (pre-0.5.5.9) profile loaders
		display_no = self.get_display()
		name = "%s Calibration Loader (Display %s)" % (appname, display_no)
		if autostart_home:
			loader_v01b = os.path.join(autostart_home, 
									   ("dispwin-d%s-c-L" % display_no) + 
									   ".lnk")
			if os.path.exists(loader_v01b):
				try:
					# delete v0.1b loader
					os.remove(loader_v01b)
				except Exception, exception:
					safe_print(u"Warning - could not remove old "
							   u"v0.1b calibration loader '%s': %s" 
							   % tuple(safe_unicode(s) for s in 
									   (loader_v01b, exception)))
			loader_v02b = os.path.join(autostart_home, 
									   name + ".lnk")
			if os.path.exists(loader_v02b):
				try:
					# delete v02.b/v0.2.1b loader
					os.remove(loader_v02b)
				except Exception, exception:
					safe_print(u"Warning - could not remove old "
							   u"v0.2b calibration loader '%s': %s" 
							   % tuple(safe_unicode(s) for s in 
									   (loader_v02b, exception)))
			loader_v0558 = os.path.join(autostart_home, 
										name + ".lnk")
			if os.path.exists(loader_v0558):
				try:
					# delete v0.5.5.8 user loader
					os.remove(loader_v0558)
				except Exception, exception:
					safe_print(u"Warning - could not remove old "
							   u"v0.2b calibration loader '%s': %s" 
							   % tuple(safe_unicode(s) for s in 
									   (loader_v02b, exception)))
		if autostart:
			loader_v0558 = os.path.join(autostart, 
										name + ".lnk")
			if os.path.exists(loader_v0558):
				try:
					# delete v0.5.5.8 system loader
					os.remove(loader_v0558)
				except Exception, exception:
					safe_print(u"Warning - could not remove old "
							   u"v0.2b calibration loader '%s': %s" 
							   % tuple(safe_unicode(s) for s in 
									   (loader_v02b, exception)))
		# Create unified loader
		name = appname + " Profile Loader"
		if autostart:
			autostart_lnkname = os.path.join(autostart,
											 name + ".lnk")
		if autostart_home:
			autostart_home_lnkname = os.path.join(autostart_home, 
												  name + ".lnk")
		loader_args = []
		if os.path.basename(sys.executable) in ("python.exe", 
												"pythonw.exe"):
			cmd = sys.executable
		else:
			# Skip 'import site'
			loader_args += ["-S"]
			cmd = os.path.join(pydir, "lib", "pythonw.exe")
		loader_args += [u'"%s"' % get_data_path(os.path.join("scripts", 
															 "dispcalGUI-apply-profiles"))]
		try:
			scut = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
											  pythoncom.CLSCTX_INPROC_SERVER, 
											  shell.IID_IShellLink)
			scut.SetPath(cmd)
			scut.SetWorkingDirectory(pydir)
			if isexe:
				scut.SetIconLocation(exe, 0)
			else:
				scut.SetIconLocation(get_data_path(os.path.join("theme",
																"icons", 
																appname +
																".ico")), 0)
			scut.SetArguments(" ".join(loader_args))
			scut.SetShowCmd(win32con.SW_SHOWMINNOACTIVE)
			if is_superuser():
				if autostart:
					try:
						scut.QueryInterface(pythoncom.IID_IPersistFile).Save(autostart_lnkname, 0)
					except Exception, exception:
						if not silent:
							result = Warning(lang.getstr("error.autostart_creation", 
													     autostart) + "\n\n" + 
										     safe_unicode(exception))
						# Now try user scope
				else:
					if not silent:
						result = Warning(lang.getstr("error.autostart_system"))
			if autostart_home:
				if (autostart and 
					os.path.isfile(autostart_lnkname)):
					# Remove existing user loader
					if os.path.isfile(autostart_home_lnkname):
						os.remove(autostart_home_lnkname)
				else:
					# Only create user loader if no system loader
					scut.QueryInterface(
						pythoncom.IID_IPersistFile).Save(
							os.path.join(autostart_home_lnkname), 0)
			else:
				if not silent:
					result = Warning(lang.getstr("error.autostart_user"))
		except Exception, exception:
			if not silent:
				result = Warning(lang.getstr("error.autostart_creation", 
										     autostart_home) + "\n\n" + 
							     safe_unicode(exception))
		return result
	
	def _uninstall_profile_loader_win32(self):
		""" Uninstall profile loader """
		name = appname + " Profile Loader"
		if autostart:
			autostart_lnkname = os.path.join(autostart,
											 name + ".lnk")
		if autostart_home:
			autostart_home_lnkname = os.path.join(autostart_home, 
												  name + ".lnk")
		if os.path.exists(autostart_home_lnkname):
			try:
				os.remove(autostart_home_lnkname)
			except Exception, exception:
				safe_print(autostart_home_lnkname, exception)
		if os.path.exists(autostart_lnkname) and is_superuser():
			try:
				os.remove(autostart_lnkname)
			except Exception, exception:
				safe_print(autostart_lnkname, exception)
		return True
	
	def _install_profile_loader_xdg(self, silent=False):
		""" Install profile loader """
		# See http://standards.freedesktop.org/autostart-spec
		# Must return either True on success or an Exception object on error
		result = True
		# Remove outdated (pre-0.5.5.9) profile loaders
		name = "%s-Calibration-Loader-Display-%s" % (appname,
													 self.get_display())
		desktopfile_path = os.path.join(autostart_home, 
										name + ".desktop")
		oy_desktopfile_path = os.path.join(autostart_home, 
										   "oyranos-monitor.desktop")
		system_desktopfile_path = os.path.join(
			autostart, name + ".desktop")
		# Remove old (pre-0.5.5.9) dispwin user loader
		if os.path.exists(desktopfile_path):
			try:
				os.remove(desktopfile_path)
			except Exception, exception:
				result = Warning(lang.getstr("error.autostart_remove_old", 
										     desktopfile_path))
		# Remove old (pre-0.5.5.9) oyranos user loader
		if os.path.exists(oy_desktopfile_path):
			try:
				os.remove(oy_desktopfile_path)
			except Exception, exception:
				result = Warning(lang.getstr("error.autostart_remove_old", 
										     oy_desktopfile_path))
		# Remove old (pre-0.5.5.9) dispwin system loader
		if (os.path.exists(system_desktopfile_path) and
		    (self.exec_cmd("rm", ["-f", system_desktopfile_path], 
								 capture_output=True, low_contrast=False, 
								 skip_scripts=True, silent=False, asroot=True, 
								 title=lang.getstr("autostart_remove_old")) 
			 is not True) and not silent):
			result = Warning(lang.getstr("error.autostart_remove_old", 
									     system_desktopfile_path))
		# Create unified loader
		# Prepend 'z' so our loader hopefully loads after
		# possible nvidia-settings entry (which resets gamma table)
		name = "z-%s-apply-profiles" % appname
		desktopfile_path = os.path.join(autostart_home, 
										name + ".desktop")
		system_desktopfile_path = os.path.join(autostart, name + ".desktop")
		if not os.path.exists(system_desktopfile_path) and \
		   not os.path.exists(desktopfile_path):
			try:
				# Create user loader, even if we later try to 
				# move it to the system-wide location so that atleast 
				# the user loader is present if the move to the system 
				# dir fails
				if not os.path.exists(autostart_home):
					os.makedirs(autostart_home)
				desktopfile = open(desktopfile_path, "w")
				desktopfile.write('[Desktop Entry]\n')
				desktopfile.write('Version=1.0\n')
				desktopfile.write('Encoding=UTF-8\n')
				desktopfile.write('Type=Application\n')
				desktopfile.write('Name=%s\n' % (appname + 
												 ' Profile Loader').encode("UTF-8"))
				desktopfile.write('Comment=%s\n' % 
								  lang.getstr("calibrationloader.description", 
											  lcode="en").encode("UTF-8"))
				if lang.getcode() != "en":
					desktopfile.write(('Comment[%s]=%s\n' % 
									   (lang.getcode(),
										lang.getstr("calibrationloader.description"))).encode("UTF-8"))
				desktopfile.write('Icon=%s\n' % appname.encode("UTF-8"))
				desktopfile.write('Exec=%s-apply-profiles\n' % appname.encode("UTF-8"))
				desktopfile.write('Terminal=false\n')
				desktopfile.close()
			except Exception, exception:
				if not silent:
					result = Warning(lang.getstr("error.autostart_creation", 
											     desktopfile_path) + "\n\n" + 
								     safe_unicode(exception))
			else:
				if getcfg("profile.install_scope") == "l" and autostart:
					# Move system-wide loader
					if (self.exec_cmd("mkdir", 
											 ["-p", autostart], 
											 capture_output=True, 
											 low_contrast=False, 
											 skip_scripts=True, 
											 silent=True, 
											 asroot=True) is not True or 
						self.exec_cmd("mv", 
											 ["-f", 
											  desktopfile_path, 
											  system_desktopfile_path], 
											 capture_output=True, 
											 low_contrast=False, 
											 skip_scripts=True, 
											 silent=True, 
											 asroot=True) is not True) and \
					   not silent:
						result = Warning(lang.getstr("error.autostart_creation", 
												     system_desktopfile_path))
		return result
	
	def instrument_supports_ccss(self):
		instrument_name = self.get_instrument_name()
		return ("i1 DisplayPro, ColorMunki Display" in instrument_name or
				"Spyder4" in instrument_name)
	
	def create_ccxx(self, args=None, working_dir=None):
		""" Create CCMX or CCSS """
		if not args:
			args = []
		cmd = get_argyll_util("ccxxmake")
		if not "-I" in args:
			# Display manufacturer & name
			name = self.get_display_name(True)
			if name:
				args.insert(0, "-I")
				args.insert(1, name)
			elif not "-T" in args:
				# Display technology
				args.insert(0, "-T")
				displaytech = ["LCD" if getcfg("measurement_mode") == "l" else "CRT"]
				if (self.get_instrument_features().get("projector_mode") and 
					getcfg("measurement_mode.projector")):
					displaytech.append("Projector")
				args.insert(1, " ".join(displaytech))
		return self.exec_cmd(cmd, ["-v"] + args, capture_output=True, 
							 skip_scripts=True, silent=False,
							 working_dir=working_dir)

	def is_working(self):
		""" Check if the Worker instance is busy. Return True or False. """
		return not getattr(self, "finished", True)

	def prepare_colprof(self, profile_name=None, display_name=None,
						display_manufacturer=None):
		"""
		Prepare a colprof commandline.
		
		All options are read from the user configuration.
		Profile name and display name can be ovverridden by passing the
		corresponding arguments.
		
		"""
		profile_save_path = self.create_tempdir()
		if not profile_save_path or isinstance(profile_save_path, Exception):
			return profile_save_path, None
		# Check directory and in/output file(s)
		result = check_create_dir(profile_save_path)
		if isinstance(result, Exception):
			return result, None
		if profile_name is None:
			profile_name = getcfg("profile.name.expanded")
		inoutfile = os.path.join(profile_save_path, 
								 make_argyll_compatible_path(profile_name))
		if not os.path.exists(inoutfile + ".ti3"):
			return Error(lang.getstr("error.measurement.file_missing", 
									 inoutfile + ".ti3")), None
		if not os.path.isfile(inoutfile + ".ti3"):
			return Error(lang.getstr("error.measurement.file_notfile", 
									 inoutfile + ".ti3")), None
		#
		cmd = get_argyll_util("colprof")
		args = []
		args += ["-v"] # verbose
		args += ["-q" + getcfg("profile.quality")]
		args += ["-a" + getcfg("profile.type")]
		if getcfg("profile.type") in ["l", "x", "X"]:
			if getcfg("gamap_saturation"):
				gamap = "S"
			elif getcfg("gamap_perceptual"):
				gamap = "s"
			else:
				gamap = None
			if gamap:
				args += ["-" + gamap]
				args += [getcfg("gamap_profile")]
				args += ["-t" + getcfg("gamap_perceptual_intent")]
				if gamap == "S":
					args += ["-T" + getcfg("gamap_saturation_intent")]
				if getcfg("gamap_src_viewcond"):
					args += ["-c" + getcfg("gamap_src_viewcond")]
				if getcfg("gamap_out_viewcond"):
					args += ["-d" + getcfg("gamap_out_viewcond")]
		args += ["-C"]
		args += [getcfg("copyright").encode("ASCII", "asciize")]
		if getcfg("extra_args.colprof").strip():
			args += parse_argument_string(getcfg("extra_args.colprof"))
		options_dispcal = None
		if "-d3" in self.options_targen:
			# only add display desc and dispcal options if creating RGB profile
			options_dispcal = self.options_dispcal
			if len(self.displays):
				args.extend(
					self.update_display_name_manufacturer(inoutfile + ".ti3", 
														  display_name,
														  display_manufacturer, 
														  write=False))
		self.options_colprof = list(args)
		args += ["-D"]
		args += [profile_name]
		args += [inoutfile]
		# Add dispcal and colprof arguments to ti3
		ti3 = add_options_to_ti3(inoutfile + ".ti3", options_dispcal, 
								 self.options_colprof)
		if ti3:
			# Prepare ChromaticityType tag
			colorants = ti3.get_colorants()
			if colorants and not None in colorants:
				color_rep = ti3.queryv1("COLOR_REP").split("_")
				chrm = ICCP.ChromaticityType()
				chrm.type = 0
				for colorant in colorants:
					if color_rep[1] == "LAB":
						XYZ = colormath.Lab2XYZ(colorant["LAB_L"],
												colorant["LAB_A"],
												colorant["LAB_B"])
					else:
						XYZ = (colorant["XYZ_X"], colorant["XYZ_Y"],
							   colorant["XYZ_Z"])
					chrm.channels.append(colormath.XYZ2xyY(*XYZ)[:-1])
				with open(inoutfile + ".chrm", "wb") as blob:
					blob.write(chrm.tagData)
			# Black point compensation
			ti3[0].add_keyword("USE_BLACK_POINT_COMPENSATION",
							   "YES" if getcfg("profile.black_point_compensation")
							   else "NO")
			if getcfg("profile.black_point_compensation"):
				# Backup TI3
				ti3.write(inoutfile + ".ti3.backup")
				# Apply black point compensation
				ti3.apply_bpc()
			ti3.write()
		return cmd, args

	def prepare_dispcal(self, calibrate=True, verify=False, dry_run=False):
		"""
		Prepare a dispcal commandline.
		
		All options are read from the user configuration.
		You can choose if you want to calibrate and/or verify by passing 
		the corresponding arguments.
		
		"""
		cmd = get_argyll_util("dispcal")
		args = []
		args += ["-v2"] # verbose
		if getcfg("argyll.debug"):
			args += ["-D6"]
		result = self.add_measurement_features(args)
		if isinstance(result, Exception):
			return result, None
		if calibrate:
			args += ["-q" + getcfg("calibration.quality")]
			profile_save_path = self.create_tempdir()
			if not profile_save_path or isinstance(profile_save_path, Exception):
				return profile_save_path, None
			# Check directory and in/output file(s)
			result = check_create_dir(profile_save_path)
			if isinstance(result, Exception):
				return result, None
			inoutfile = os.path.join(profile_save_path, 
									 make_argyll_compatible_path(getcfg("profile.name.expanded")))
			if getcfg("profile.update") or \
			   self.dispcal_create_fast_matrix_shaper:
				args += ["-o"]
			if getcfg("calibration.update") and not dry_run:
				cal = getcfg("calibration.file")
				calcopy = os.path.join(inoutfile + ".cal")
				filename, ext = os.path.splitext(cal)
				ext = ".cal"
				cal = filename + ext
				if ext.lower() == ".cal":
					result = check_cal_isfile(cal)
					if isinstance(result, Exception):
						return result, None
					if not result:
						return None, None
					if not os.path.exists(calcopy):
						try:
							# Copy cal to profile dir
							shutil.copyfile(cal, calcopy) 
						except Exception, exception:
							return Error(lang.getstr("error.copy_failed", 
													 (cal, calcopy)) + 
													 "\n\n" + 
													 safe_unicode(exception)), None
						result = check_cal_isfile(calcopy)
						if isinstance(result, Exception):
							return result, None
						if not result:
							return None, None
						cal = calcopy
				else:
					rslt = extract_fix_copy_cal(cal, calcopy)
					if isinstance(rslt, ICCP.ICCProfileInvalidError):
						return Error(lang.getstr("profile.invalid") + 
									 "\n" + cal), None
					elif isinstance(rslt, Exception):
						return Error(lang.getstr("cal_extraction_failed") + 
									 "\n" + cal + "\n\n" + 
									 unicode(str(rslt),  enc, "replace")), None
					if not isinstance(rslt, list):
						return None, None
				if getcfg("profile.update"):
					profile_path = os.path.splitext(
						getcfg("calibration.file"))[0] + profile_ext
					result = check_profile_isfile(profile_path)
					if isinstance(result, Exception):
						return result, None
					if not result:
						return None, None
					profilecopy = os.path.join(inoutfile + profile_ext)
					if not os.path.exists(profilecopy):
						try:
							# Copy profile to profile dir
							shutil.copyfile(profile_path, profilecopy)
						except Exception, exception:
							return Error(lang.getstr("error.copy_failed", 
													   (profile_path, 
													    profilecopy)) + 
										   "\n\n" + safe_unicode(exception)), None
						result = check_profile_isfile(profilecopy)
						if isinstance(result, Exception):
							return result, None
						if not result:
							return None, None
				args += ["-u"]
		##if (calibrate and not getcfg("calibration.update")) or \
		   ##(not calibrate and verify):
		if calibrate or verify:
			if calibrate and not \
			   getcfg("calibration.interactive_display_adjustment"):
				# Skip interactive display adjustment
				args += ["-m"]
			whitepoint_colortemp = getcfg("whitepoint.colortemp", False)
			whitepoint_x = getcfg("whitepoint.x", False)
			whitepoint_y = getcfg("whitepoint.y", False)
			if whitepoint_colortemp or None in (whitepoint_x, whitepoint_y):
				whitepoint = getcfg("whitepoint.colortemp.locus")
				if whitepoint_colortemp:
					whitepoint += str(whitepoint_colortemp)
				args += ["-" + whitepoint]
			else:
				args += ["-w%s,%s" % (whitepoint_x, whitepoint_y)]
			luminance = getcfg("calibration.luminance", False)
			if luminance:
				args += ["-b%s" % luminance]
			args += ["-" + getcfg("trc.type") + str(getcfg("trc"))]
			args += ["-f%s" % getcfg("calibration.black_output_offset")]
			if bool(int(getcfg("calibration.ambient_viewcond_adjust"))):
				args += ["-a%s" % 
						 getcfg("calibration.ambient_viewcond_adjust.lux")]
			if not getcfg("calibration.black_point_correction.auto"):
				args += ["-k%s" % getcfg("calibration.black_point_correction")]
			if defaults["calibration.black_point_rate.enabled"] and \
			   float(getcfg("calibration.black_point_correction")) < 1:
				black_point_rate = getcfg("calibration.black_point_rate")
				if black_point_rate:
					args += ["-A%s" % black_point_rate]
			black_luminance = getcfg("calibration.black_luminance", False)
			if black_luminance:
				args += ["-B%f" % black_luminance]
			if verify:
				if calibrate and type(verify) == int:
					args += ["-e%s" % verify]  # Verify final computed curves
				else:
					args += ["-E"]  # Verify current curves
		if getcfg("extra_args.dispcal").strip():
			args += parse_argument_string(getcfg("extra_args.dispcal"))
		self.options_dispcal = list(args)
		if calibrate:
			args += [inoutfile]
		return cmd, args

	def prepare_dispread(self, apply_calibration=True):
		"""
		Prepare a dispread commandline.
		
		All options are read from the user configuration.
		You can choose if you want to apply the current calibration,
		either the previously by dispcal created one by passing in True, by
		passing in a valid path to a .cal file, or by passing in None
		(current video card gamma table).
		
		"""
		profile_save_path = self.create_tempdir()
		if not profile_save_path or isinstance(profile_save_path, Exception):
			return profile_save_path, None
		# Check directory and in/output file(s)
		result = check_create_dir(profile_save_path)
		if isinstance(result, Exception):
			return result, None
		inoutfile = os.path.join(profile_save_path, 
								 make_argyll_compatible_path(getcfg("profile.name.expanded")))
		if not os.path.exists(inoutfile + ".ti1"):
			filename, ext = os.path.splitext(getcfg("testchart.file"))
			result = check_file_isfile(filename + ext)
			if isinstance(result, Exception):
				return result, None
			try:
				if ext.lower() in (".icc", ".icm"):
					try:
						profile = ICCP.ICCProfile(filename + ext)
					except (IOError, ICCP.ICCProfileInvalidError), exception:
						return Error(lang.getstr("error.testchart.read", 
												 getcfg("testchart.file"))), None
					ti3 = StringIO(profile.tags.get("CIED", "") or 
								   profile.tags.get("targ", ""))
				elif ext.lower() == ".ti1":
					shutil.copyfile(filename + ext, inoutfile + ".ti1")
				else: # ti3
					try:
						ti3 = open(filename + ext, "rU")
					except Exception, exception:
						return Error(lang.getstr("error.testchart.read", 
												 getcfg("testchart.file"))), None
				if ext.lower() != ".ti1":
					ti3_lines = [line.strip() for line in ti3]
					ti3.close()
					if not "CTI3" in ti3_lines:
						return Error(lang.getstr("error.testchart.invalid", 
												 getcfg("testchart.file"))), None
					ti1 = open(inoutfile + ".ti1", "w")
					ti1.write(ti3_to_ti1(ti3_lines))
					ti1.close()
			except Exception, exception:
				return Error(lang.getstr("error.testchart.creation_failed", 
										 inoutfile + ".ti1") + "\n\n" + 
							 safe_unicode(exception)), None
		if apply_calibration is not False:
			if apply_calibration is True:
				# Always a .cal file in that case
				cal = os.path.join(getcfg("profile.save_path"), 
								   getcfg("profile.name.expanded"), 
								   getcfg("profile.name.expanded")) + ".cal"
			elif apply_calibration is None:
				result = None
				if self.argyll_version >= [1, 1, 0]:
					cal = inoutfile + ".cal"
					cmd, args = (get_argyll_util("dispwin"), 
								 ["-d" + self.get_display(), "-s", cal])
					result = self.exec_cmd(cmd, args, capture_output=True, 
										   skip_scripts=True, silent=True)
					if isinstance(result, Exception):
						return result, None
				if not result:
					return Error(lang.getstr("calibration.load_error")), None
			else:
				cal = apply_calibration # can be .cal or .icc / .icm
			calcopy = inoutfile + ".cal"
			filename, ext = os.path.splitext(cal)
			if ext.lower() == ".cal":
				result = check_cal_isfile(cal)
				if isinstance(result, Exception):
					return result, None
				if not result:
					return None, None
				# Get dispcal options if present
				options_dispcal = get_options_from_cal(cal)[0]
				if not os.path.exists(calcopy):
					try:
						# Copy cal to temp dir
						shutil.copyfile(cal, calcopy)
					except Exception, exception:
						return Error(lang.getstr("error.copy_failed", 
												 (cal, calcopy)) + "\n\n" + 
									 safe_unicode(exception)), None
					result = check_cal_isfile(calcopy)
					if isinstance(result, Exception):
						return result, None
					if not result:
						return None, None
			else:
				# .icc / .icm
				result = check_profile_isfile(cal)
				if isinstance(result, Exception):
					return result, None
				if not result:
					return None, None
				try:
					profile = ICCP.ICCProfile(filename + ext)
				except (IOError, ICCP.ICCProfileInvalidError), exception:
					profile = None
				if profile:
					ti3 = StringIO(profile.tags.get("CIED", "") or 
								   profile.tags.get("targ", ""))
					# Get dispcal options if present
					options_dispcal = get_options_from_profile(profile)[0]
				else:
					ti3 = StringIO("")
				ti3_lines = [line.strip() for line in ti3]
				ti3.close()
				if not "CTI3" in ti3_lines:
					return Error(lang.getstr("error.cal_extraction", 
											 (cal))), None
				try:
					tmpcal = open(calcopy, "w")
					tmpcal.write(extract_cal_from_ti3(ti3_lines))
					tmpcal.close()
				except Exception, exception:
					return Error(lang.getstr("error.cal_extraction", (cal)) + 
								 "\n\n" + safe_unicode(exception)), None
			cal = calcopy
			if options_dispcal:
				self.options_dispcal = ["-" + arg for arg in options_dispcal]
		#
		# Make sure any measurement options are present
		if not self.options_dispcal:
			self.prepare_dispcal(dry_run=True)
		# Special case -X because it can have a separate filename argument
		if "-X" in self.options_dispcal:
			index = self.options_dispcal.index("-X")
			if (len(self.options_dispcal) > index + 1 and
				self.options_dispcal[index + 1][0] != "-"):
				self.options_dispcal = (self.options_dispcal[:index] +
										self.options_dispcal[index + 2:])
		# Strip options we may override (basically all the stuff which can be 
		# added by add_measurement_features. -X is repeated because it can
		# have a number instead of explicit filename argument, e.g. -X1)
		dispcal_override_args = ("-F", "-H", "-I", "-P", "-V", "-X", "-d", "-c", 
								 "-p", "-y")
		self.options_dispcal = filter(lambda arg: not arg[:2] in dispcal_override_args, 
									  self.options_dispcal)
		# Only add the dispcal extra args which may override measurement features
		dispcal_extra_args = parse_argument_string(getcfg("extra_args.dispcal"))
		for i, arg in enumerate(dispcal_extra_args):
			if not arg.startswith("-") and i > 0:
				# Assume option to previous arg
				arg = dispcal_extra_args[i - 1]
			if arg[:2] in dispcal_override_args:
				self.options_dispcal += [dispcal_extra_args[i]]
		result = self.add_measurement_features(self.options_dispcal)
		if isinstance(result, Exception):
			return result, None
		cmd = get_argyll_util("dispread")
		args = []
		args += ["-v"] # verbose
		if getcfg("argyll.debug"):
			args += ["-D6"]
		result = self.add_measurement_features(args)
		if isinstance(result, Exception):
			return result, None
		# TTBD/FIXME: Skipping of sensor calibration can't be done in
		# emissive mode (see Argyll source spectro/ss.c, around line 40)
		if getcfg("allow_skip_sensor_cal") and self.dispread_after_dispcal and \
		   (self.get_instrument_features().get("skip_sensor_cal") or test) and \
		   self.argyll_version >= [1, 1, 0]:
			args += ["-N"]
		if apply_calibration is not False:
			args += ["-k"]
			args += [cal]
		if self.get_instrument_features().get("spectral"):
			args += ["-s"]
		if getcfg("extra_args.dispread").strip():
			args += parse_argument_string(getcfg("extra_args.dispread"))
		self.options_dispread = list(args)
		return cmd, self.options_dispread + [inoutfile]

	def prepare_dispwin(self, cal=None, profile_path=None, install=True):
		"""
		Prepare a dispwin commandline.
		
		All options are read from the user configuration.
		If you pass in cal as True, it will try to load the current 
		display profile's calibration. If cal is a path, it'll use
		that instead. If cal is False, it'll clear the current calibration.
		If cal is None, it'll try to load the calibration from a profile
		specified by profile_path.
		
		"""
		cmd = get_argyll_util("dispwin")
		args = []
		args += ["-v"]
		if getcfg("argyll.debug"):
			if self.argyll_version >= [1, 3, 1]:
				args += ["-D6"]
			else:
				args += ["-E6"]
		args += ["-d" + self.get_display()]
		if sys.platform != "darwin" or cal is False:
			# Mac OS X 10.7 Lion needs root privileges when clearing 
			# calibration
			args += ["-c"]
		if cal is True:
			args += [self.get_dispwin_display_profile_argument(
						max(0, min(len(self.displays), 
								   getcfg("display.number")) - 1))]
		elif cal:
			result = check_cal_isfile(cal)
			if isinstance(result, Exception):
				return result, None
			if not result:
				return None, None
			args += [cal]
		else:
			if cal is None:
				if not profile_path:
					profile_save_path = os.path.join(
						getcfg("profile.save_path"), 
						getcfg("profile.name.expanded"))
					profile_path = os.path.join(profile_save_path, 
						getcfg("profile.name.expanded") + profile_ext)
				result = check_profile_isfile(profile_path)
				if isinstance(result, Exception):
					return result, None
				if not result:
					return None, None
				try:
					profile = ICCP.ICCProfile(profile_path)
				except (IOError, ICCP.ICCProfileInvalidError), exception:
					return Error(lang.getstr("profile.invalid") + 
											 "\n" + profile_path), None
				if profile.profileClass != "mntr" or \
				   profile.colorSpace != "RGB":
					return Error(lang.getstr("profile.unsupported", 
											 (profile.profileClass, 
											  profile.colorSpace)) + 
								   "\n" + profile_path), None
				if install:
					if getcfg("profile.install_scope") != "u" and \
						(((sys.platform == "darwin" or 
						   (sys.platform != "win32" and 
							self.argyll_version >= [1, 1, 0])) and 
						  (os.geteuid() == 0 or which("sudo"))) or 
						 (sys.platform == "win32" and 
						  sys.getwindowsversion() >= (6, ) and 
						  self.argyll_version > [1, 1, 1]) or test):
							# -S option is broken on Linux with current Argyll 
							# releases
							args += ["-S" + getcfg("profile.install_scope")]
					args += ["-I"]
					if (sys.platform in ("win32", "darwin") or 
						fs_enc.upper() not in ("UTF8", "UTF-8")) and \
					   re.search("[^\x20-\x7e]", 
								 os.path.basename(profile_path)):
						# Copy to temp dir and give unique ASCII-only name to
						# avoid profile install issues
						tmp_dir = self.create_tempdir()
						if not tmp_dir or isinstance(tmp_dir, Exception):
							return tmp_dir, None
						# Check directory and in/output file(s)
						result = check_create_dir(tmp_dir)
						if isinstance(result, Exception):
							return result, None
						# profile name: 'display<n>-<hexmd5sum>.icc'
						profile_tmp_path = os.path.join(tmp_dir, "display" + 
														self.get_display() + 
														"-" + 
														md5(profile.data).hexdigest() + 
														profile_ext)
						shutil.copyfile(profile_path, profile_tmp_path)
						profile_path = profile_tmp_path
				args += [profile_path]
		return cmd, args

	def prepare_targen(self):
		"""
		Prepare a targen commandline.
		
		All options are read from the user configuration.
		
		"""
		path = self.create_tempdir()
		if not path or isinstance(path, Exception):
			return path, None
		# Check directory and in/output file(s)
		result = check_create_dir(path)
		if isinstance(result, Exception):
			return result, None
		inoutfile = os.path.join(path, "temp")
		cmd = get_argyll_util("targen")
		args = []
		args += ['-v']
		args += ['-d3']
		args += ['-e%s' % getcfg("tc_white_patches")]
		args += ['-s%s' % getcfg("tc_single_channel_patches")]
		args += ['-g%s' % getcfg("tc_gray_patches")]
		args += ['-m%s' % getcfg("tc_multi_steps")]
		if getcfg("tc_fullspread_patches") > 0:
			args += ['-f%s' % config.get_total_patches()]
			tc_algo = getcfg("tc_algo")
			if tc_algo:
				args += ['-' + tc_algo]
			if tc_algo in ("i", "I"):
				args += ['-a%s' % getcfg("tc_angle")]
			if tc_algo == "":
				args += ['-A%s' % getcfg("tc_adaption")]
			if getcfg("tc_precond") and getcfg("tc_precond_profile"):
				args += ['-c']
				args += [getcfg("tc_precond_profile")]
			if getcfg("tc_filter"):
				args += ['-F%s,%s,%s,%s' % (getcfg("tc_filter_L"), 
											getcfg("tc_filter_a"), 
											getcfg("tc_filter_b"), 
											getcfg("tc_filter_rad"))]
		else:
			args += ['-f0']
		if getcfg("tc_vrml_lab"):
			args += ['-w']
		if getcfg("tc_vrml_device"):
			args += ['-W']
		self.options_targen = list(args)
		args += [inoutfile]
		return cmd, args

	def progress_handler(self, event):
		if getattr(self, "subprocess_abort", False) or \
		   getattr(self, "thread_abort", False):
			self.progress_wnd.Pulse(lang.getstr("aborting"))
			return
		self.check_instrument_calibration()
		percentage = None
		msg = self.recent.read(FilteredStream.triggers)
		lastmsg = self.lastmsg.read(FilteredStream.triggers).strip()
		if re.match("\\s*\\d+%", lastmsg):
			# colprof
			try:
				percentage = int(self.lastmsg.read().strip("%"))
			except ValueError:
				pass
		elif re.match("Patch \\d+ of \\d+", lastmsg, re.I):
			# dispcal/dispread
			components = lastmsg.split()
			try:
				start = float(components[1])
				end = float(components[3])
			except ValueError:
				pass
			else:
				percentage = start / end * 100
		elif re.match("Added \\d+/\\d+", lastmsg, re.I):
			# targen
			components = lastmsg.lower().replace("added ", "").split("/")
			try:
				start = float(components[0])
				end = float(components[1])
			except ValueError:
				pass
			else:
				percentage = start / end * 100
		if not test and percentage and self.progress_wnd is getattr(self, "terminal", None):
			# We no longer need keyboard interaction, switch over to
			# progress dialog
			wx.CallAfter(self.swap_progress_wnds)
		if getattr(self.progress_wnd, "original_msg", None) and \
		   msg != self.progress_wnd.original_msg:
			# UGLY HACK: This 'safe_print' call fixes a GTK assertion and 
			# segfault under Arch Linux when setting the window title
			safe_print("")
			self.progress_wnd.SetTitle(self.progress_wnd.original_msg)
			self.progress_wnd.original_msg = None
		if percentage:
			if "Setting up the instrument" in msg or \
			   "Commencing device calibration" in msg or \
			   "Calibration complete" in msg:
				self.recent.clear()
				msg = ""
			keepGoing, skip = self.progress_wnd.Update(math.ceil(percentage), 
													   msg + "\n" + 
													   lastmsg)
		else:
			if getattr(self.progress_wnd, "lastmsg", "") == msg or not msg:
				keepGoing, skip = self.progress_wnd.Pulse()
			else:
				if "Setting up the instrument" in lastmsg:
					msg = lang.getstr("instrument.initializing")
				keepGoing, skip = self.progress_wnd.Pulse(msg)
		if not keepGoing:
			if getattr(self, "subprocess", None) and \
			   not getattr(self, "subprocess_abort", False):
				if debug:
					safe_print('[D] calling quit_terminate_cmd')
				self.abort_subprocess()
			elif not getattr(self, "thread_abort", False):
				if debug:
					safe_print('[D] thread_abort')
				self.thread_abort = True
		if self.finished is True:
			return
		if not self.activated and self.progress_wnd.IsShownOnScreen() and \
		   (not wx.GetApp().IsActive() or not self.progress_wnd.IsActive()):
		   	self.activated = True
			self.progress_wnd.Raise()

	def progress_dlg_start(self, progress_title="", progress_msg="", 
						   parent=None, resume=False):
		if getattr(self, "progress_dlg", None) and not resume:
			self.progress_dlg.Destroy()
			self.progress_dlg = None
		if getattr(self, "progress_wnd", None) and \
		   self.progress_wnd is getattr(self, "terminal", None):
			self.terminal.stop_timer()
			self.terminal.Hide()
		if self.finished is True:
			return
		if getattr(self, "progress_dlg", None):
			self.progress_wnd = self.progress_dlg
			self.progress_wnd.MakeModal(True)
			# UGLY HACK: This 'safe_print' call fixes a GTK assertion and 
			# segfault under Arch Linux when setting the window title
			safe_print("")
			self.progress_wnd.SetTitle(progress_title)
			self.progress_wnd.Update(0, progress_msg)
			self.progress_wnd.Resume()
			if not self.progress_wnd.IsShownOnScreen():
				self.progress_wnd.Show()
			self.progress_wnd.start_timer()
		else:
			# Set maximum to 101 to prevent the 'cancel' changing to 'close'
			# when 100 is reached
			self.progress_dlg = ProgressDialog(progress_title, progress_msg, 
											   maximum=101, 
											   parent=parent, 
											   handler=self.progress_handler,
											   keyhandler=self.terminal_key_handler)
			self.progress_wnd = self.progress_dlg
		self.progress_wnd.original_msg = progress_msg
	
	def quit_terminate_cmd(self):
		if debug:
			safe_print('[D] safe_quit')
		##if getattr(self, "subprocess", None) and \
		   ##not getattr(self, "subprocess_abort", False) and \
		if getattr(self, "subprocess", None) and \
		   (hasattr(self.subprocess, "poll") and 
			self.subprocess.poll() is None) or \
		   (hasattr(self.subprocess, "isalive") and 
			self.subprocess.isalive()):
			if debug or test:
				safe_print('User requested abort')
			##self.subprocess_abort = True
			##self.thread_abort = True
			try:
				if self.measure and hasattr(self.subprocess, "send"):
					try:
						if debug or test:
							safe_print('Sending ESC (1)')
						self.subprocess.send("\x1b")
						ts = time()
						while getattr(self, "subprocess", None) and \
						   self.subprocess.isalive():
							if time() > ts + 9 or \
							   " or Q to " in self.lastmsg.read():
								break
							sleep(1)
						if getattr(self, "subprocess", None) and \
						   self.subprocess.isalive():
							if debug or test:
								safe_print('Sending ESC (2)')
							self.subprocess.send("\x1b")
							sleep(.5)
					except Exception, exception:
						if debug:
							safe_print(traceback.format_exc())
				if getattr(self, "subprocess", None) and \
				   (hasattr(self.subprocess, "poll") and 
					self.subprocess.poll() is None) or \
				   (hasattr(self.subprocess, "isalive") and 
					self.subprocess.isalive()):
					if debug or test:
						safe_print('Trying to terminate subprocess...')
					self.subprocess.terminate()
					ts = time()
					while getattr(self, "subprocess", None) and \
					   hasattr(self.subprocess, "isalive") and \
					   self.subprocess.isalive():
						if time() > ts + 3:
							break
						sleep(.25)
					if getattr(self, "subprocess", None) and \
					   hasattr(self.subprocess, "isalive") and \
					   self.subprocess.isalive():
						if debug or test:
							safe_print('Trying to terminate subprocess forcefully...')
						self.subprocess.terminate(force=True)
			except Exception, exception:
				if debug:
					safe_print(traceback.format_exc())
			if debug:
				safe_print('[D] end try')
		elif debug:
			safe_print('[D] subprocess: %r' % getattr(self, "subprocess", None))
			safe_print('[D] subprocess_abort: %r' % getattr(self, "subprocess_abort", 
													 False))
			if getattr(self, "subprocess", None):
				safe_print('[D] subprocess has poll: %r' % hasattr(self.subprocess, 
															"poll"))
				if hasattr(self.subprocess, "poll"):
					safe_print('[D] subprocess.poll(): %r' % self.subprocess.poll())
				safe_print('[D] subprocess has isalive: %r' % hasattr(self.subprocess, 
															   "isalive"))
				if hasattr(self.subprocess, "isalive"):
					safe_print('[D] subprocess.isalive(): %r' % self.subprocess.isalive())
	
	def safe_send(self, bytes, retry=3):
		for i in xrange(0, retry):
			sleep(.25)
			try:
				self.subprocess.send(bytes)
			except:
				if i == retry - 2:
					return False
			else:
				return True

	def spyder2_firmware_exists(self):
		if self.argyll_version < [1, 2, 0]:
			spyd2en = get_argyll_util("spyd2en")
			if not spyd2en:
				return False
			pldpaths = [os.path.join(os.path.dirname(spyd2en), "spyd2PLD.bin")]
		else:
			pldpaths = [os.path.join(dir_, "color", "spyd2PLD.bin") 
						for dir_ in [defaultpaths.appdata, 
									 defaultpaths.home] + 
									defaultpaths.commonappdata]
		for pldpath in pldpaths:
			if os.path.isfile(pldpath):
				return True
		return False

	def spyder4_cal_exists(self):
		if self.argyll_version < [1, 3, 6]:
			# We couldn't use it even if it exists
			return False
		paths = [os.path.join(dir_, "color", "spyd4cal.bin") 
				 for dir_ in [defaultpaths.appdata, 
							  defaultpaths.home] + defaultpaths.commonappdata]
		for path in paths:
			if os.path.isfile(path):
				return True
		return False

	def start(self, consumer, producer, cargs=(), ckwargs=None, wargs=(), 
			  wkwargs=None, progress_title=appname, progress_msg="", 
			  parent=None, progress_start=100, resume=False, 
			  continue_next=False, stop_timers=True):
		"""
		Start a worker process.
		
		Also show a progress dialog while the process is running.
		
		consumer         consumer function.
		producer         producer function.
		cargs            consumer arguments.
		ckwargs          consumer keyword arguments.
		wargs            producer arguments.
		wkwargs          producer keyword arguments.
		progress_title   progress dialog title. Defaults to '%s'.
		progress_msg     progress dialog message. Defaults to ''.
		progress_start   show progress dialog after delay (ms).
		resume           resume previous progress dialog (elapsed time etc).
		continue_next    do not hide progress dialog after producer finishes.
		
		""" % appname
		if ckwargs is None:
			ckwargs = {}
		if wkwargs is None:
			wkwargs = {}
		while self.is_working():
			sleep(.25) # wait until previous worker thread finishes
		if hasattr(self.owner, "stop_timers") and stop_timers:
			self.owner.stop_timers()
		if not parent:
			parent = self.owner
		if progress_start < 100:
			progress_start = 100
		self.resume = resume
		self.instrument_calibration_started = False
		self.instrument_calibration_complete = False
		if self.interactive or test:
			self.progress_start_timer = wx.Timer()
			if getattr(self, "progress_wnd", None) and \
			   self.progress_wnd is getattr(self, "progress_dlg", None):
				self.progress_dlg.Destroy()
				self.progress_dlg = None
			if progress_msg and progress_title == appname:
				progress_title = progress_msg
			if getattr(self, "terminal", None):
				self.progress_wnd = self.terminal
				if not resume:
					if isinstance(self.progress_wnd, SimpleTerminal):
						self.progress_wnd.console.SetValue("")
					elif isinstance(self.progress_wnd, DisplayAdjustmentFrame):
						self.progress_wnd.reset()
				self.progress_wnd.stop_timer()
				self.progress_wnd.Resume()
				self.progress_wnd.start_timer()
				# UGLY HACK: This 'safe_print' call fixes a GTK assertion and 
				# segfault under Arch Linux when setting the window title
				safe_print("")
				if isinstance(self.progress_wnd, SimpleTerminal):
					self.progress_wnd.SetTitle(progress_title)
				self.progress_wnd.Show()
				if resume and isinstance(self.progress_wnd, SimpleTerminal):
					self.progress_wnd.console.ScrollLines(
						self.progress_wnd.console.GetNumberOfLines())
			else:
				if test:
					self.terminal = SimpleTerminal(parent, title=progress_title,
												   handler=self.progress_handler,
												   keyhandler=self.terminal_key_handler)
				else:
					self.terminal = DisplayAdjustmentFrame(parent,
														   handler=self.progress_handler,
														   keyhandler=self.terminal_key_handler)
				self.terminal.worker = self
				self.progress_wnd = self.terminal
		else:
			if not progress_msg:
				progress_msg = lang.getstr("please_wait")
			# Show the progress dialog after a delay
			self.progress_start_timer = wx.CallLater(progress_start, 
													 self.progress_dlg_start, 
													 progress_title, 
													 progress_msg, parent,
													 resume)
		self.activated = False
		self.finished = False
		self.subprocess_abort = False
		self.thread_abort = False
		self.thread = delayedresult.startWorker(self.generic_consumer, 
												producer, [consumer, 
														   continue_next] + 
												list(cargs), ckwargs, wargs, 
												wkwargs)
		return True
	
	def swap_progress_wnds(self):
		parent = self.terminal.GetParent()
		if isinstance(self.terminal, DisplayAdjustmentFrame):
			title = lang.getstr("calibration")
		else:
			title = self.terminal.GetTitle()
		self.progress_dlg_start(title, "", parent, self.resume)
	
	def terminal_key_handler(self, event):
		keycode = None
		if event.GetEventType() in (wx.EVT_CHAR_HOOK.typeId,
									wx.EVT_KEY_DOWN.typeId):
			keycode = event.GetKeyCode()
		elif event.GetEventType() == wx.EVT_MENU.typeId:
			keycode = self.progress_wnd.id_to_keycode.get(event.GetId())
		if keycode is not None and getattr(self, "subprocess", None) and \
			hasattr(self.subprocess, "send"):
			keycode = keycodes.get(keycode, keycode)
			##if keycode == ord("7") and \
			   ##self.progress_wnd is getattr(self, "terminal", None) and \
			   ##"7) Continue on to calibration" in self.recent.read():
				### calibration
				##wx.CallAfter(self.swap_progress_wnds)
			##el
			if keycode in (ord("\x1b"), ord("8"), ord("Q"), ord("q")):
				# exit
				self.abort_subprocess()
				return
			try:
				self.subprocess.send(chr(keycode))
			except:
				pass
	
	def calculate_gamut(self, profile_path):
		"""
		Calculate gamut, volume, and coverage % against sRGB and Adobe RGB.
		
		Return gamut volume (int, scaled to sRGB = 1.0) and
		coverage (dict) as tuple.
		
		"""
		outname = os.path.splitext(profile_path)[0]
		gamut_volume = None
		gamut_coverage = {}
		# Create profile gamut and vrml
		if (sys.platform == "win32" and
			re.search("[^\x20-\x7e]", os.path.basename(profile_path))):
			# Avoid problems with encoding
			profile_path = win32api.GetShortPathName(profile_path)
		result = self.exec_cmd(get_argyll_util("iccgamut"),
							   ["-v", "-w", "-ir", profile_path],
							   capture_output=True,
							   skip_scripts=True)
		if not isinstance(result, Exception) and result:
			# iccgamut output looks like this:
			# Header:
			#  <...>
			#
			# Total volume of gamut is xxxxxx.xxxxxx cubic colorspace units
			for line in self.output:
				match = re.search("(\d+(?:\.\d+)?)\s+cubic\s+colorspace\s+"
								  "units", line)
				if match:
					gamut_volume = float(match.groups()[0]) / ICCP.GAMUT_VOLUME_SRGB
					break
		name = os.path.splitext(profile_path)[0]
		gamfilename = name + ".gam"
		wrlfilename = name + ".wrl"
		tmpfilenames = [gamfilename, wrlfilename]
		for key, src in (("srgb", "sRGB"), ("adobe-rgb", "ClayRGB1998")):
			if not isinstance(result, Exception) and result:
				# Create gamut view and intersection
				src_path = get_data_path("ref/%s.gam" % src)
				if not src_path:
					continue
				outfilename = outname + (" vs %s.wrl" % src)
				tmpfilenames.append(outfilename)
				result = self.exec_cmd(get_argyll_util("viewgam"),
									   ["-cw", "-t.75", "-s", src_path, "-cn",
										"-t.25", "-s", gamfilename, "-i",
										outfilename],
									   capture_output=True,
									   skip_scripts=True)
				if not isinstance(result, Exception) and result:
					# viewgam output looks like this:
					# Intersecting volume = xxx.x cubic units
					# 'path/to/1.gam' volume = xxx.x cubic units, intersect = xx.xx%
					# 'path/to/2.gam' volume = xxx.x cubic units, intersect = xx.xx%
					for line in self.output:
						match = re.search("[\\\/]%s.gam'\s+volume\s*=\s*"
										  "\d+(?:\.\d+)?\s+cubic\s+units,?"
										  "\s+intersect\s*=\s*"
										  "(\d+(?:\.\d+)?)" %
										  re.escape(src), line)
						if match:
							gamut_coverage[key] = float(match.groups()[0]) / 100.0
							break
		if not isinstance(result, Exception) and result:
			# Compress gam and wrl files using gzip
			for tmpfilename in tmpfilenames:
				try:
					with open(tmpfilename, "rb") as infile:
						data = infile.read()
					if (tmpfilename == gamfilename and
						tmpfilename != outname + ".gam"):
						# Use the original file name
						filename = outname + ".gam"
					elif (tmpfilename == wrlfilename and
						  tmpfilename != outname + ".wrl"):
						# Use the original file name
						filename = outname + ".wrl"
					else:
						filename = tmpfilename
					if filename.endswith(".wrl"):
						outfilename = filename[:-4] + ".wrz"
					else:
						outfilename = filename + ".gz"
					with GzipFileProper(filename + ".gz", "wb") as gz:
						# Always use original filename with '.gz' extension,
						# that way the filename in the header will be correct
						gz.write(data)
					if outfilename != filename + ".gz":
						# Rename the file afterwards if outfilename is different
						os.rename(filename + ".gz", outfilename)
					# Remove uncompressed file
					os.remove(tmpfilename)
				except Exception, exception:
					safe_print(safe_unicode(exception))
		elif result:
			# Exception
			safe_print(safe_unicode(result))
		return gamut_volume, gamut_coverage
	
	def chart_lookup(self, cgats, profile, as_ti3=False, 
					 check_missing_fields=False, absolute=False):
		if profile.colorSpace == "RGB":
			labels = ('RGB_R', 'RGB_G', 'RGB_B')
		else:
			labels = ('CMYK_C', 'CMYK_M', 'CMYK_Y', 'CMYK_K')
		ti1 = None
		ti3_ref = None
		gray = None
		scale = 1.0
		try:
			if not isinstance(cgats, CGATS.CGATS):
				cgats = CGATS.CGATS(cgats, True)
			else:
				# Always make a copy and do not alter a passed in CGATS instance!
				cgats = CGATS.CGATS(str(cgats))
			if 0 in cgats:
				# only look at the first section
				cgats[0].filename = cgats.filename
				cgats = cgats[0]
			primaries = cgats.queryi(labels)
			if primaries and not as_ti3:
				for i in primaries:
					for label in labels:
						if primaries[i][label] > 100:
							scale = 2.55
							break
				if scale > 1.0:
					for i in primaries:
						for label in labels:
							primaries[i][label] = primaries[i][label] / scale
				cgats.type = 'CTI1'
				cgats.COLOR_REP = profile.colorSpace
				ti1, ti3_ref, gray = self.ti1_lookup_to_ti3(cgats, profile, 
															"l", absolute)
			else:
				if not primaries and check_missing_fields:
					raise ValueError(lang.getstr("error.testchart.missing_fields", 
												 (cgats.filename, ", ".join(labels))))
				ti1, ti3_ref = self.ti3_lookup_to_ti1(cgats, profile)
		except Exception, exception:
			InfoDialog(self.owner, msg=safe_unicode(exception), 
					   ok=lang.getstr("ok"), bitmap=geticon(32, "dialog-error"))
		return ti1, ti3_ref, gray
	
	def ti1_lookup_to_ti3(self, ti1, profile, pcs=None, absolute=False):
		"""
		Read TI1 (filename or CGATS instance), lookup device->pcs values 
		colorimetrically through profile using Argyll's xicclu 
		utility and return TI3 (CGATS instance)
		
		"""
		
		# ti1
		if isinstance(ti1, basestring):
			ti1 = CGATS.CGATS(ti1)
		if not isinstance(ti1, CGATS.CGATS):
			raise TypeError('Wrong type for ti1, needs to be CGATS.CGATS '
							'instance')
		
		# profile
		if isinstance(profile, basestring):
			profile = ICCP.ICCProfile(profile)
		if not isinstance(profile, ICCP.ICCProfile):
			raise TypeError('Wrong type for profile, needs to be '
							'ICCP.ICCProfile instance')
		
		# determine pcs for lookup
		if not pcs:
			color_rep = profile.connectionColorSpace.upper()
			if color_rep == 'LAB':
				pcs = 'l'
			elif color_rep == 'XYZ':
				pcs = 'x'
			else:
				raise ValueError('Unknown CIE color representation ' + color_rep)
		
		# get profile color space
		colorspace = profile.colorSpace
		
		# required fields for ti1
		if colorspace == "CMYK":
			required = ("CMYK_C", "CMYK_M", "CMYK_Y", "CMYK_K")
		else:
			required = ("RGB_R", "RGB_G", "RGB_B")
		ti1_filename = ti1.filename
		try:
			ti1 = verify_cgats(ti1, required, True)
		except CGATS.CGATSInvalidError:
			raise ValueError(lang.getstr("error.testchart.invalid", 
										 ti1_filename))
		except CGATS.CGATSKeyError:
			raise ValueError(lang.getstr("error.testchart.missing_fields", 
										 (ti1_filename, ", ".join(required))))
		
		# read device values from ti1
		data = ti1.queryv1("DATA")
		if not data:
			raise ValueError(lang.getstr("error.testchart.invalid", 
										 ti1_filename))
		device_data = data.queryv(required)
		if not device_data:
			raise ValueError(lang.getstr("error.testchart.missing_fields", 
										 (ti1_filename, ", ".join(required))))
		
		if colorspace == "RGB":
			# make sure the first four patches are white so the whitepoint can be
			# averaged
			white_rgb = {'RGB_R': 100, 'RGB_G': 100, 'RGB_B': 100}
			white = dict(white_rgb)
			wp = ti1.queryv1("APPROX_WHITE_POINT")
			if wp:
				wp = [float(v) for v in wp.split()]
				wp = [CGATS.rpad((v / wp[1]) * 100.0, data.vmaxlen) for v in wp]
			else:
				wp = colormath.get_standard_illuminant("D65", scale=100)
			for label in data.parent.DATA_FORMAT.values():
				if not label in white:
					if label.upper() == 'LAB_L':
						value = 100
					elif label.upper() in ('LAB_A', 'LAB_B'):
						value = 0
					elif label.upper() == 'XYZ_X':
						value = wp[0]
					elif label.upper() == 'XYZ_Y':
						value = 100
					elif label.upper() == 'XYZ_Z':
						value = wp[2]
					else:
						value = '0'
					white.update({label: value})
			white_added_count = 0
			while len(data.queryi(white_rgb)) < 4:  # add white patches
				data.insert(0, white)
				white_added_count += 1
			safe_print("Added %i white patch(es)" % white_added_count)
		
		idata = []
		for primaries in device_data.values():
			idata.append(' '.join(str(n) for n in primaries.values()))
		##safe_print('\n'.join(idata))

		# lookup device->cie values through profile using xicclu
		xicclu = get_argyll_util("xicclu").encode(fs_enc)
		cwd = self.create_tempdir()
		if isinstance(cwd, Exception):
			raise cwd
		profile.write(os.path.join(cwd, "temp.icc"))
		if sys.platform == "win32":
			startupinfo = sp.STARTUPINFO()
			startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = sp.SW_HIDE
		else:
			startupinfo = None
		p = sp.Popen([xicclu, '-ff', '-i' + ('a' if absolute else 'r'), '-p' + pcs, '-s100', "temp.icc"], 
					 stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.STDOUT, 
					 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
		odata = p.communicate('\n'.join(idata))[0].splitlines()
		if p.wait() != 0:
			# error
			raise IOError(''.join(odata))
		##safe_print('\n'.join(odata))
		
		gray = []
		igray = []
		igray_idx = []
		if colorspace == "RGB":
			# treat r=g=b specially: set expected a=b=0
			for i, line in enumerate(odata):
				line = line.strip().split('->')
				line = ''.join(line).split()
				if line[-1] == '(clip)':
					line.pop()
				r, g, b = [float(n) for n in line[:3]]
				if r == g == b < 100:
					# if grayscale and not white
					cie = [float(n) for n in line[5:-1]]
					if pcs == 'x':
						# Need to scale XYZ coming from xicclu
						# Lab is already scaled
						cie = colormath.XYZ2Lab(*[n * 100.0 for n in cie])
					cie = (cie[0], 0, 0)  # set a=b=0
					igray.append("%s %s %s" % cie)
					igray_idx.append(i)
					if pcs == 'x':
						cie = colormath.Lab2XYZ(*cie)
						luminance = cie[1]
					else:
						luminance = colormath.Lab2XYZ(*cie)[1]
					if luminance * 100.0 >= 1:
						# only add if luminance is greater or equal 1% because 
						# dark tones fluctuate too much
						gray.append((r, g, b))
					if False:  # NEVER?
						# set cie in odata to a=b=0
						line[5:-1] = [str(n) for n in cie]
						odata[i] = ' -> '.join([' '.join(line[:4]), line[4], 
												' '.join(line[5:])])
			
		if igray and False:  # NEVER?
			# lookup cie->device values for grays through profile using xicclu
			gray = []
			xicclu = get_argyll_util("xicclu").encode(fs_enc)
			cwd = self.create_tempdir()
			if isinstance(cwd, Exception):
				raise cwd
			profile.write(os.path.join(cwd, "temp.icc"))
			if sys.platform == "win32":
				startupinfo = sp.STARTUPINFO()
				startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
				startupinfo.wShowWindow = sp.SW_HIDE
			else:
				startupinfo = None
			p = sp.Popen([xicclu, '-fb', '-ir', '-pl', '-s100', "temp.icc"], 
						 stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.STDOUT, 
						 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
			ogray = p.communicate('\n'.join(igray))[0].splitlines()
			if p.wait() != 0:
				# error
				raise IOError(''.join(odata))
			for i, line in enumerate(ogray):
				line = line.strip().split('->')
				line = ''.join(line).split()
				if line[-1] == '(clip)':
					line.pop()
				cie = [float(n) for n in line[:3]]
				rgb = [float(n) for n in line[5:-1]]
				if colormath.Lab2XYZ(cie[0], 0, 0)[1] * 100.0 >= 1:
					# only add if luminance is greater or equal 1% because 
					# dark tones fluctuate too much
					gray.append(rgb)
				# update values in ti1 and data for ti3
				for n, channel in enumerate(("R", "G", "B")):
					data[igray_idx[i] + 
						 white_added_count]["RGB_" + channel] = rgb[n]
				oline = odata[igray_idx[i]].strip().split('->', 1)
				odata[igray_idx[i]] = ' [RGB] ->'.join([' '.join(line[5:-1])] + 
													   oline[1:])
		
		self.wrapup(False)

		# write output ti3
		ofile = StringIO()
		ofile.write('CTI3\n')
		ofile.write('\n')
		ofile.write('DESCRIPTOR "Argyll Calibration Target chart information 3"\n')
		ofile.write('KEYWORD "DEVICE_CLASS"\n')
		ofile.write('DEVICE_CLASS "' + ('DISPLAY' if colorspace == 'RGB' else 
										'OUTPUT') + '"\n')
		include_sample_name = False
		i = 0
		offset = 0 if colorspace == "RGB" else 1
		for line in odata:
			line = line.strip().split('->')
			line = ''.join(line).split()
			if line[-1] == '(clip)':
				line.pop()
			if i == 0:
				icolor = line[3 + offset].strip('[]')
				if icolor == 'RGB':
					olabel = 'RGB_R RGB_G RGB_B'
				elif icolor == 'CMYK':
					olabel = 'CMYK_C CMYK_M CMYK_Y CMYK_K'
				else:
					raise ValueError('Unknown color representation ' + icolor)
				ocolor = line[-1].strip('[]').upper()
				if ocolor == 'LAB':
					ilabel = 'LAB_L LAB_A LAB_B'
				elif ocolor == 'XYZ':
					ilabel = 'XYZ_X XYZ_Y XYZ_Z'
				else:
					raise ValueError('Unknown CIE color representation ' + ocolor)
				ofile.write('KEYWORD "COLOR_REP"\n')
				ofile.write('COLOR_REP "' + icolor + '_' + ocolor + '"\n')
				
				ofile.write('\n')
				ofile.write('NUMBER_OF_FIELDS ')
				if include_sample_name:
					ofile.write(str(2 + len(icolor) + len(ocolor)) + '\n')
				else:
					ofile.write(str(1 + len(icolor) + len(ocolor)) + '\n')
				ofile.write('BEGIN_DATA_FORMAT\n')
				ofile.write('SAMPLE_ID ')
				if include_sample_name:
					ofile.write('SAMPLE_NAME ' + olabel + ' ' + ilabel + '\n')
				else:
					ofile.write(olabel + ' ' + ilabel + '\n')
				ofile.write('END_DATA_FORMAT\n')
				ofile.write('\n')
				ofile.write('NUMBER_OF_SETS ' + str(len(odata)) + '\n')
				ofile.write('BEGIN_DATA\n')
			i += 1
			cie = [float(n) for n in line[5 + offset:-1]]
			if pcs == 'x':
				# Need to scale XYZ coming from xicclu, Lab is already scaled
				cie = [round(n * 100.0, 5 - len(str(int(abs(n * 100.0))))) 
					   for n in cie]
			cie = [str(n) for n in cie]
			if include_sample_name:
				ofile.write(str(i) + ' ' + data[i - 1][1].strip('"') + ' ' + 
							' '.join(line[:3 + offset]) + ' ' + ' '.join(cie) + '\n')
			else:
				ofile.write(str(i) + ' ' + ' '.join(line[:3 + offset]) + ' ' + 
							' '.join(cie) + '\n')
		ofile.write('END_DATA\n')
		ofile.seek(0)
		return ti1, CGATS.CGATS(ofile)[0], map(list, gray)
	
	def ti3_lookup_to_ti1(self, ti3, profile):
		"""
		Read TI3 (filename or CGATS instance), lookup cie->device values 
		colorimetrically through profile using Argyll's xicclu 
		utility and return TI1 and compatible TI3 (CGATS instances)
		
		"""
		
		# ti3
		copy = True
		if isinstance(ti3, basestring):
			copy = False
			ti3 = CGATS.CGATS(ti3)
		if not isinstance(ti3, CGATS.CGATS):
			raise TypeError('Wrong type for ti3, needs to be CGATS.CGATS '
							'instance')
		ti3_filename = ti3.filename
		if copy:
			# Make a copy and do not alter a passed in CGATS instance!
			ti3 = CGATS.CGATS(str(ti3))
		
		try:
			ti3v = verify_cgats(ti3, ("LAB_L", "LAB_A", "LAB_B"), True)
		except CGATS.CGATSInvalidError, exception:
			raise ValueError(lang.getstr("error.testchart.invalid", 
										 ti3_filename) + "\n" +
										 lang.getstr(safe_str(exception)))
		except CGATS.CGATSKeyError:
			try:
				ti3v = verify_cgats(ti3, ("XYZ_X", "XYZ_Y", "XYZ_Z"), True)
			except CGATS.CGATSKeyError:
				raise ValueError(lang.getstr("error.testchart.missing_fields", 
											 (ti3_filename, 
											  "XYZ_X, XYZ_Y, XYZ_Z " +
											  lang.getstr("or") + 
											  " LAB_L, LAB_A, LAB_B")))
			else:
				color_rep = 'XYZ'
		else:
			color_rep = 'LAB'
		
		# profile
		if isinstance(profile, basestring):
			profile = ICCP.ICCProfile(profile)
		if not isinstance(profile, ICCP.ICCProfile):
			raise TypeError('Wrong type for profile, needs to be '
							'ICCP.ICCProfile instance')
			
		# determine pcs for lookup
		if color_rep == 'LAB':
			pcs = 'l'
			required = ("LAB_L", "LAB_A", "LAB_B")
		elif color_rep == 'XYZ':
			pcs = 'x'
			required = ("XYZ_X", "XYZ_Y", "XYZ_Z")
		else:
			raise ValueError('Unknown CIE color representation ' + color_rep)

		# get profile color space
		colorspace = profile.colorSpace

		# read cie values from ti3
		data = ti3v.queryv1("DATA")
		if not data:
			raise ValueError(lang.getstr("error.testchart.invalid", 
										 ti3_filename))
		cie_data = data.queryv(required)
		if not cie_data:
			raise ValueError(lang.getstr("error.testchart.missing_fields", 
										 (ti3_filename, ", ".join(required))))
		idata = []
		if colorspace == "RGB":
			# make sure the first four patches are white so the whitepoint can be
			# averaged
			wp = [n * 100.0 for n in profile.tags.wtpt.values()]
			if color_rep == 'LAB':
				wp = colormath.XYZ2Lab(*wp)
				wp = OrderedDict((('L', wp[0]), ('a', wp[1]), ('b', wp[2])))
			else:
				wp = OrderedDict((('X', wp[0]), ('Y', wp[1]), ('Z', wp[2])))
			wp = [wp] * 4
			safe_print("Added 4 white patches")
		else:
			wp = []
		
		for cie in wp + cie_data.values():
			cie = cie.values()
			if color_rep == 'XYZ':
				# assume scale 0...100 in ti3, we need to convert to 0...1
				cie = [n / 100.0 for n in cie]
			idata.append(' '.join(str(n) for n in cie))
		##safe_print('\n'.join(idata))

		# lookup cie->device values through profile.icc using xicclu
		xicclu = get_argyll_util("xicclu").encode(fs_enc)
		cwd = self.create_tempdir()
		if isinstance(cwd, Exception):
			raise cwd
		profile.write(os.path.join(cwd, "temp.icc"))
		if sys.platform == "win32":
			startupinfo = sp.STARTUPINFO()
			startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = sp.SW_HIDE
		else:
			startupinfo = None
		p = sp.Popen([xicclu, '-fb', '-ir', '-p' + pcs, '-s100', "temp.icc"], 
					 stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.STDOUT, 
					 cwd=cwd.encode(fs_enc), startupinfo=startupinfo)
		odata = p.communicate('\n'.join(idata))[0].splitlines()
		if p.wait() != 0:
			# error
			raise IOError(''.join(odata))
		##safe_print('\n'.join(odata))
		self.wrapup(False)
		
		# write output ti1/ti3
		ti1out = StringIO()
		ti1out.write('CTI1\n')
		ti1out.write('\n')
		ti1out.write('DESCRIPTOR "Argyll Calibration Target chart information 1"\n')
		include_sample_name = False
		i = 0
		for line in odata:
			line = line.strip().split('->')
			line = ''.join(line).split()
			if line[-1] == '(clip)':
				line.pop()
			if i == 0:
				icolor = line[3].strip('[]').upper()
				if icolor == 'LAB':
					ilabel = 'LAB_L LAB_A LAB_B'
				elif icolor == 'XYZ':
					ilabel = 'XYZ_X XYZ_Y XYZ_Z'
				else:
					raise ValueError('Unknown CIE color representation ' + icolor)
				ocolor = line[-1].strip('[]')
				if ocolor == 'RGB':
					olabel = 'RGB_R RGB_G RGB_B'
				elif ocolor == 'CMYK':
					olabel = 'CMYK_C CMYK_M CMYK_Y CMYK_K'
				else:
					raise ValueError('Unknown color representation ' + ocolor)
				olabels = olabel.split()
				# add device fields to DATA_FORMAT if not yet present
				if not olabels[0] in ti3v.DATA_FORMAT.values() and \
				   not olabels[1] in ti3v.DATA_FORMAT.values() and \
				   not olabels[2] in ti3v.DATA_FORMAT.values() and \
				   (ocolor == 'RGB' or (ocolor == 'CMYK' and 
				    not olabels[3] in ti3v.DATA_FORMAT.values())):
					ti3v.DATA_FORMAT.add_data(olabels)
				# add required fields to DATA_FORMAT if not yet present
				if not required[0] in ti3v.DATA_FORMAT.values() and \
				   not required[1] in ti3v.DATA_FORMAT.values() and \
				   not required[2] in ti3v.DATA_FORMAT.values():
					ti3v.DATA_FORMAT.add_data(required)
				ti1out.write('KEYWORD "COLOR_REP"\n')
				ti1out.write('COLOR_REP "' + ocolor + '"\n')
				ti1out.write('\n')
				ti1out.write('NUMBER_OF_FIELDS ')
				if include_sample_name:
					ti1out.write(str(2 + len(icolor) + len(ocolor)) + '\n')
				else:
					ti1out.write(str(1 + len(icolor) + len(ocolor)) + '\n')
				ti1out.write('BEGIN_DATA_FORMAT\n')
				ti1out.write('SAMPLE_ID ')
				if include_sample_name:
					ti1out.write('SAMPLE_NAME ' + olabel + ' ' + ilabel + '\n')
				else:
					ti1out.write(olabel + ' ' + ilabel + '\n')
				ti1out.write('END_DATA_FORMAT\n')
				ti1out.write('\n')
				ti1out.write('NUMBER_OF_SETS ' + str(len(odata)) + '\n')
				ti1out.write('BEGIN_DATA\n')
			if i < len(wp):
				if ocolor == 'RGB':
					device = '100.00 100.00 100.00'.split()
				else:
					device = '0 0 0 0'.split()
			else:
				device = line[5:-1]
			cie = (wp + cie_data.values())[i].values()
			cie = [str(n) for n in cie]
			if include_sample_name:
				ti1out.write(str(i + 1) + ' ' + data[i][1].strip('"') + ' ' + 
							 ' '.join(device) + ' ' + ' '.join(cie) + '\n')
			else:
				ti1out.write(str(i + 1) + ' ' + ' '.join(device) + ' ' + 
							 ' '.join(cie) + '\n')
			if i > len(wp) - 1:  # don't include whitepoint patches in ti3
				# set device values in ti3
				for n, v in enumerate(olabels):
					ti3v.DATA[i - len(wp)][v] = float(line[5 + n])
				# set PCS values in ti3
				for n, v in enumerate(cie):
					ti3v.DATA[i - len(wp)][required[n]] = float(v)
			i += 1
		ti1out.write('END_DATA\n')
		ti1out.seek(0)
		return CGATS.CGATS(ti1out), ti3v


	def wrapup(self, copy=True, remove=True, dst_path=None, ext_filter=None):
		"""
		Wrap up - copy and/or clean temporary file(s).
		
		"""
		if debug: safe_print("[D] wrapup(copy=%s, remove=%s)" % (copy, remove))
		if not self.tempdir or not os.path.isdir(self.tempdir):
			return # nothing to do
		if copy:
			if not ext_filter:
				ext_filter = [".app", ".cal", ".ccmx", ".ccss", ".cmd", 
							  ".command", ".gam", ".gz", ".icc", ".icm",
							  ".sh", ".ti1", ".ti3", ".wrl", ".wrz"]
			if dst_path is None:
				dst_path = os.path.join(getcfg("profile.save_path"), 
										getcfg("profile.name.expanded"), 
										getcfg("profile.name.expanded") + 
										".ext")
			result = check_create_dir(os.path.dirname(dst_path))
			if isinstance(result, Exception):
				return result
			if result:
				try:
					src_listdir = os.listdir(self.tempdir)
				except Exception, exception:
					safe_print(u"Error - directory '%s' listing failed: %s" % 
							   tuple(safe_unicode(s) for s in (self.tempdir, 
															   exception)))
				else:
					for basename in src_listdir:
						name, ext = os.path.splitext(basename)
						if ext_filter is None or ext.lower() in ext_filter:
							src = os.path.join(self.tempdir, basename)
							dst = os.path.join(os.path.dirname(dst_path), basename)
							if os.path.exists(dst):
								if os.path.isdir(dst):
									if verbose >= 2:
										safe_print(appname + 
												   ": Removing existing "
												   "destination directory tree", 
												   dst)
									try:
										shutil.rmtree(dst, True)
									except Exception, exception:
										safe_print(u"Warning - directory '%s' "
												   u"could not be removed: %s" % 
												   tuple(safe_unicode(s) 
														 for s in (dst, 
																   exception)))
								else:
									if verbose >= 2:
										safe_print(appname + 
												   ": Removing existing "
												   "destination file", dst)
									try:
										os.remove(dst)
									except Exception, exception:
										safe_print(u"Warning - file '%s' could "
												   u"not be removed: %s" % 
												   tuple(safe_unicode(s) 
														 for s in (dst, 
																   exception)))
							if remove:
								if verbose >= 2:
									safe_print(appname + ": Moving temporary "
											   "object %s to %s" % (src, dst))
								try:
									shutil.move(src, dst)
								except Exception, exception:
									safe_print(u"Warning - temporary object "
											   u"'%s' could not be moved to "
											   u"'%s': %s" % 
											   tuple(safe_unicode(s) for s in 
													 (src, dst, exception)))
							else:
								if os.path.isdir(src):
									if verbose >= 2:
										safe_print(appname + 
												   ": Copying temporary "
												   "directory tree %s to %s" % 
												   (src, dst))
									try:
										shutil.copytree(src, dst)
									except Exception, exception:
										safe_print(u"Warning - temporary "
												   u"directory '%s' could not "
												   u"be copied to '%s': %s" % 
												   tuple(safe_unicode(s) 
														 for s in 
														 (src, dst, exception)))
								else:
									if verbose >= 2:
										safe_print(appname + 
												   ": Copying temporary "
												   "file %s to %s" % (src, dst))
									try:
										shutil.copyfile(src, dst)
									except Exception, exception:
										safe_print(u"Warning - temporary file "
												   u"'%s' could not be copied "
												   u"to '%s': %s" % 
												   tuple(safe_unicode(s) 
														 for s in 
														 (src, dst, exception)))
		if remove:
			try:
				src_listdir = os.listdir(self.tempdir)
			except Exception, exception:
				safe_print(u"Error - directory '%s' listing failed: %s" % 
						   tuple(safe_unicode(s) for s in (self.tempdir, 
														   exception)))
			else:
				for basename in src_listdir:
					name, ext = os.path.splitext(basename)
					if ext_filter is None or ext.lower() not in ext_filter:
						src = os.path.join(self.tempdir, basename)
						isdir = os.path.isdir(src)
						if isdir:
							if verbose >= 2:
								safe_print(appname + ": Removing temporary "
										   "directory tree", src)
							try:
								shutil.rmtree(src, True)
							except Exception, exception:
								safe_print(u"Warning - temporary directory "
										   u"'%s' could not be removed: %s" % 
										   tuple(safe_unicode(s) for s in 
												 (src, exception)))
						else:
							if verbose >= 2:
								safe_print(appname + 
										   ": Removing temporary file", 
										   src)
							try:
								os.remove(src)
							except Exception, exception:
								safe_print(u"Warning - temporary directory "
										   u"'%s' could not be removed: %s" % 
										   tuple(safe_unicode(s) for s in 
												 (src, exception)))
			try:
				src_listdir = os.listdir(self.tempdir)
			except Exception, exception:
				safe_print(u"Error - directory '%s' listing failed: %s" % 
						   tuple(safe_unicode(s) for s in (self.tempdir, 
														   exception)))
			else:
				if not src_listdir:
					if verbose >= 2:
						safe_print(appname + 
								   ": Removing empty temporary directory", 
								   self.tempdir)
					try:
						shutil.rmtree(self.tempdir, True)
					except Exception, exception:
						safe_print(u"Warning - temporary directory '%s' could "
								   u"not be removed: %s" % 
								   tuple(safe_unicode(s) for s in 
										 (self.tempdir, exception)))
		return True
