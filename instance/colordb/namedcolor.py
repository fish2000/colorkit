

"""
Blue =  RGBint & 255
Green = (RGBint >> 8) & 255
Red =   (RGBint >> 16) & 255
"""

from colortype import ColorType

RGB = ColorType('RGB')

def uint24_to_rgb(uint24=0):
    """ convert an unsigned 24-bit(ish) integer to an RGB triple of uint8 values (r, g, b). """
    return (
        (uint24 & 255),
        ((uint24 >> 8) & 255),
        ((uint24 >> 16) & 255))

def uint24_to_hex(uint24=0):
    """ convert an unsigned 24-bit(ish) integer to a hex string '#RRGGBB'. """
    return '#%06X' % uint24

def hex_to_int(hexstr):
    """ convert a hex string '#RRGGBB' to an integer. """
    return int(hexstr.lower().lstrip('#0x'), 16)






def main():
    hexes = ['#CC33CC', 'CC33CC', 'ff0fe3', '#ff1912', '0x3366A2', '0XAFAFf6', '#000312', '#0101A1', '#FA9421']
    
    for hexnum in hexes:
        print 'hex_to_int(%s) = %s' % (hexnum, hex_to_int(hexnum))
        print 'uint24_to_rgb(%s) = %s' % (hex_to_int(hexnum), uint24_to_rgb(hex_to_int(hexnum)))
        print 'RGB(*%s) = %s' % (uint24_to_rgb(hex_to_int(hexnum)), RGB(*uint24_to_rgb(hex_to_int(hexnum)))._asdict())
        print 'str(RGB(*%s)) = %s' % (uint24_to_rgb(hex_to_int(hexnum)), str(RGB(*uint24_to_rgb(hex_to_int(hexnum)))))
        print 'uint24_to_hex(%s) = %s' % (hex_to_int(hexnum), uint24_to_hex(hex_to_int(hexnum)))
        print ''


if __name__ == '__main__':
    main()