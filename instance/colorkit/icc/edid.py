# -*- coding: utf-8 -*-

from hashlib import md5
import codecs
import math
import os
import string
import struct
import sys
if sys.platform == "win32":
	if sys.getwindowsversion() >= (6, ):
		# Use WMI for Vista/Win7
		import wmi
		wmi_connection = wmi.WMI(namespace="WMI")
	else:
		# Use registry as fallback for Win2k/XP/2003
		import _winreg
		wmi_connection = None
	import pywintypes
	import win32api
elif sys.platform != "darwin":
	try:
		import xrandr
	except ImportError:
		xrandr = None
else:
	import binascii
	import re
	import subprocess as sp

import config
from log import log, safe_print
from util_str import make_ascii_printable
if sys.platform == "win32":
	import util_win

HEADER = (0, 8)
MANUFACTURER_ID = (8, 10)
PRODUCT_ID = (10, 12)
SERIAL_32 = (12, 16)
WEEK_OF_MANUFACTURE = 16
YEAR_OF_MANUFACTURE = 17
EDID_VERSION = 18
EDID_REVISION = 19
MAX_H_SIZE_CM = 21
MAX_V_SIZE_CM = 22
GAMMA = 23
FEATURES = 24
LO_RG_XY = 25
LO_BW_XY = 26
HI_R_X = 27
HI_R_Y = 28
HI_G_X = 29
HI_G_Y = 30
HI_B_X = 31
HI_B_Y = 32
HI_W_X = 33
HI_W_Y = 34
BLOCKS = ((54, 72), (72, 90), (90, 108), (108, 126))
BLOCK_TYPE = 3
BLOCK_CONTENTS = (5, 18)
BLOCK_TYPE_SERIAL_ASCII = "\xff"
BLOCK_TYPE_ASCII = "\xfe"
BLOCK_TYPE_MONITOR_NAME = "\xfc"
BLOCK_TYPE_COLOR_POINT = "\xfb"
BLOCK_TYPE_COLOR_MANAGEMENT_DATA  = "\xf9"
EXTENSION_FLAG = 126
CHECKSUM = 127
BLOCK_DI_EXT = "\x40"
TRC = (81, 127)

pnpidcache = {}

def combine_hi_8lo(hi, lo):
	return hi << 8 | lo


def get_edid(display_no=0, display_name=None):
	""" Get and parse EDID. Return dict. 
	
	On Mac OS X, you need to specify a display name.
	On all other platforms, you need to specify a display number (zero-based).
	
	"""
	edid = None
	if sys.platform == "win32":
		# The ordering will work as long as Argyll continues using
		# EnumDisplayMonitors
		monitors = util_win.get_real_display_devices_info()
		moninfo = monitors[display_no]
		device = util_win.get_active_display_device(moninfo["Device"])
		if not device:
			return {}
		id = device.DeviceID.split("\\")[1]
		if wmi_connection:
			# Use WMI for Vista/Win7
			# http://msdn.microsoft.com/en-us/library/Aa392707
			try:
				msmonitors = wmi_connection.WmiMonitorDescriptorMethods()
			except Exception, exception:
				raise WMIError(exception)
			for msmonitor in msmonitors:
				if msmonitor.InstanceName.split("\\")[1] == id:
					try:
						edid = msmonitor.WmiGetMonitorRawEEdidV1Block(0)
					except:
						# No EDID entry
						pass
					else:
						edid = "".join(chr(i) for i in edid[0])
					break
		else:
			# Use registry as fallback for Win2k/XP/2003
			# http://msdn.microsoft.com/en-us/library/ff546173%28VS.85%29.aspx
			# "The Enum tree is reserved for use by operating system components, 
			#  and its layout is subject to change. (...) Drivers and Windows 
			#  applications must not access the Enum tree directly."
			# But do we care? Probably not, as older Windows' API isn't likely
			# gonna change.
			driver = "\\".join(device.DeviceID.split("\\")[-2:])
			subkey = "\\".join(["SYSTEM", "CurrentControlSet", "Enum", 
								"DISPLAY", id])
			try:
				key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, subkey)
			except WindowsError:
				# Registry error
				safe_print("Windows registry error: Key", 
						   "\\".join(["HKEY_LOCAL_MACHINE", subkey]), 
						   "does not exist.")
				return {}
			numsubkeys, numvalues, mtime = _winreg.QueryInfoKey(key)
			for i in range(numsubkeys):
				hkname = _winreg.EnumKey(key, i)
				hk = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, 
									 "\\".join([subkey, hkname]))
				try:
					test = _winreg.QueryValueEx(hk, "Driver")[0]
				except WindowsError:
					# No Driver entry
					continue
				if test == driver:
					# Found our display device
					try:
						devparms = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, 
										 "\\".join([subkey, hkname, 
													"Device Parameters"]))
					except WindowsError:
						# No Device Parameters (registry error?)
						safe_print("Windows registry error: Key", 
								   "\\".join(["HKEY_LOCAL_MACHINE", subkey, 
											  hkname, "Device Parameters"]), 
								   "does not exist.")
						continue
					try:
						edid = _winreg.QueryValueEx(devparms, "EDID")[0]
					except WindowsError:
						# No EDID entry
						pass
	elif sys.platform == "darwin":
		# Get EDID via ioreg
		p = sp.Popen(["ioreg", "-c", "IODisplay", "-S", "-w0"], stdout=sp.PIPE)
		stdout, stderr = p.communicate()
		if stdout:
			for edid in [binascii.unhexlify(edid_hex) for edid_hex in 
						 re.findall('"IODisplayEDID"\s*=\s*<([0-9A-Fa-f]*)>', 
									stdout)]:
				if edid and len(edid) >= 128:
					parsed_edid = parse_edid(edid)
					if parsed_edid.get("monitor_name",
									   parsed_edid.get("ascii")) == display_name:
						# On Mac OS X, you need to specify a display name 
						# because the order is unknown
						return parsed_edid
		return {}
	elif xrandr:
		# Check XrandR output properties
		edid = None
		for key in ("EDID", "EDID_DATA"):
			try:
				edid = xrandr.get_output_property(display_no, key, 
													   xrandr.XA_INTEGER)
			except ValueError:
				pass
			else:
				break
		if not edid:
			# Check X11 atoms
			for key in ("XFree86_DDC_EDID1_RAWDATA", 
						"XFree86_DDC_EDID2_RAWDATA"):
				if display_no > 0:
					key += "_%s" % display_no
				try:
					edid = xrandr.get_atom(key)
				except ValueError:
					pass
				else:
					break
		if edid:
			edid = "".join(chr(i) for i in edid)
	if edid and len(edid) >= 128:
		return parse_edid(edid)
	return {}


