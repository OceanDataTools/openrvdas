import json
import logging
import multiprocessing
import os
import sys
import threading
import time

from json import JSONDecodeError
from signal import SIGTERM, SIGINT

from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

sys.path.append('.')

from .models import load_cruise_config_to_models
from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CruiseState, CurrentCruise
from .models import ServerMessage, ServerState

from gui.run_servers import ServerRunner

# Read in JSON with comments
from logger.utils.read_json import parse_json

from gui.settings import WEBSOCKET_SERVER, WEBSOCKET_SERVER

############################
def get_server_state(server):
  """Retrieve latest state for specified server name. If none exists,
  create (but do not save) a new default one."""
  try:
    return ServerState.objects.filter(server=server).latest('timestamp')
  except ServerState.DoesNotExist:
    return ServerState(server=server, running=False, desired=False)

################################################################################
def index(request):

  # We'll accumulate any errors we encounter here
  errors = []

  ############################
  # If we've gotten a POST request
  if request.method == 'POST':
    logging.warning('REQUEST: %s', request.POST)

    # Did we get a configuration file?
    if request.FILES.get('config_file', None):
      config_file = request.FILES['config_file']
      config_contents = config_file.read() 
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        config = parse_json(config_contents.decode('utf-8'))
        errors += load_cruise_config_to_models(config, config_file.name)
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

      # Find the config that matches the new mode for each logger. If
      # no config for a logger, that means the logger isn't supposed
      # to be running in this mode. 
      for logger in Logger.objects.filter(cruise=cruise):
        config_set = LoggerConfig.objects.filter(logger=logger, mode=new_mode)
        config_set_size = config_set.count()
        if config_set_size == 0:
          desired_config = None
        elif config_set_size == 1:
          desired_config = config_set.first()
        else:
          desired_config = None
          logging.error('Multiple matching configs for logger %s, mode %s',
                        logger.name, new_mode_name)

        logger.desired_config = desired_config
        logger.save()
        #LoggerConfigState(config=desired_config, desired=true).save()

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)

  # Now assemble the information needed to display the page.
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
  for logger in Logger.objects.filter(cruise=cruise):
    desired_config = logger.desired_config or None
    if logger.desired_config:
      logging.warning('config for %s is %s', logger.name, desired_config.name)
    else:
      logging.warning('no config for %s', logger.name)
    loggers[logger.name] = desired_config or None

  template_vars = {
    'is_superuser': True,
    'websocket_server': WEBSOCKET_SERVER,
    'cruise': cruise,
    'modes': modes,
    'current_mode': current_mode,
    'loggers': loggers,
    'status_server_running': get_server_state('StatusServer').running,
    'logger_server_running': get_server_state('LoggerServer').running,
    'errors': ', '.join(errors),
  }

  # Render what we've ended up with
  return render(request, 'gui/index.html', template_vars)

################################################################################
run_servers_object = None
run_servers_process = None

################################################################################
# To start/stop/monitor servers

# NOTE: Starting/stopping the ServerRunner process (gui/run_servers.py)
# is not yet working. You'll need to start/stop it manually for now.

def servers(request):
  global run_servers_object, run_servers_process

  # If we've gotten a POST request, check for new desired_state
  if request.method == 'POST':
    if request.POST.get('start', None):
      # Start the run_servers process
      logging.warning('Starting servers')
      if run_servers_object:
        logging.warning('Killing existing run_servers process')
        run_servers_object.quit()
      #run_servers_object = ServerRunner()
      #multiprocessing.set_start_method('spawn')
      #run_servers_process = \
      #    multiprocessing.Process(target=run_servers_object.start)
      #run_servers_process.start()

    if request.POST.get('stop', None):
      # Stop any run_servers process
      logging.warning('Stopping servers')
      if run_servers_object:
        logging.warning('Asking StatusServer and LoggerServer to shut down')
        ServerState(server='StatusServer', running=True, desired=False).save()
        ServerState(server='LoggerServer', running=True, desired=False).save()
        time.sleep(1)
        logging.warning('Killing existing run_servers process')
        #run_servers_process.terminate()

  template_vars = {'websocket_server': WEBSOCKET_SERVER}

  # Render what we've ended up with
  return render(request, 'gui/servers.html', template_vars)

################################################################################
# Page to display messages from the specified server
def server_messages(request, server):
  template_vars = {'websocket_server': WEBSOCKET_SERVER, 'server': server}
  return render(request, 'gui/server_messages.html', template_vars)

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
      desired_config = LoggerConfig.objects.get(id=config_id)
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
  all_configs = LoggerConfig.objects.filter(logger=logger)
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
        errors += load_cruise_config_to_models(config, config_file.name)
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

################################################################################
# By default, what config should logger have in current mode?
def get_logger_mode_config(logger):
  try:
    cruise = CurrentCruise.objects.latest('as_of').cruise
    mode = cruise.current_mode
    return LoggerConfig.objects.get(logger=logger, mode=mode)
  except CurrentCruise.DoesNotExist:
    logging.warning('CurrentCruise does not exist')
    return None
  except LoggerConfig.DoesNotExist:
    logging.warning('No config matching logger %s in mode %s', logger, mode)
    return None

################################################################################
def widget(request, field_list=''):
  global logger_server

  template_vars = {
    'field_list': field_list,
    'is_superuser': True,
    'websocket_server': WEBSOCKET_SERVER,
  }

  # Render what we've ended up with
  return render(request, 'gui/widget.html', template_vars)
