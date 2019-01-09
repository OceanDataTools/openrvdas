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

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CurrentCruise, CruiseState
from .models import LogMessage, ServerState

from server.logger_manager import LoggerManager

# Read in JSON with comments
from logger.utils.read_config import parse

from django_gui.settings import HOSTNAME
from django_gui.settings import WEBSOCKET_STATUS_SERVER, WEBSOCKET_DATA_SERVER

# Convenience dicts we pass to the server_message page to
# translate logging levels to names and colors.
LOG_LEVELS = {
  0:  'ALL',
  10: 'DEBUG',
  20: 'INFO',
  30: 'WARNING',
  40: 'ERROR',
  50: 'CRITICAL'
}

LOG_LEVEL_COLORS = {
  0:  '',
  10: '',
  20: '',
  30: '#FFFF99',
  40: '#FF9999',
  50: '#FF6666'
}

############################
# We're going to interact with the Django DB via its API class
from .django_server_api import DjangoServerAPI
api = None

def log_request(request, cmd):
  global api
  if api:
    user = request.user
    host = request.get_host()
    elements = ', '.join(['%s:%s' % (k,v) for k, v in request.POST.items()
                          if k not in ['csrfmiddlewaretoken', 'cruise_id']])
    api.message_log(source='Django', user='(%s@%s)' % (user, host),
                    log_level=api.INFO, message=elements)

################################################################################
def index(request):
  """Home page - render logger states and cruise information.
  """
  global api
  if api is None:
    api = DjangoServerAPI()

  ############################
  # If we've gotten a POST request
  cruise_id = ''
  errors = []
  if request.method == 'POST':
    logging.debug('POST: %s', request.POST)

    # First things first: log the request
    log_request(request, 'index')

    # Are they deleting a cruise?(!)
    if 'delete_cruise' in request.POST:
      logging.info('deleting cruise')
      api.delete_cruise()

    # Did we get a mode selection?
    elif 'select_mode' in request.POST:
      new_mode_name = request.POST['select_mode']
      logging.info('switching to mode "%s"', new_mode_name)
      api.set_active_mode(new_mode_name)

    # Did we get a cruise definition file? Load it and switch to the
    # configuration it defines.
    elif 'load_config' in request.POST and 'config_file' in request.FILES:
      config_file = request.FILES['config_file']
      config_contents = config_file.read()
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        configuration = parse(config_contents.decode('utf-8'))
        api.load_configuration(configuration)
      except JSONDecodeError as e:
        errors.append('Error loading "%s": %s' % (config_file.name, str(e)))
      except ValueError as e:
        errors.append(str(e))

      # If there weren't any errors, switch to the configuration we've
      # just loaded.
      if errors:
        logging.warning('Errors! %s', errors)

    elif 'cancel' in request.POST:
      logging.warning('User canceled upload')

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)

  # Assemble information to draw page
  template_vars = {
    'cruise_id': cruise_id or '',
    'websocket_server': WEBSOCKET_STATUS_SERVER,
    'errors': errors,
    'loggers': {},
  }

  # If we have a cruise id, assemble loggers and other cruise-specific
  # info from API.
  #template_vars['is_superuser'] = True
  try:
    template_vars['modes'] = api.get_modes()
    template_vars['current_mode'] = api.get_active_mode()

    # Get config corresponding to current mode for each logger

    # REPLACE WITH?
    #template_vars['loggers'] = api.get_logger_configs()
    for logger_id in api.get_loggers():
      logger_config = api.get_logger_config_name(logger_id)
      template_vars['loggers'][logger_id] = logger_config
      logging.warning('config for %s is %s', logger_id, logger_config)
  except ValueError:
    logging.info('No configuration loaded')

  return render(request, 'django_gui/index.html', template_vars)

################################################################################
# Page to display messages from the specified server
#def server_messages(request, log_level=logging.INFO,
#                    cruise_id=None, source=None):
def server_messages(request, path):
  global api
  if api is None:
    api = DjangoServerAPI()

  path_pieces = path.split('/')
  log_level = path_pieces[0] if len(path_pieces) > 0 else logging.INFO
  source = path_pieces[1] if len(path_pieces) > 1 else None

  template_vars = {'websocket_server': WEBSOCKET_STATUS_SERVER,
                   'log_level': int(log_level),
                   'log_levels': LOG_LEVELS,
                   'log_level_colors': LOG_LEVEL_COLORS,
                   'source': source}
  return render(request, 'django_gui/server_messages.html', template_vars)

################################################################################
def edit_config(request, logger_id):
  global api
  if api is None:
    api = DjangoServerAPI()

  ############################
  # If we've gotten a POST request, they've selected a new config
  if request.method == 'POST':
    # First things first: log the request
    log_request(request, '%s edit_config' % logger_id)

    # Now figure out what they selected
    new_config = request.POST['select_config']
    logging.warning('selected config: %s', new_config)
    api.set_active_logger_config(logger_id, new_config)

    # Close window once we've done our processing
    return HttpResponse('<script>window.close()</script>')

  # What's our current mode? What's the default config for this logger
  # in this mode?
  config_options = api.get_logger_config_names(logger_id)
  current_config = api.get_logger_config_name(logger_id)
  current_mode = api.get_active_mode()
  default_config = api.get_logger_config_name(logger_id, current_mode)
  return render(request, 'django_gui/edit_config.html',
                {
                  'logger_id': logger_id,
                  'current_config': current_config,
                  'default_config': default_config,
                  'config_options': config_options
                })

################################################################################
def widget(request, field_list=''):
  global logger_server

  template_vars = {
    'field_list': field_list,
    'is_superuser': True,
    'websocket_data_server': WEBSOCKET_DATA_SERVER,
  }

  # Render what we've ended up with
  return render(request, 'django_gui/widget.html', template_vars)
