# -*- coding: utf-8 -*-

import decimal
Decimal = decimal.Decimal
import os
import traceback
from time import strftime

from options import debug
from safe_print import safe_print
from util_io import StringIOu as StringIO
from util_str import safe_unicode
import CGATS
import ICCProfile as ICCP

cals = {}

def quote_nonoption_args(args):
	""" Puts quotes around all arguments which are not options 
	(ie. which do not start with a hyphen '-')
	
	"""
	args = list(args)
	for i, arg in enumerate(args):
		if arg[0] != "-":
			args[i] = '"' + arg + '"'
	return args


def add_dispcal_options_to_cal(cal, options_dispcal):
	# Add dispcal options to cal
	options_dispcal = quote_nonoption_args(options_dispcal)
	try:
		cgats = CGATS.CGATS(cal)
		cgats[0].add_section("ARGYLL_DISPCAL_ARGS", 
							 " ".join(options_dispcal).encode("UTF-7", 
															  "replace"))
		return cgats
	except Exception, exception:
		safe_print(safe_unicode(traceback.format_exc()))


def add_options_to_ti3(ti3, options_dispcal=None, options_colprof=None):
	# Add dispcal and colprof options to ti3
	try:
		cgats = CGATS.CGATS(ti3)
		if options_colprof:
			options_colprof = quote_nonoption_args(options_colprof)
			cgats[0].add_section("ARGYLL_COLPROF_ARGS", 
							   " ".join(options_colprof).encode("UTF-7", 
																"replace"))
		if options_dispcal and len(cgats) > 1:
			options_dispcal = quote_nonoption_args(options_dispcal)
			cgats[1].add_section("ARGYLL_DISPCAL_ARGS", 
							   " ".join(options_dispcal).encode("UTF-7", 
																"replace"))
		return cgats
	except Exception, exception:
		safe_print(safe_unicode(traceback.format_exc()))


def cal_to_fake_profile(cal):
	""" 
	Create and return a 'fake' ICCProfile with just a vcgt tag.
	
	cal must refer to a valid Argyll CAL file and can be a CGATS instance 
	or a filename.
	
	"""
	if not isinstance(cal, CGATS.CGATS):
		try:
			cal = CGATS.CGATS(cal)
		except (IOError, CGATS.CGATSInvalidError, 
			CGATS.CGATSInvalidOperationError, CGATS.CGATSKeyError, 
			CGATS.CGATSTypeError, CGATS.CGATSValueError), exception:
			safe_print(u"Warning - couldn't process CGATS file '%s': %s" % 
					   tuple(safe_unicode(s) for s in (cal, exception)))
			return None
	required_fields = ("RGB_I", "RGB_R", "RGB_G", "RGB_B")
	data_format = cal.queryv1("DATA_FORMAT")
	if data_format:
		for field in required_fields:
			if not field in data_format.values():
				if debug: safe_print("[D] Missing required field:", field)
				return None
		for field in data_format.values():
			if not field in required_fields:
				if debug: safe_print("[D] Unknown field:", field)
				return None
	entries = cal.queryv(required_fields)
	if len(entries) < 1:
		if debug: safe_print("[D] No entries found in", cal.filename)
		return None
	profile = ICCP.ICCProfile()
	profile.fileName = cal.filename
	profile._data = "\0" * 128
	profile._tags.desc = ICCP.TextDescriptionType("", "desc")
	profile._tags.desc.ASCII = safe_unicode(
				os.path.basename(cal.filename)).encode("ascii", "asciize")
	profile._tags.desc.Unicode = safe_unicode(os.path.basename(cal.filename))
	profile._tags.vcgt = ICCP.VideoCardGammaTableType("", "vcgt")
	profile._tags.vcgt.update({
		"channels": 3,
		"entryCount": len(entries),
		"entrySize": 2,
		"data": [[], [], []]
	})
	for n in entries:
		for i in range(3):
			profile._tags.vcgt.data[i].append(int(round(entries[n][i + 1] * 
														65535.0)))
	profile.size = len(profile.data)
	profile.is_loaded = True
	return profile


def can_update_cal(path):
	""" Check if cal can be updated by checking for required fields. """
	try:
		calstat = os.stat(path)
	except Exception, exception:
		safe_print(u"Warning - os.stat('%s') failed: %s" % 
				   tuple(safe_unicode(s) for s in (path, exception)))
		return False
	if not path in cals or cals[path].mtime != calstat.st_mtime:
		try:
			cal = CGATS.CGATS(path)
		except (IOError, CGATS.CGATSInvalidError, 
			CGATS.CGATSInvalidOperationError, CGATS.CGATSKeyError, 
			CGATS.CGATSTypeError, CGATS.CGATSValueError), exception:
			if path in cals:
				del cals[path]
			safe_print(u"Warning - couldn't process CGATS file '%s': %s" % 
					   tuple(safe_unicode(s) for s in (path, exception)))
		else:
			if cal.queryv1("DEVICE_TYPE") in ("CRT", "LCD") and not None in \
			   (cal.queryv1("TARGET_WHITE_XYZ"), 
				cal.queryv1("TARGET_GAMMA"), 
				cal.queryv1("BLACK_POINT_CORRECTION"), 
				cal.queryv1("QUALITY")):
				cals[path] = cal
	return path in cals and cals[path].mtime == calstat.st_mtime