def parse_manufacturer_id(block):
	""" Parse the manufacturer id and return decoded string. 
	
	The range is always ASCII charcode 64 to 95.
	
	"""
	h = combine_hi_8lo(ord(block[0]), ord(block[1]))
	manufacturer_id = []
	for shift in (10, 5, 0):
		manufacturer_id.append(chr(((h >> shift) & 0x1f) + ord('A') - 1))
	return "".join(manufacturer_id).strip()


def get_manufacturer_name(manufacturer_id):
	""" Try and get a nice descriptive string for our manufacturer id.
	This uses pnp.ids which will be looked for in several places.
	If it can't find the file, it simply returns the manufacturer id.
	
	Examples:
	SAM -> Samsung Electric Company
	NEC -> NEC Corporation
	
	pnp.ids can be created from Excel data available from Microsoft:
	http://www.microsoft.com/whdc/system/pnppwr/pnp/pnpid.mspx
	
	"""
	if not pnpidcache:
		paths = ["/usr/share/hwdata/pnp.ids",  # hwdata, e.g. Red Hat
				 "/usr/share/misc/pnp.ids",  # pnputils, e.g. Debian
				 "/usr/share/libgnome-desktop/pnp.ids",  # fallback gnome-desktop
				 os.path.join(config.pydir, "pnp.ids")]  # fallback
		for path in paths:
			if os.path.isfile(path):
				try:
					pnp_ids = codecs.open(path, "r", "UTF-8", "replace")
				except IOError:
					pass
				else:
					try:
						for line in pnp_ids:
							try:
								# Strip leading/trailing whitespace
								# (non-breaking spaces too)
								id, name = line.strip(string.whitespace + 
													  u"\u00a0").split(None, 1)
							except ValueError:
								continue
							pnpidcache[id] = name
					except OSError:
						pass
					pnp_ids.close()
	return pnpidcache.get(manufacturer_id, manufacturer_id)


def edid_get_bit(value, bit):
	return (value & (1 << bit)) >> bit


def edid_get_bits(value, begin, end):
	mask = (1 << (end - begin + 1)) - 1
	return (value >> begin) & mask


def edid_decode_fraction(high, low):
	result = 0.0
	high = (high << 2) | low
	for i in xrange(0, 10):
		result += edid_get_bit(high, i) * math.pow(2, i - 10)
	return result


