#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from colorkit.icc import ICCProfile as iccp
from colorkit.icc.defaultpaths import iccprofiles, iccprofiles_home
from colorkit.icc.safe_print import safe_print

pths = set(iccprofiles_home + iccprofiles)
pths.add('/Users/fish/Library/ColorSync/Profiles')
pths.add('/Users/fish/Dropbox/ost2/face/icc/uploads')
pths.add('/Users/fish/Dropbox/ost2/face/icc/s3')

for p in pths:
    if os.path.isdir(p):
        for f in os.listdir(p):
            try:
                profile = iccp.ICCProfile(os.path.join(p, f))
            except:
                pass
            else:
                if "ncl2" in profile.tags:
                    safe_print(f)
                    safe_print(profile.tags.ncl2)
                    safe_print("")
                    
                    #profile.print_info()
                    for label, value in profile.get_info():
                        if not value:
                            safe_print(unicode(label))
                        else:
                            safe_print(unicode(label) + u":", unicode(value))
                    
                    safe_print("")

