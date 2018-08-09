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

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CurrentCruise, CruiseState
from .models import LogMessage, ServerState

from server.logger_manager import LoggerManager

# Read in JSON with comments
from logger.utils.read_json import parse_json

from django_gui.settings import HOSTNAME, WEBSOCKET_SERVER

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
  user = request.user
  host = request.get_host()
  elements = ', '.join(['%s:%s' % (k,v) for k, v in request.POST.items()
                        if k not in ['csrfmiddlewaretoken']])
  if api:
    api.message_log(source='Django', user='(%s@%s)' % (user, host),
                    log_level=api.INFO, message='post: %s' % elements)
  
################################################################################
def index(request, cruise_id=None):
  """Home page - render logger states and cruise information.
  """
  global api
  if api is None:
    api = DjangoServerAPI()
   
  ############################
  # If we've gotten a POST request
  errors = []
  if request.method == 'POST':
    logging.warning('POST: %s', request.POST)
    
    # First things first: log the request
    log_request(request, (cruise_id or 'no_cruise') + ' index')

    # Did we get a cruise selection?
    if 'select_cruise' in request.POST:
      cruise_id = request.POST['select_cruise']
      logging.info('switching to cruise "%s"', cruise_id)

    # Are they deleting a cruise?(!)
    if 'delete_cruise' in request.POST:
      logging.info('deleting cruise "%s"', cruise_id)
      api.delete_cruise(request.POST['delete_cruise'])

    # Did we get a mode selection?
    elif 'select_mode' in request.POST:
      new_mode_name = request.POST['select_mode']
      logging.info('switching to mode "%s"', new_mode_name)
      api.set_mode(cruise_id, new_mode_name)

    # Did we get a cruise definition file? Load it and switch to the
    # cruise_id it defines.
    elif 'load_cruise' in request.POST and 'config_file' in request.FILES:
      config_file = request.FILES['config_file']
      config_contents = config_file.read() 
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        config = parse_json(config_contents.decode('utf-8'))
        api.load_cruise(config, config_file.name)
      except JSONDecodeError as e:
        errors.append('Error loading "%s": %s' % (config_file.name, str(e)))
      except ValueError as e:
        errors.append(str(e))

      # If there weren't any errors, switch to the cruise_id we've
      # just loaded.
      if not errors:
        cruise_id = config.get('cruise', {}).get('id', '')
        return HttpResponse(
          '<script>window.location.assign("/cruise/%s")</script>' % cruise_id)
      else:
        logging.warning('Errors! %s', errors)

    elif 'cancel' in request.POST:
      logging.warning('User canceled upload')

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)

  # Assemble information to draw page
  template_vars = {
    'cruise_id': cruise_id or '',
    'websocket_server': WEBSOCKET_SERVER,
    'cruise_list': api.get_cruises(),
    'errors': errors,
  }

  # If we have a cruise id, assemble loggers and other cruise-specific
  # info from API.
  if cruise_id:
    #template_vars['is_superuser'] = True
    template_vars['modes'] = api.get_modes(cruise_id)
    template_vars['current_mode'] = api.get_mode(cruise_id)

    # Get config corresponding to current mode for each logger
    loggers = {}
    for logger_id in api.get_loggers(cruise_id):
      logger_config = api.get_logger_config_name(cruise_id, logger_id)
      loggers[logger_id] = logger_config
      logging.warning('config for %s is %s', logger_id, logger_config)
    template_vars['loggers'] = loggers
    
  return render(request, 'django_gui/index.html', template_vars)

################################################################################
# Page to display messages from the specified server
def server_messages(request, log_level=logging.INFO, source=None):

  template_vars = {'websocket_server': WEBSOCKET_SERVER,
                   'log_level': log_level,
                   'log_levels': LOG_LEVELS,
                   'log_level_colors': LOG_LEVEL_COLORS,
                   'source': source}
  return render(request, 'django_gui/server_messages.html', template_vars)

################################################################################
def edit_config(request, cruise_id, logger_id):  
  global api
  if api is None:
    api = DjangoServerAPI()

  ############################
  # If we've gotten a POST request, they've selected a new config
  if request.method == 'POST':
    # First things first: log the request
    log_request(request, '%s:%s edit_config' % (cruise_id, logger_id))

    # Now figure out what they selected
    new_config = request.POST['select_config']
    logging.warning('selected config: %s', new_config)
    api.set_logger_config_name(cruise_id, logger_id, new_config)
    
    # Close window once we've done our processing
    return HttpResponse('<script>window.close()</script>')

  # What's our current mode? What's the default config for this logger
  # in this mode?
  config_options = api.get_logger_config_names(cruise_id, logger_id)
  current_config = api.get_logger_config_name(cruise_id, logger_id)
  current_mode = api.get_mode(cruise_id)
  default_config = api.get_logger_config_name(cruise_id, logger_id,
                                              current_mode)
  return render(request, 'django_gui/edit_config.html',
                {'cruise_id': cruise_id,
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
    'websocket_server': WEBSOCKET_SERVER,
  }

  # Render what we've ended up with
  return render(request, 'django_gui/widget.html', template_vars)
