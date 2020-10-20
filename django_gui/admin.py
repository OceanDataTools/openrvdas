from django.contrib import admin

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise
from .models import LastUpdate
from .models import LogMessage


#############################################
class ModeInline(admin.TabularInline):
    model = Mode
    extra = 0
    list_display = ('name', 'cruise')
    fieldsets = [(None,    {'fields': ['name', 'cruise']})]

    readonly_fields = ('name', 'cruise')
    can_delete = False
    show_change_link = True


#############################################
class LoggerConfigModeInline(admin.TabularInline):
    model = LoggerConfig.modes.through
    extra = 0
    # fields = ('logger', 'name')
    # readonly_fields = ('name', 'logger', 'current_config', 'enabled', 'modes', 'config_json')
    can_delete = False
    show_change_link = True


#############################################
class LoggerAdmin(admin.ModelAdmin):
    list_display = ('name', 'cruise', 'config')
    list_filter = ('cruise',)


#############################################
class LoggerConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'logger', 'get_modes', 'current_config',
                    'enabled', 'config_json')
    list_filter = ('logger', 'enabled')

    def get_modes(self, obj):
        return "\n".join([m.name for m in obj.modes.all()])

    inlines = [LoggerConfigModeInline]


#############################################
class LoggerConfigStateAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'last_checked', 'logger', 'config',
                    'running', 'failed', 'pid', 'errors')
    list_filter = ('logger__cruise', 'logger', 'config', 'running')


#############################################
class ModeAdmin(admin.ModelAdmin):
    def configs(self, obj):
        return Mode.objects.filter(mode=obj)

    list_display = ('name', 'cruise')
    fieldsets = [
        (None,    {'fields': ['name', 'cruise']}),
        # ('JSON Source', {'classes': ['collapse'],
        #                 'fields': ['config_json']})
    ]
    inlines = [LoggerConfigModeInline]


#############################################
class CruiseAdmin(admin.ModelAdmin):
    def modes(self, obj):
        return Mode.objects.filter(cruise=obj)

    list_display = ('id', 'end', 'start',
                    'active_mode', 'default_mode',
                    'config_filename', 'loaded_time', 'modes')
    fieldsets = [
        (None,    {'fields': ['id', 'active_mode']}),
        ('Dates', {'classes': ['collapse'],
                   'fields': ['start', 'end']}),
        ('Source', {'classes': ['collapse'],
                    'fields': ['config_filename', 'config_text']})
    ]
    inlines = [ModeInline]


#############################################
class LastUpdateAdmin(admin.ModelAdmin):
    list_display = ('timestamp',)


#############################################
class LogMessageAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'source', 'user', 'log_level',
                    'cruise_id', 'message')
    list_filter = ('source', 'user', 'log_level', 'cruise_id')


#############################################
# class CurrentCruiseAdmin(admin.ModelAdmin):
#  list_display = ('cruise', 'as_of')

# class CruiseStateAdmin(admin.ModelAdmin):
#  list_display = ('cruise', 'active_mode', 'started')
#  list_filter = ('cruise',)


#############################################
# class ServerStateAdmin(admin.ModelAdmin):
#  list_display = ('timestamp', 'server', 'running', 'desired', 'process_id')
#  list_filter = ('server', 'running', 'desired')

# class StatusUpdateAdmin(admin.ModelAdmin):
#  list_display = ('timestamp', 'server', 'cruise', 'status')


#############################################
admin.site.register(Logger, LoggerAdmin)
admin.site.register(LoggerConfig, LoggerConfigAdmin)
admin.site.register(LoggerConfigState, LoggerConfigStateAdmin)

admin.site.register(Mode, ModeAdmin)

admin.site.register(Cruise, CruiseAdmin)
admin.site.register(LogMessage, LogMessageAdmin)
admin.site.register(LastUpdate, LastUpdateAdmin)

# admin.site.register(CurrentCruise, CurrentCruiseAdmin)
# admin.site.register(CruiseState, CruiseStateAdmin)

# admin.site.register(StatusUpdate, StatusUpdateAdmin)
# admin.site.register(ServerState, ServerStateAdmin)
