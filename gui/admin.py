from django.contrib import admin

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CurrentCruise, CruiseState
from .models import ServerState, ServerMessage, StatusUpdate

#############################################
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

#############################################
class LoggerAdmin(admin.ModelAdmin):
  list_display = ('name', 'cruise', 'config')
  list_filter = ('cruise',)

class LoggerConfigAdmin(admin.ModelAdmin):
  list_display = ('name', 'logger', 'mode', 'enabled', 'config_json')
  list_filter = ('logger', 'mode', 'enabled')

class LoggerConfigStateAdmin(admin.ModelAdmin):
  list_display = ('timestamp', 'logger', 'config', 'running',
                  'process_id', 'errors')
  list_filter = ('logger__cruise', 'logger', 'config', 'running')
  
#############################################
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

#############################################
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

class CurrentCruiseAdmin(admin.ModelAdmin):
  list_display = ('cruise', 'as_of')

class CruiseStateAdmin(admin.ModelAdmin):
  list_display = ('cruise', 'current_mode', 'started')
  list_filter = ('cruise',)

#############################################
class ServerStateAdmin(admin.ModelAdmin):
  list_display = ('timestamp', 'server', 'running', 'desired', 'process_id')
  list_filter = ('server', 'running', 'desired')

class ServerMessageAdmin(admin.ModelAdmin):
  list_display = ('timestamp', 'server', 'message')
  list_filter = ('server',)

class StatusUpdateAdmin(admin.ModelAdmin):
  list_display = ('timestamp', 'server', 'cruise', 'status')

#############################################
admin.site.register(Logger, LoggerAdmin)
admin.site.register(LoggerConfig, LoggerConfigAdmin)
admin.site.register(LoggerConfigState, LoggerConfigStateAdmin)

admin.site.register(Mode, ModeAdmin)

admin.site.register(Cruise, CruiseAdmin)
admin.site.register(CurrentCruise, CurrentCruiseAdmin)
admin.site.register(CruiseState, CruiseStateAdmin)

admin.site.register(ServerState, ServerStateAdmin)
admin.site.register(ServerMessage, ServerMessageAdmin)
admin.site.register(StatusUpdate, StatusUpdateAdmin)



