from django.db import models

# Create your models here.

# Add recognized model option to django
import django.db.models.options as options
options.DEFAULT_NAMES = options.DEFAULT_NAMES + ('dtype',)