def parse_edid(edid):
	""" Parse raw EDID data (binary string) and return dict. """
	hash = md5(edid).hexdigest()
	header = edid[HEADER[0]:HEADER[1]]
	manufacturer_id = parse_manufacturer_id(edid[MANUFACTURER_ID[0]:MANUFACTURER_ID[1]])
	manufacturer = get_manufacturer_name(manufacturer_id)
	
	product_id = struct.unpack("<H", edid[PRODUCT_ID[0]:PRODUCT_ID[1]])[0]
	serial_32 = struct.unpack("<I", edid[SERIAL_32[0]:SERIAL_32[1]])[0]
	week_of_manufacture = ord(edid[WEEK_OF_MANUFACTURE])
	year_of_manufacture = ord(edid[YEAR_OF_MANUFACTURE]) + 1990
	edid_version = ord(edid[EDID_VERSION])
	edid_revision = ord(edid[EDID_REVISION])
	
	max_h_size_cm = ord(edid[MAX_H_SIZE_CM])
	max_v_size_cm = ord(edid[MAX_V_SIZE_CM])
	if edid[GAMMA] != "\xff":
		gamma = ord(edid[GAMMA]) / 100.0 + 1
	features = ord(edid[FEATURES])
	
	red_x = edid_decode_fraction(ord(edid[HI_R_X]), 
								 edid_get_bits(ord(edid[LO_RG_XY]), 6, 7))
	red_y = edid_decode_fraction(ord(edid[HI_R_Y]), 
								 edid_get_bits(ord(edid[LO_RG_XY]), 5, 4))
	
	green_x = edid_decode_fraction(ord(edid[HI_G_X]), 
								   edid_get_bits(ord(edid[LO_RG_XY]), 2, 3))
	green_y = edid_decode_fraction(ord(edid[HI_G_Y]), 
								   edid_get_bits(ord(edid[LO_RG_XY]), 0, 1))

	blue_x = edid_decode_fraction(ord(edid[HI_B_X]), 
								  edid_get_bits(ord(edid[LO_BW_XY]), 6, 7))
	blue_y = edid_decode_fraction(ord(edid[HI_B_Y]), 
								  edid_get_bits(ord(edid[LO_BW_XY]), 4, 5))

	white_x = edid_decode_fraction(ord(edid[HI_W_X]), 
								   edid_get_bits(ord(edid[LO_BW_XY]), 2, 3))
	white_y = edid_decode_fraction(ord(edid[HI_W_Y]), 
								   edid_get_bits(ord(edid[LO_BW_XY]), 0, 1))
	
	result = locals()
	
	text_types = {BLOCK_TYPE_SERIAL_ASCII: "serial_ascii",
				  BLOCK_TYPE_ASCII: "ascii",
				  BLOCK_TYPE_MONITOR_NAME: "monitor_name"}
	
	# Parse descriptor blocks
	for start, stop in BLOCKS:
		block = edid[start:stop]
		if block[:BLOCK_TYPE] != "\0\0\0":
			# Ignore pixel clock data
			continue
		text_type = text_types.get(block[BLOCK_TYPE])
		if text_type:
			# Strip all leading/trailing whitespace and NULL chars, then
			# replace all non-printable chars with NULL
			desc = make_ascii_printable(
				block[BLOCK_CONTENTS[0]:BLOCK_CONTENTS[1]].strip(
					"\0" + string.whitespace), subst="\0")
			# Filter out bogus strings
			if desc.count("\0") <= 4 < len(desc):
				# Replace any NULL chars with dashes to make a printable string
				# also replace whitespace with space
				result[text_type] = desc.translate(
					string.maketrans("\0" + string.whitespace, 
									 "-" + (" " * len(string.whitespace))))
		elif block[BLOCK_TYPE] == BLOCK_TYPE_COLOR_POINT:
			for i in (5, 10):
				# 2nd white point index in range 1...255
				# 3rd white point index in range 2...255
				# 0 = do not use
				if ord(block[i]) > i / 5:
					white_x = edid_decode_fraction(ord(edid[i + 2]), 
												   edid_get_bits(ord(edid[i + 1]), 
																 2, 3))
					result["white_x_" + str(ord(block[i]))] = white_x
					if not result.get("white_x"):
						result["white_x"] = white_x
					white_y = edid_decode_fraction(ord(edid[i + 3]), 
												   edid_get_bits(ord(edid[i + 1]), 
																 0, 1))
					result["white_y_" + str(ord(block[i]))] = white_y
					if not result.get("white_y"):
						result["white_y"] = white_y
					if block[i + 4] != "\xff":
						gamma = ord(block[i + 4]) / 100.0 + 1
						result["gamma_" + str(ord(block[i]))] = gamma
						if not result.get("gamma"):
							result["gamma"] = gamma
		elif block[BLOCK_TYPE] == BLOCK_TYPE_COLOR_MANAGEMENT_DATA:
			# TODO: Implement? How could it be used?
			result["color_management_data"] = block[BLOCK_CONTENTS[0]:BLOCK_CONTENTS[1]]
	
	result["ext_flag"] = ord(edid[EXTENSION_FLAG])
	result["checksum"] = ord(edid[CHECKSUM])
	result["checksum_valid"] = sum(ord(char) for char in edid) % 256 == 0
	
	if len(edid) > 128 and result["ext_flag"] > 0:
		# Parse extension blocks
		block = edid[128:]
		while block:
			if block[0] == BLOCK_DI_EXT:
				if block[TRC[0]] != "\0":
					# TODO: Implement
					pass
			block = block[128:]
	
	return result


class WMIError(Exception):
	pass
