from django.db import models


##############################
class Logger(models.Model):
    """Note that name may not be unique in the database - multiple cruises
    may have loggers named 'gyr1'. To distinguish conflicts, we use the
    implicit logger id."""
    name = models.CharField(max_length=255, blank=True)
    cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE,
                               blank=True, null=True)

    # The current configuration for this logger.
    config = models.ForeignKey('LoggerConfig', on_delete=models.CASCADE,
                               related_name='logger_config',
                               blank=True, null=True)

    def __str__(self):
        return self.name


##############################
class LoggerConfig(models.Model):
    name = models.CharField(max_length=255, blank=True)
    cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE,
                               blank=True, null=True)
    logger = models.ForeignKey('Logger', on_delete=models.CASCADE,
                               blank=True, null=True)

    # A config may be used by a logger in more than one mode
    modes = models.ManyToManyField('Mode')

    # Is this the currently-selected config for a logger?
    current_config = models.BooleanField(default=False)

    config_json = models.TextField('configuration string')

    # If this config is disabled, don't run it, even when mode
    # is selected.
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return '%s (%s)' % (self.name, self.modes.all())


##############################
# Do we want this logger_config running? Is it? If so, since when, and
# what's its pid?  If run state doesn't align with current mode, then
# highlight in interface
class LoggerConfigState(models.Model):
    logger = models.ForeignKey('Logger', on_delete=models.CASCADE,
                               blank=True, null=True)
    config = models.ForeignKey('LoggerConfig', on_delete=models.CASCADE,
                               blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    last_checked = models.DateTimeField(auto_now=True)

    running = models.BooleanField(default=False, blank=True, null=True)
    failed = models.BooleanField(default=False, blank=True)
    pid = models.IntegerField(default=0, blank=True, null=True)
    errors = models.TextField(default='', blank=True, null=True)


##############################
class Mode(models.Model):
    name = models.CharField(max_length=255, blank=True)
    cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE,
                               blank=True, null=True)

    def __str__(self):
        return self.name


##############################
class Cruise(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    start = models.DateTimeField(blank=True, null=True)
    end = models.DateTimeField(blank=True, null=True)

    # The file this cruise configuration has been loaded from
    config_filename = models.CharField(max_length=255, blank=True, null=True)
    config_text = models.TextField(blank=True, null=True)
    loaded_time = models.DateTimeField(auto_now_add=True, null=True)

    active_mode = models.ForeignKey('Mode', on_delete=models.SET_NULL,
                                    blank=True, null=True,
                                    related_name='cruise_active_mode')
    default_mode = models.ForeignKey('Mode', on_delete=models.SET_NULL,
                                     blank=True, null=True,
                                     related_name='cruise_default_mode')

    def modes(self):
        return list(Mode.objects.filter(cruise=self).values_list('name', flat=True))

    def __str__(self):
        return self.id


##############################
# Last time state was updated. Use this to avoid having to do
# expensive queries all the time.
class LastUpdate(models.Model):
    timestamp = models.DateTimeField(auto_now=True)


##############################
# Messages that our servers log. Note that, to avoid a lookup every
# time we write a log message, we're storing cruise_id as a string
# rather than a foreign key.
class LogMessage(models.Model):
    source = models.CharField(max_length=80, blank=True, null=True)
    user = models.CharField(max_length=80, blank=True, null=True)
    log_level = models.IntegerField(default=0, blank=True, null=True)
    cruise_id = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)


##############################
# What mode is cruise in? Since when?
# class CruiseState(models.Model):
#  cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE)
#  active_mode = models.ForeignKey('Mode', on_delete=models.CASCADE)
#  started = models.DateTimeField(auto_now_add=True)
#
#  def __str__(self):
#    return '%s: %s' % (self.cruise, self.active_mode)


##############################
# Which is our current cruise? Since when?
# class CurrentCruise(models.Model):
#  cruise = models.ForeignKey('Cruise', on_delete=models.SET_NULL,
#                             blank=True, null=True)
#  as_of = models.DateTimeField(auto_now_add=True)
#
#  def __str__(self):
#    return self.cruise.id


##############################
# Which servers are running, and when?
# If run state doesn't align with current mode, then highlight in interface
# class ServerState(models.Model):
#  timestamp = models.DateTimeField(auto_now_add=True)
#  server = models.CharField(max_length=80, blank=True, null=True)
#  running = models.BooleanField(default=False)
#  desired = models.BooleanField(default=False)
#  process_id = models.IntegerField(default=0, blank=True, null=True)


##############################
# JSON-encoded status message saved various servers
# class StatusUpdate(models.Model):
#  timestamp = models.DateTimeField(auto_now_add=True)
#  server = models.CharField(max_length=80, blank=True, null=True)
#  cruise = models.CharField(max_length=80, blank=True, null=True)
#  status = models.TextField(blank=True, null=True)
