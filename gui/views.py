import logging
import multiprocessing
import sys

from json import JSONDecodeError

from django.shortcuts import render
from django.http import HttpResponse

sys.path.append('.')

from .models import load_config_to_models
from .models import Logger, Config, Mode, Cruise
from .models import ConfigState, CruiseState, CurrentCruise

# Read in JSON with comments
from logger.utils.read_json import parse_json

from gui.settings import WEBSOCKET_STATUS_SERVER

from gui.django_run_loggers import LoggerServer

# A global pointing to the process running a DjangoLoggerRunner instance
logger_server = None
logger_server_proc = None

################################################################################
def index(request):
  global logger_server
  global logger_server_proc

  template_vars = {}
  template_vars['is_superuser'] = True
  template_vars['websocket_status_server'] = WEBSOCKET_STATUS_SERVER

  # We'll accumulate any errors we encounter here
  errors = []

  ############################
  # If we've gotten a POST request
  if request.method == 'POST':
    # Did we get a configuration file?
    if request.FILES.get('config_file', None):
      config_file = request.FILES['config_file']
      config_contents = config_file.read() 
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        config = parse_json(config_contents.decode('utf-8'))
        errors += load_config_to_models(config, config_file.name)
      except JSONDecodeError as e:
        errors.append(str(e))
        config = None

    # Did we get a mode selection?
    elif request.POST.get('select_mode', None):
      new_mode_name = request.POST['select_mode']
      logging.warning('switching to mode "%s"', new_mode_name)
      cruise = CurrentCruise.objects.latest('as_of').cruise      
      new_mode = Mode.objects.get(name=new_mode_name, cruise=cruise)
      current_mode = new_mode
      cruise.current_mode = new_mode
      cruise.save()

      # First, clear out desired state of all loggers so we can start
      # fresh. There is undoubtedly a clever way we can combine this
      # with the following loop, but for now, cleanliness is more
      # important than efficiency.
      for logger in Logger.objects.all():
        logger.desired_config = None
        logger.save()

      # Now update all the logger.current_config assignments to reflect
      # current mode.
      for config in Config.objects.filter(mode=new_mode):
        logger = config.logger
        logger.desired_config = config
        logger.save()
      
    # Did we get a server start/stop selection?
    elif request.POST.get('server', None):
      desired_server_state = request.POST.get('server')
      if desired_server_state == 'start':
        if logger_server:
          logging.warning('Got "start server" but server is non-empty!')
        if logger_server_proc and logger_server_proc.is_alive():
          logging.warning('Got "start server" but server is alive!')
          logger_server_proc.terminate()

        logging.warning('Starting LoggerServer')
        logger_server = LoggerServer()
        context = multiprocessing.get_context('fork')
        logger_server_proc = context.Process(name='LoggerServer',
                                             target=logger_server.start)
        logger_server_proc.start()

      elif desired_server_state == 'stop':
        if not logger_server:
          logging.warning('Got "stop server" but server is empty!')
        elif not logger_server_proc or not logger_server_proc.is_alive():
          logging.warning('Got "stop server" but server is not alive!')
        else:
          logging.info('Killing LoggerServer')
          logger_server_proc.terminate()

        # Regardless of whether things went bad, zero out server and proc
        logger_server = None
        logger_server_proc = None

      else:
        logging.error('Unknown desired server state: %s', desired_server_state)

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)
  
  try:
    cruise = CurrentCruise.objects.latest('as_of').cruise
    modes = Mode.objects.filter(cruise=cruise)
    current_mode = cruise.current_mode
    logging.warning('Current cruise: %s', cruise.id)
  except CurrentCruise.DoesNotExist:
    cruise = None
    modes = []
    current_mode = None
    logging.warning('No current cruise')

  # Get config corresponding to current mode for each logger
  loggers = {}
  for logger in Logger.objects.all():
    desired_config = logger.desired_config or None
    if logger.desired_config:
      logging.warning('config for %s is %s', logger.name, desired_config.name)
    else:
      logging.warning('no config for %s', logger.name)
    loggers[logger.name] = desired_config or None

  template_vars['cruise'] = cruise
  template_vars['modes'] = modes
  template_vars['current_mode'] = current_mode
  template_vars['loggers'] = loggers
  template_vars['server_running'] = logger_server is not None

  if errors:
    template_vars['errors'] = ', '.join(errors),

  # Render what we've ended up with
  return render(request, 'gui/index.html', template_vars)

################################################################################
def edit_config(request, logger_name):
  logger = Logger.objects.get(name=logger_name)
  
  ############################
  # If we've gotten a POST request
  if request.method == 'POST':
    config_id = request.POST['select_config']
    if not config_id:
      desired_config = None
      logging.warning('Selected null config for %s', logger_name)
    else:
      desired_config = Config.objects.get(id=config_id)
      logging.warning('Selected config "%s" for %s',
                      desired_config.name, logger_name)

      enabled_text = request.POST.get('enabled', None)
      if not enabled_text in ['enabled', 'disabled']:
        raise ValueError('Got bad "enabled" value: "%s"', enabled_text)
      enabled = enabled_text == 'enabled'
      desired_config.enabled = enabled
      desired_config.save()

    # Set the config to be its logger's desired_config
    logger.desired_config = desired_config
    logger.save()
    
    # Close window once we've done our processing
    return HttpResponse('<script>window.close()</script>')

  logger = Logger.objects.get(name=logger_name)
  all_configs = Config.objects.filter(logger=logger)
  logger_mode_config = get_logger_mode_config(logger)

  return render(request, 'gui/edit_config.html',
                {'logger': logger,
                 'logger_mode_config': logger_mode_config,
                 'all_configs': all_configs})

################################################################################
def load_config(request):
  # If not a POST, just draw the page
  if not request.method == 'POST':
    return render(request, 'gui/load_config.html', {})

  # If POST, we've expect there to be a file to process
  else:
    logging.warning('Got POST: %s', request.POST)
    errors = []

    # Did we get a configuration file?
    if request.FILES.get('config_file', None):

      config_file = request.FILES['config_file']
      config_contents = config_file.read() 
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        config = parse_json(config_contents.decode('utf-8'))
        errors += load_config_to_models(config, config_file.name)
      except JSONDecodeError as e:
        errors.append(str(e))

      # If no errors, close window - we're done.
      if not errors:
        return HttpResponse('<script>window.close()</script>')

    else:
      errors.append('No configuration file selected')

    # If here, there were errors
    return render(request, 'gui/load_config.html',
                  {'errors': ';'.join(errors)})

# By default, what config should logger have in current mode?
def get_logger_mode_config(logger):
  try:
    cruise = CurrentCruise.objects.latest('as_of').cruise
    mode = cruise.current_mode
    return Config.objects.get(logger=logger, mode=mode)
  except CurrentCruise.DoesNotExist:
    logging.warning('CurrentCruise does not exist')
    return None
  except Config.DoesNotExist:
    logging.warning('No config matching logger %s in mode %s', logger, mode)
    return None