def extract_cal_from_ti3(ti3_data):
	"""
	Extract and return the CAL section of a TI3.
	
	ti3_data can be a file object or a string holding the data.
	
	"""
	if isinstance(ti3_data, (str, unicode)):
		ti3 = StringIO(ti3_data)
	else:
		ti3 = ti3_data
	cal = False
	cal_lines = []
	for line in ti3:
		line = line.strip()
		if line == "CAL":
			line = "CAL    "  # Make sure CGATS file identifiers are 
							  # always a minimum of 7 characters
			cal = True
		if cal:
			cal_lines += [line]
			if line == 'END_DATA':
				break
	if isinstance(ti3, file):
		ti3.close()
	return "\n".join(cal_lines)


def extract_fix_copy_cal(source_filename, target_filename=None):
	"""
	Return the CAL section from a profile's embedded measurement data.
	
	Try to 'fix it' (add information needed to make the resulting .cal file
	'updateable') and optionally copy it to target_filename.
	
	"""
	from worker import get_options_from_profile
	try:
		profile = ICCP.ICCProfile(source_filename)
	except (IOError, ICCP.ICCProfileInvalidError), exception:
		return exception
	if "CIED" in profile.tags or "targ" in profile.tags:
		cal_lines = []
		ti3 = StringIO(profile.tags.get("CIED", "") or 
					   profile.tags.get("targ", ""))
		ti3_lines = [line.strip() for line in ti3]
		ti3.close()
		cal_found = False
		for line in ti3_lines:
			line = line.strip()
			if line == "CAL":
				line = "CAL    "  # Make sure CGATS file identifiers are 
								  #always a minimum of 7 characters
				cal_found = True
			if cal_found:
				cal_lines += [line]
				if line == 'DEVICE_CLASS "DISPLAY"':
					options_dispcal = get_options_from_profile(profile)[0]
					if options_dispcal:
						whitepoint = False
						b = profile.tags.lumi.Y
						for o in options_dispcal:
							if o[0] == "y":
								cal_lines += ['KEYWORD "DEVICE_TYPE"']
								if o[1] == "c":
									cal_lines += ['DEVICE_TYPE "CRT"']
								else:
									cal_lines += ['DEVICE_TYPE "LCD"']
								continue
							if o[0] in ("t", "T"):
								continue
							if o[0] == "w":
								continue
							if o[0] in ("g", "G"):
								if o[1:] == "240":
									trc = "SMPTE240M"
								elif o[1:] == "709":
									trc = "REC709"
								elif o[1:] == "l":
									trc = "L_STAR"
								elif o[1:] == "s":
									trc = "sRGB"
								else:
									trc = o[1:]
									if o[0] == "G":
										try:
											trc = 0 - Decimal(trc)
										except decimal.InvalidOperation, \
											   exception:
											continue
								cal_lines += ['KEYWORD "TARGET_GAMMA"']
								cal_lines += ['TARGET_GAMMA "%s"' % trc]
								continue
							if o[0] == "f":
								cal_lines += ['KEYWORD '
									'"DEGREE_OF_BLACK_OUTPUT_OFFSET"']
								cal_lines += [
									'DEGREE_OF_BLACK_OUTPUT_OFFSET "%s"' % 
									o[1:]]
								continue
							if o[0] == "k":
								cal_lines += ['KEYWORD '
									'"BLACK_POINT_CORRECTION"']
								cal_lines += [
									'BLACK_POINT_CORRECTION "%s"' % o[1:]]
								continue
							if o[0] == "B":
								cal_lines += ['KEYWORD '
									'"TARGET_BLACK_BRIGHTNESS"']
								cal_lines += [
									'TARGET_BLACK_BRIGHTNESS "%s"' % o[1:]]
								continue
							if o[0] == "q":
								if o[1] == "l":
									q = "low"
								elif o[1] == "m":
									q = "medium"
								else:
									q = "high"
								cal_lines += ['KEYWORD "QUALITY"']
								cal_lines += ['QUALITY "%s"' % q]
								continue
						if not whitepoint:
							cal_lines += ['KEYWORD "NATIVE_TARGET_WHITE"']
							cal_lines += ['NATIVE_TARGET_WHITE ""']
		if cal_lines:
			if target_filename:
				try:
					f = open(target_filename, "w")
					f.write("\n".join(cal_lines))
					f.close()
				except Exception, exception:
					return exception
			return cal_lines
	else:
		return None


