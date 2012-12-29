
from collections import namedtuple

from django.db import models
import numpy

# Add recognized model option to django
import django.db.models.options as options
options.DEFAULT_NAMES = options.DEFAULT_NAMES + ('dtype',)



class RGBColor(namedtuple("RGBColor", 'r g b')):
            
    __slots__ = ()
            
    def __repr__(self):
        return "%s(dtype=%s, %s)" % (
            'RGBColor', self.dtype, ', '.join(
                ['%s=%s' % (i[0], i[1]) \
                    for i in self._asdict().items()]))
            
    def __doc__(self):
        return """
        %(clsname)s(%(channels)s):
        Returns a set of %(upperclsname)s-space coordinates as a dtyped %(length)s-channel vector,
        representing one unique (pseudo-`const`) %(upperclsname)s value.
        """ % {
            'clsname': 'RGBColor',
            'upperclsname': 'RGB',
            'channels': ', '.join(
                ['%s=%s' % (chn, "<%s>" % self.dtype.name) \
                    for chn in ('r', 'g', 'b')]),
            'length': 3, }
            
    @property
    def name(self):
        return self.__class__.__name__
            
    @property
    def dtype(self):
        return numpy.dtype('uint8')
            
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
        return ''.join(['0x%0', str(len(self)*2), 'X']) % hash(self)
            
    def __str__(self):
        return ''.join(['#%0', str(len(self)*2), 'X']) % hash(self)
        #return ('#%%0 %iX' % len(self)*2) % hash(self)
            
    def __unicode__(self):
        return u''.join([u'#%0', unicode(len(self)*2), u'X']) % hash(self)
        #return (u'#%%0 %iX' % len(self)*2) % hash(self)


class RGB(models.Model):
    id = models.PositiveIntegerField(
        primary_key=True,
        db_index=True,
        unique=True,
        default=0,
        blank=True,
        null=False)
    
    _r = models.PositiveSmallIntegerField(
        db_index=True,
        unique=False,
        default=0)
    _g = models.PositiveSmallIntegerField(
        db_index=True,
        unique=False,
        default=0)
    _b = models.PositiveSmallIntegerField(
        db_index=True,
        unique=False,
        default=0)
    
    def save(self, *args, **kwargs):
        from colordb.namedcolor import uint24_to_rgb
        self._r, self._g, self._b = uint24_to_rgb(self.id)
        super(RGB, self).save(*args, **kwargs)
    
    def _get_named_tuple(self):
        return RGBColor(
            r=((self.id >> 16) & 255),
            g=((self.id >> 8) & 255),
            b=(self.id & 255))
    
    value = property(_get_named_tuple)
    
    def _get_r(self):
        return self.value.r
    
    def _get_g(self):
        return self.value.g
    
    def _get_b(self):
        return self.value.b
    
    r = property(_get_r)
    g = property(_get_g)
    b = property(_get_b)
    