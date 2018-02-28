from django.contrib import admin

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CurrentCruise, CruiseState

class ModeInline(admin.TabularInline):
  model = Mode
  extra = 0
  list_display = ('name', 'cruise')
  fieldsets = [(None,    {'fields':['name', 'cruise']})]
  
  readonly_fields = ('name', 'cruise')
  can_delete = False
  show_change_link = True
  
class LoggerConfigInline(admin.TabularInline):
  model = LoggerConfig
  extra = 0
  fields = ('logger', 'name')
  readonly_fields = ('name', 'logger', 'enabled', 'mode', 'config_json')
  can_delete = False
  show_change_link = True
  """fieldsets = [
    (None,    {'fields':['name', 'logger']}),
    ('JSON Source', {'classes': ['collapse'],
                     'fields': ['config_json']})
    ]
  """
class CruiseAdmin(admin.ModelAdmin):
  def modes(self, obj):
    return Mode.objects.filter(cruise=obj)

  list_display = ('id', 'end', 'start',
                  'current_mode', 'default_mode',
                  'config_filename', 'loaded_time', 'modes')
  fieldsets = [
    (None,    {'fields':['id', 'current_mode']}),
    ('Dates', {'classes': ['collapse'],
               'fields': ['start', 'end']}),
    ('Source', {'classes': ['collapse'],
               'fields': ['config_filename', 'config_text']})
    ]
  inlines = [ ModeInline ]

class ModeAdmin(admin.ModelAdmin):
  def configs(self, obj):
    return Mode.objects.filter(mode=obj)

  list_display = ('name', 'cruise')
  fieldsets = [
    (None,    {'fields':['name', 'cruise']}),
    #('JSON Source', {'classes': ['collapse'],
    #                 'fields': ['config_json']})
    ]
  inlines = [ LoggerConfigInline ]

class CurrentCruiseAdmin(admin.ModelAdmin):
  list_display = ('cruise', 'as_of')

admin.site.register(Cruise, CruiseAdmin)

admin.site.register(Mode, ModeAdmin)

admin.site.register(CurrentCruise, CurrentCruiseAdmin)

admin.site.register(Logger)
admin.site.register(LoggerConfig)
admin.site.register(LoggerConfigState)
admin.site.register(CruiseState)