def ti3_to_ti1(ti3_data):
	"""
	Create and return TI1 data converted from TI3.
	
	ti3_data can be a file object or a string holding the data.
	
	"""
	if isinstance(ti3_data, (str, unicode)):
		ti3 = StringIO(ti3_data)
	else:
		ti3 = ti3_data
	ti1_lines = []
	for line in ti3:
		line = line.strip()
		if line == "CTI3":
			line = 'CTI1   '  # Make sure CGATS file identifiers are 
							  # always a minimum of 7 characters
		else:
			values = line.split(None, 1)
			if len(values) > 1:
				if "DEVICE_CLASS" in values or "LUMINANCE_XYZ_CDM2" in values:
					continue
				if values[0] == "DESCRIPTOR":
					values[1] = ('"Argyll Calibration Target chart '
								 'information 1"')
				elif values[0] == "ORIGINATOR":
					values[1] = '"Argyll targen"'
				elif values[0] == "COLOR_REP":
					values[1] = '"%s"' % values[1].strip('"').split('_')[0]
				line = " ".join(values)
		ti1_lines += [line]
		if line == 'END_DATA':
			break
	if isinstance(ti3, file):
		ti3.close()
	return "\n".join(ti1_lines)


def vcgt_to_cal(profile):
	""" Return a CAL (CGATS instance) from vcgt """
	cgats = CGATS.CGATS(file_identifier="CAL    ")
	context = cgats.add_data({"DESCRIPTOR": "Argyll Device Calibration State"})
	context.add_data({"ORIGINATOR": "vcgt"})
	context.add_data({"CREATED": strftime("%a %b %d %H:%M:%S %Y",
										  profile.dateTime.timetuple())})
	context.add_keyword("DEVICE_CLASS", "DISPLAY")
	context.add_keyword("COLOR_REP", "RGB")
	context.add_keyword("RGB_I")
	key = "DATA_FORMAT"
	context[key] = CGATS.CGATS()
	context[key].key = key
	context[key].parent = context
	context[key].root = cgats
	context[key].type = key
	context[key].add_data(("RGB_I", "RGB_R", "RGB_G", "RGB_B"))
	key = "DATA"
	context[key] = CGATS.CGATS()
	context[key].key = key
	context[key].parent = context
	context[key].root = cgats
	context[key].type = key
	values = profile.tags.vcgt.getNormalizedValues()
	for i, triplet in enumerate(values):
		context[key].add_data(("%.7f" % (i / float(len(values) - 1)), ) + triplet)
	return cgats


def verify_cgats(cgats, required, ignore_unknown=True):
	"""
	Verify and return a CGATS instance or None on failure.
	
	Verify if a CGATS instance has a section with all required fields. 
	Return the section as CGATS instance on success, None on failure.
	
	If ignore_unknown evaluates to True, ignore fields which are not required.
	Otherwise, the CGATS data must contain only the required fields, no more,
	no less.
	"""
	cgats_1 = cgats.queryi1(required)
	if cgats_1 and cgats_1.parent and cgats_1.parent.parent:
		cgats_1 = cgats_1.parent.parent
		if cgats_1.queryv1("NUMBER_OF_SETS"):
			if cgats_1.queryv1("DATA_FORMAT"):
				for field in required:
					if not field in cgats_1.queryv1("DATA_FORMAT").values():
						raise CGATS.CGATSKeyError("Missing required field: %s" % field)
				if not ignore_unknown:
					for field in cgats_1.queryv1("DATA_FORMAT").values():
						if not field in required:
							raise CGATS.CGATSError("Unknown field: %s" % field)
			else:
				raise CGATS.CGATSInvalidError("Missing DATA_FORMAT")
		else:
			raise CGATS.CGATSInvalidError("Missing NUMBER_OF_SETS")
		cgats_1.filename = cgats.filename
		return cgats_1
	else:
		raise CGATS.CGATSKeyError("Missing required fields: %s" % 
								  ", ".join(required))

def verify_ti1_rgb_xyz(cgats):
	"""
	Verify and return a CGATS instance or None on failure.
	
	Verify if a CGATS instance has a TI1 section with all required fields 
	for RGB devices. Return the TI1 section as CGATS instance on success, 
	None on failure.
	
	"""
	return verify_cgats(cgats, ("SAMPLE_ID", "RGB_R", "RGB_B", "RGB_G", 
								"XYZ_X", "XYZ_Y", "XYZ_Z"))
