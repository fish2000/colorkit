# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'RGB'
        db.create_table('colordb_rgb', (
            ('id', self.gf('django.db.models.fields.PositiveIntegerField')(default=0, unique=True, primary_key=True, db_index=True)),
            ('_r', self.gf('django.db.models.fields.PositiveSmallIntegerField')(default=0, db_index=True)),
            ('_g', self.gf('django.db.models.fields.PositiveSmallIntegerField')(default=0, db_index=True)),
            ('_b', self.gf('django.db.models.fields.PositiveSmallIntegerField')(default=0, db_index=True)),
        ))
        db.send_create_signal('colordb', ['RGB'])


    def backwards(self, orm):
        # Deleting model 'RGB'
        db.delete_table('colordb_rgb')


    models = {
        'colordb.rgb': {
            'Meta': {'object_name': 'RGB'},
            '_b': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '0', 'db_index': 'True'}),
            '_g': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '0', 'db_index': 'True'}),
            '_r': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '0', 'db_index': 'True'}),
            'id': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0', 'unique': 'True', 'primary_key': 'True', 'db_index': 'True'})
        }
    }

    complete_apps = ['colordb']