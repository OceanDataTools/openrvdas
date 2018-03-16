import json
import logging

from django.db import models

# Insight: don't try to represent components of individual loggers in
# Model - just cruise/mode/config, and store config as JSON string:

# NOTE: add strings as names for fields?

##############################
class Logger(models.Model):
  name = models.CharField(max_length=256, blank=True)
  cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE,
                             blank=True, null=True)
  desired_config = models.ForeignKey('LoggerConfig', on_delete=models.CASCADE,
                                     related_name="desired_config",
                                     blank=True, null=True)
  current_config = models.ForeignKey('LoggerConfig', on_delete=models.CASCADE,
                                     related_name="current_config",
                                     blank=True, null=True)
  def __str__(self):
    return self.name
   
##############################
class LoggerConfig(models.Model):
  name = models.CharField(max_length=256, blank=True)
  logger = models.ForeignKey('Logger', on_delete=models.CASCADE,
                             blank=True, null=True)
  mode = models.ForeignKey('Mode', on_delete=models.CASCADE,
                           blank=True, null=True)
  config_json = models.TextField('configuration string')

  # If this config is disabled, don't run it, even when mode
  # is selected.
  enabled = models.BooleanField(default=True)

  def __str__(self):
    return '%s (%s)' % (self.name, self.mode)

##############################
class Mode(models.Model):
  name = models.CharField(max_length=256, blank=True)
  cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE,
                             blank=True, null=True)
  def __str__(self):
    return self.name
  
##############################
class Cruise(models.Model):
  id = models.CharField(max_length=256, primary_key=True)
  start = models.DateTimeField(blank=True, null=True)
  end = models.DateTimeField(blank=True, null=True)

  # The file this cruise configuration has been loaded from
  config_filename = models.CharField(max_length=256, blank=True, null=True)
  config_text = models.TextField(blank=True, null=True)
  loaded_time = models.DateTimeField(auto_now_add=True, null=True)

  current_mode = models.ForeignKey('Mode', on_delete=models.SET_NULL,
                                   blank=True, null=True,
                                   related_name='cruise_current_mode')
  default_mode = models.ForeignKey('Mode', on_delete=models.SET_NULL,
                                   blank=True, null=True,
                                   related_name='cruise_default_mode')
  def modes(self):
    return Mode.objects.filter(cruise=self)

  def __str__(self):
    return self.id
  
##############################
# Which is our current cruise? Since when?
class CurrentCruise(models.Model):
  cruise = models.ForeignKey('Cruise', on_delete=models.SET_NULL,
                             blank=True, null=True)
  as_of = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return self.cruise.id

##############################
# What mode is cruise in? Since when?
class CruiseState(models.Model):
  cruise = models.ForeignKey('Cruise', on_delete=models.CASCADE)
  current_mode = models.ForeignKey('Mode', on_delete=models.CASCADE)
  started = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return '%s: %s' % (self.cruise, self.mode)

##############################
# Do we want this logger_config running? Is it? If so, since when, and
# what's its pid?  If run state doesn't align with current mode, then
# highlight in interface
class LoggerConfigState(models.Model):
  config = models.ForeignKey('LoggerConfig', on_delete=models.CASCADE)
  running = models.BooleanField(default=False)
  desired = models.BooleanField(default=False)
  process_id = models.IntegerField(default=0, blank=True)
  timestamp = models.DateTimeField(auto_now_add=True)
  errors = models.TextField(blank=True, null=True)

##############################
# Which servers are running, and when?
# If run state doesn't align with current mode, then highlight in interface
class ServerState(models.Model):
  timestamp = models.DateTimeField(auto_now_add=True)
  server = models.CharField(max_length=80, blank=True, null=True)
  running = models.BooleanField(default=False)
  desired = models.BooleanField(default=False)
  process_id = models.IntegerField(default=0, blank=True, null=True)

##############################
# Messages that our servers log
class ServerMessage(models.Model):
  server = models.CharField(max_length=80, blank=True, null=True)
  message = models.TextField(blank=True, null=True)
  timestamp = models.DateTimeField(auto_now_add=True)

##############################
# JSON-encoded status message saved various servers
class StatusUpdate(models.Model):
  timestamp = models.DateTimeField(auto_now_add=True)
  server = models.CharField(max_length=80, blank=True, null=True)
  cruise = models.CharField(max_length=80, blank=True, null=True)
  status = models.TextField(blank=True, null=True)


################################################################################
def load_cruise_config_to_models(config, config_filename='none'):
  errors = []
  
  # Load cruise info. In theory, we're okay with there not being a
  # cruise definition, though as yet unsure how that would play out in
  # the models.
  cruise_model = None
  cruise = config.get('cruise', {})
  if cruise:
    cruise_id = cruise.get('id', '--no name--')
    cruise_start = cruise.get('start', '')
    cruise_end = cruise.get('end', '')
  else:
    cruise_id = '--no name--'
    cruise_start = None
    cruise_end = None

  # If the cruise already exists, delete it (and all modes/configs
  # that point to it) before creating the new one. Save the filename
  # and the config source that we've been handed.
  try:
    cruise_model = Cruise.objects.get(id=cruise_id)
    logging.info('Deleting old cruise models for %s', cruise_id)
    cruise_model.delete()
  except Cruise.DoesNotExist:
    pass

  # Now create the new cruise model
  cruise_model = Cruise(id=cruise_id, start=cruise_start, end=cruise_end,
                        config_filename=config_filename,
                        config_text=json.dumps(config, indent=2,sort_keys=True))
  cruise_model.save()

  # Flag it as our current cruise
  current_cruise_model = CurrentCruise(cruise=cruise_model)
  current_cruise_model.save()
  
  # Load info about modes
  modes = config.get('modes', {})
  if modes:
    for mode_name, loggers in modes.items():
      logging.info('  loading mode "%s"', mode_name)
      mode_model = Mode(name=mode_name, cruise=cruise_model)
      mode_model.save()

      for logger_name, logger_config in loggers.items():
        logging.info('    loading logger "%s"', logger_name)
        logger_model, _  = Logger.objects.get_or_create(name=logger_name,
                                                        cruise=cruise_model)

        config_json = json.dumps(logger_config, indent=2, sort_keys=True)
        config_model = LoggerConfig(name=logger_config.get('name', 'no_name'),
                                    logger=logger_model,
                                    mode=mode_model,
                                    config_json=config_json)
        config_model.save()

  # Do we have a default mode?
  default_mode = config.get('default_mode', {})
  if default_mode:
    try:
      default_mode_model = Mode.objects.get(name=default_mode,
                                            cruise=cruise_model)
      cruise_model.default_mode = default_mode_model
      cruise_model.current_mode = default_mode_model
      cruise_model.save()
    except Mode.DoesNotExist:
      load_error = 'Specified default mode "%s" does not exist' % default_mode
      logging.error(load_error)
      errors.append(load_error)

  return errors
