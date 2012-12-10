#!/usr/bin/env python
# encoding: utf-8
"""
colordb/colortype.py

Created by FI$H 2000 on 2012-08-23.
Copyright (c) 2012 Objects In Space And Time, LLC. All rights reserved.
"""

import numpy
#from os.path import join
from collections import namedtuple, defaultdict
from colordb.utils import split_abbreviations
from colordb.exceptions import InvalidColorTypeString

color_types = defaultdict(lambda: {})

def ColorType(name, *args, **kwargs):
    global color_types
    dtype = numpy.dtype(kwargs.pop('dtype', 'uint8'))
    ndtype = dtype.name
    if name not in color_types[ndtype].keys():
        __channels__ = channels = split_abbreviations(name)
        if not len(channels) > 0:
            raise InvalidColorTypeString("""
                ColorType() called without a format string
                specifying at least one channel (as a capital letter).""")
        
        class Color(namedtuple(name, channels, dtype)):
            
            __slots__ = ()
            
            def __repr__(self):
                return "%s(dtype=%s, %s)" % (
                    name, dtype, ', '.join(
                        ['%s=%s' % (i[0], i[1]) \
                            for i in self._asdict().items()]))
            
            def __str__(self):
                return str(repr(self))
            
            def __unicode__(self):
                return unicode(str(self))
            
            def __doc__(self):
                return """
                %(clsname)s(%(channels)s) returns %(upperclsname)s %(length)s-channel color object initialized with the named values.
                """ % {
                    'clsname': name,
                    'upperclsname': name,
                    'channels': ', '.join(
                        ['%s=%s' % (chn, "<%s>" % dtype.name) \
                            for chn in __channels__]),
                    'length': len(__channels__), }
            
            def _cast(self, new_dtype=None):
                if new_dtype is None:
                    new_dtype = numpy.dtype('uint8')
                if numpy.dtype(new_dtype) in numpy.cast.keys():
                    NewColorType = ColorType(name, dtype=new_dtype)
                    return NewColorType(*map(new_dtype.type, tuple(self)))
                return self
            
            @property
            def dtype(self):
                return self.__dtype__
            
            def __eq__(self, other):
                if not len(other) == len(self):
                    return False
                return all([self[i] == other[i] \
                    for i in xrange(len(self))])
            
            def __hash__(self):
                return sum(map(
                    lambda chn: chn[1]*(256**chn[0]),
                    zip(reversed(
                        xrange(len(self))), self)))
            
            def __array_interface__(self):
                """ Many more details available:
                    http://docs.scipy.org/doc/numpy/reference/arrays.interface.html#python-side """
                return dict(
                    version=3,
                    shape=(len(__channels__),),
                    typestr='|V%s' % len(self.__channels__),
                    descr=[(channel, self.dtype.str) for channel in __channels__])
        
        Color.__name__ = name
        Color.__dtype__ = dtype
        color_types[ndtype][name] = Color
    
    return color_types[ndtype][name]

