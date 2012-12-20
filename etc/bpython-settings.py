
## timer
import time
t1 = time.time()

## setup django
from django.core.management import setup_environ
import colorkit.settings
setup_environ(colorkit.settings)

from django.conf import settings
from django.contrib.auth.models import User
fish = User.objects.get(username='fish')

from tagging.models import Tag as Tagg

## web scraping stuff
from BeautifulSoup import BeautifulSoup
import os, sys, re, urllib2, requests, xerox

## how long... has this been... going on?
t2 = time.time()
dt = str((t2-t1)*1.00)
dtout = dt[:(dt.find(".")+4)]
print ">>> VirtualEnv colorkit Praxon loaded in %ssec from %s" % (dtout, '/Users/fish/Praxa/colorkit')




