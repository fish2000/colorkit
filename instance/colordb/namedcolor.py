

"""
Blue =  RGBint & 255
Green = (RGBint >> 8) & 255
Red =   (RGBint >> 16) & 255
"""

from colordb.colortype import ColorType
from colorkit.icc.colormath import RGB2XYZ
from colorkit.icc.ICCProfile import NamedColor2Type
from colorkit.icc.ICCProfile import NamedColor2Value

RGB = ColorType('RGB')

def uint24_to_rgb(uint24=0):
    """ convert:
         an unsigned 24-bit(ish) integer
         to an RGB triple of uint8 values (r, g, b).
    """
    return (
        (uint24 & 255),
        ((uint24 >> 8) & 255),
        ((uint24 >> 16) & 255))

def uint24_to_RGB(uint24=0):
    """ convert:
         an unsigned 24-bit(ish) integer
         to an RGB triple of float 0.0-1.0 values (R, G, B).
    """
    return (uint8 / 255.0 for uint8 in uint24_to_rgb(uint24))

def uint24_to_hex(uint24=0):
    """ convert:
         an unsigned 24-bit(ish) integer
         to a hex string '#RRGGBB'.
    """
    return '#%06X' % uint24

def normalize_hex(hexstr):
    """ internal-use helper:
         for normalizing/unfucking hex RGB strings
    """
    return hexstr.upper().lstrip('#0X')

def hex_to_int(hexstr):
    """ convert:
         a hex string '#RRGGBB'
         to an integer.
    """
    return int(normalize_hex(hexstr), 16)

def hex_to_rgb(hexstr):
    """ convert:
         a hex string '#RRGGBB'
         to an RGB triple of uint8 values (r, g, b).
    """
    return uint24_to_rgb(hex_to_int(hexstr))

def hex_to_RGB(hexstr):
    """ convert:
         a hex string '#RRGGBB'
         to an RGB triple of float 0.0-1.0 values (R, G, B).
    """
    return uint24_to_RGB(hex_to_int(hexstr))




def main():
    hexes = ['#CC33CC', 'CC33CC', 'ff0fe3', '#ff1912', '0x3366A2', '0XAFAFf6', '#000312', '#0101A1', '#FA9421']
    nc2t = NamedColor2Type()
    nc2t.deviceCoordCount = 3
    nc2t._prefix = "#"
    nc2t._suffix = ""
    
    for hexnum in hexes:
        print 'hex_to_int(%s) = %s' % (hexnum, hex_to_int(hexnum))
        print 'uint24_to_rgb(%s) = %s' % (hex_to_int(hexnum), uint24_to_rgb(hex_to_int(hexnum)))
        print 'RGB(*%s) = %s' % (uint24_to_rgb(hex_to_int(hexnum)), RGB(*uint24_to_rgb(hex_to_int(hexnum)))._asdict())
        print 'str(RGB(*%s)) = %s' % (uint24_to_rgb(hex_to_int(hexnum)), str(RGB(*uint24_to_rgb(hex_to_int(hexnum)))))
        print 'uint24_to_hex(%s) = %s' % (hex_to_int(hexnum), uint24_to_hex(hex_to_int(hexnum)))
        hx = normalize_hex(
            uint24_to_hex(
                hex_to_int(hexnum)))
        
        if hx not in nc2t.keys():
            print "storing %s in NamedColor2Type... " % hx
            nc2t.add_color(hx,
                *hex_to_rgb(hexnum),
                **dict(zip('XYZ', RGB2XYZ(*hex_to_RGB(hexnum),
                    rgb_space="sRGB", scale=100.0))))
        else:
            print "%s has already been stored in the NamedColor2Type tag." % hx
        print ''
    print nc2t


if __name__ == '__main__':
    main()