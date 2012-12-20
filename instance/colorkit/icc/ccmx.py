#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import with_statement  # Python 2.5
import codecs
import os
import sys
import time

import demjson


CCMX_TEMPLATE = '''CCMX   

DESCRIPTOR "%(Name)s"
KEYWORD "INSTRUMENT"
INSTRUMENT "%(Device)s"
KEYWORD "DISPLAY"
DISPLAY "%(Display)s"
KEYWORD "REFERENCE"
REFERENCE "%(ReferenceDevice)s"
ORIGINATOR "%(Originator)s"
CREATED "%(DateTime)s"
KEYWORD "COLOR_REP"
COLOR_REP "XYZ"

NUMBER_OF_FIELDS 3
BEGIN_DATA_FORMAT
XYZ_X XYZ_Y XYZ_Z 
END_DATA_FORMAT

NUMBER_OF_SETS 3
BEGIN_DATA
%(MatrixXYZ)s
END_DATA
'''


def convert_devicecorrections_to_ccmx(path, target_dir):
	""" Convert iColorDisplay DeviceCorrections.txt to individual Argyll CCMX files """
	with codecs.open(path, 'r', 'utf8') as devcorrections_file:
		lines = devcorrections_file.read().strip().splitlines()
	# Convert to JSON
	# The DeviceCorrections.txt format is as follows, so a conversion is pretty
	# straightforward:
	# "Description here, e.g. Instrument X for Monitor Y" = 
	# {
	# 	Name = "Description here, e.g. Instrument X for Monitor Y"
	# 	Device = "Instrument X"
	# 	Display = "Monitor Y"
	# 	ReferenceDevice = "eye-one Pro Rev.D"
	# 	MatrixXYZ = "3 3 1482250784 1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0 "
	# }
	# "Description here, e.g. Instrument X for Monitor Y" = 
	# {
	# 	Name = "Description here, e.g. Instrument X for Monitor Y"
	# 	Device = "Instrument X"
	# 	Display = "Monitor Y"
	# 	ReferenceDevice = "eye-one Pro Rev.D"
	# 	MatrixXYZ = "3 3 1482250784 1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0 "
	# }
	# ...etc.
	# NOTE: The first three numbers in MatrixXYZ are irrelevant for our purposes.
	for i, line in enumerate(lines):
		parts = line.strip().split('=')
		if len(parts) == 2:
			for j, part in enumerate(parts):
				part = part.strip()
				if part and not part.startswith('"') and not part.endswith('"'):
					parts[j] = '"%s"' % part
		if parts[-1].strip() not in('', '{') and i < len(lines) - 1:
			parts[-1] += ','
		lines[i] = ':'.join(parts)
	devcorrections_data = '{%s}' % ''.join(lines).replace(',}', '}')
	# Parse JSON
	devcorrections = demjson.decode(devcorrections_data)
	# Convert to ccmx
	for name, devcorrection in devcorrections.iteritems():
		values = {'DateTime': time.strftime('%a %b %d %H:%M:%S %Y'),
				  'Originator': "Quato iColorDisplay"}
		for key in ('Name', 'Device', 'Display', 'ReferenceDevice', 'MatrixXYZ'):
			value = devcorrection[key]
			if key == 'MatrixXYZ':
				# The first three numbers in the matrix are irrelevant for our 
				# purposes (see format example above).
				matrix = value.split()[3:]
				value = '\n'.join([' '.join(part) for part in (matrix[0:3], 
															   matrix[3:6], 
															   matrix[6:9])])
			values[key] = value
		with codecs.open(os.path.join(target_dir, name + '.ccmx'), 'w', 
						 'utf8') as ccmx:
			ccmx.write(CCMX_TEMPLATE % values)


if __name__ == '__main__':
	convert_devicecorrections_to_ccmx(sys.argv[1], 
									  os.path.dirname(sys.argv[1]))
