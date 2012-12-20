#!/usr/bin/env python
# encoding: utf-8
"""
colordb/colortype.py

Created by FI$H 2000 on 2012-08-23.
Copyright (c) 2012 Objects In Space And Time, LLC. All rights reserved.
"""

import numpy
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
        #print "*** %s" % name
        if not len(channels) > 0:
            raise InvalidColorTypeString("""
                ColorType() called without a format string
                specifying at least one channel (as a capital letter).""")
        
        class Color(namedtuple(name, " ".join(channels))):
            
            __slots__ = ()
            
            def __repr__(self):
                return "%s(dtype=%s, %s)" % (
                    name, dtype, ', '.join(
                        ['%s=%s' % (i[0], i[1]) \
                            for i in self._asdict().items()]))
            
            def __doc__(self):
                return """
                %(clsname)s(%(channels)s):
                Returns a set of %(upperclsname)s-space coordinates as a dtyped %(length)s-channel vector,
                representing one unique (pseudo-`const`) %(upperclsname)s value.
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
            def name(self):
                return self.__class__.__name__
            
            @property
            def dtype(self):
                return self.__dtype__
            
            def __hash__(self):
                return sum(map(
                    lambda chn: chn[1]*(256**chn[0]),
                    zip(xrange(len(self)), self)))
            
            def __int__(self):
                return int(hash(self))
            
            def __long__(self):
                return long(int(self))
            
            def __float__(self):
                return float(int(self))
            
            def __old_eq__(self, other):
                if not len(other) == len(self):
                    return False
                return all([self[i] == other[i] \
                    for i in xrange(len(self))])
            
            def __eq__(self, other):
                return (hash(self) == hash(other)) and \
                    (self.name == other.name)
            
            def __ne__(self, other):
                return (hash(self) != hash(other)) or \
                    (self.name != other.name)
            
            def __nonzero__(self):
                return numpy.any(self)
            
            def __oct__(self):
                return '0%0o' % hash(self)
            
            def __hex__(self):
                return ''.join(['0x%0', str(len(__channels__)*2), 'X']) % hash(self)
            
            def __str__(self):
                return ''.join(['#%0', str(len(__channels__)*2), 'X']) % hash(self)
                #return ('#%%0 %iX' % len(self)*2) % hash(self)
            
            def __unicode__(self):
                return u''.join([u'#%0', unicode(len(__channels__)*2), u'X']) % hash(self)
                #return (u'#%%0 %iX' % len(self)*2) % hash(self)
            
            def __array_interface__(self):
                """ Many more details available:
                    http://docs.scipy.org/doc/numpy/reference/arrays.interface.html#python-side """
                return dict(
                    version=3,
                    data=(id(self), True),
                    shape=(len(__channels__),),
                    typestr='%s%s%s' % (
                        self.dtype.byteorder,
                        self.dtype.kind,
                        self.dtype.itemsize),
                    descr=[(channel, self.dtype.str) \
                        for channel in __channels__])
        
        Color.__name__ = name
        Color.__dtype__ = dtype
        color_types[ndtype][name] = Color
        return Color
    
    return color_types[ndtype][name]


def main():
    RGB = ColorType('RGB', dtype=numpy.dtype('uint8'))
    rgb = RGB(235, 21, 12)
    rgb2 = RGB(235, 21, 12)
    notrgb = RGB(66, 6, 66)
    
    
    print "rgb:"
    print rgb
    print "hash(rgb): %s" % hash(rgb)
    print "repr(rgb): %s" % repr(rgb)
    print "str(rgb): %s" % str(rgb)
    print "unicode(rgb): %s" % unicode(rgb)
    print "int(rgb): %s" % int(rgb)
    print "long(rgb): %s" % long(rgb)
    print "float(rgb): %s" % float(rgb)
    print "oct(rgb): %s" % oct(rgb)
    print "hex(rgb): %s" % hex(rgb)
    
    print ""
    print "RGB.__name__: %s" % RGB.__name__
    print "RGB.__dtype__: %s" % RGB.__dtype__
    print "rgb.__dtype__: %s" % rgb.__dtype__
    print "rgb.name: %s" % rgb.name
    print "rgb.dtype: %s" % rgb.dtype
    
    print ""
    print "rgb == rgb2: %s" % (rgb == rgb2)
    print "rgb == notrgb: %s" % (rgb == notrgb)
    print "rgb != rgb2: %s" % (rgb != rgb2)
    print "rgb != notrgb: %s" % (rgb != notrgb)
    
    print ""
    print "rgb.__doc__(): "
    print rgb.__doc__()
    
    print ""
    print "rgb.__array_interface__(): %s" % rgb.__array_interface__()
    print "numpy.asarray(rgb): %s" % numpy.asarray(rgb2)
    print "numpy.asarray(rgb).dtype: %s" % numpy.asarray(rgb2).dtype
    print "numpy.asarray(rgb).shape: %s" % numpy.asarray(rgb2).shape
    print "numpy.array(rgb): %s" % numpy.array(rgb2)
    print "numpy.array(rgb).dtype: %s" % numpy.array(rgb2).dtype
    print "numpy.array(rgb).shape: %s" % numpy.array(rgb2).shape

if __name__ == '__main__':
    main()

