
from django.conf import settings
from django.conf.urls import patterns, include, url, static
from django.contrib import admin

admin.autodiscover()

urlpatterns = patterns('',

    url(r'^admin/',
        include(admin.site.urls)),

) + static.static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

