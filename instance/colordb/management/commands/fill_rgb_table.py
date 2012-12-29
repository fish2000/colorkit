#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from optparse import make_option

class Command(BaseCommand):
    
    option_list = BaseCommand.option_list + (
        make_option('--ignore-values', '-i', dest='ignore_values',
            action="store_true", default=False,
            help="Ignore existant stored values.",
        ),
    )
    
    help = ('Fills RGB color table.')
    args = ''
    requires_model_validation = True
    can_import_settings = True

    def handle(self, *args, **options):
        from colordb.models import RGB
        
        print "Filling RGB table for (r,g,b) values 0..255 ..."
        
        for r in xrange(0, 255):
            for g in xrange(0, 255):
                for b in xrange(0, 255):
                    compand = r*(256**2) + g*256 + b
                    rgb = RGB(id=compand)
                    rgb.save()