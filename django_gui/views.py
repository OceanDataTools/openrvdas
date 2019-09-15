import json
import logging
import multiprocessing
import os
import sys
import threading
import time

from json import JSONDecodeError
from signal import SIGTERM, SIGINT

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

from server.logger_manager import LoggerManager

# Read in JSON with comments
from logger.utils.read_config import parse

from django_gui.settings import HOSTNAME, STATIC_ROOT
from django_gui.settings import WEBSOCKET_DATA_SERVER

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
      try:
        api.set_active_mode(new_mode_name)
      except ValueError as e:
        logging.warning('Error trying to set mode to "%s": %s',
                        new_mode_name, str(e))

    # Did we get a cruise definition file? Load it. If there aren't
    # any errors, switch to the configuration it defines.
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
      if errors:
        logging.warning('Errors! %s', errors)

    # If they canceled the upload
    elif 'cancel' in request.POST:
      logging.warning('User canceled upload')

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)

  # Assemble information to draw page
  template_vars = {
    'websocket_server': WEBSOCKET_DATA_SERVER,
    'errors': {'django': errors},
  }
  try:
    template_vars['cruise_id'] = api.get_configuration().id
    template_vars['loggers'] = api.get_loggers()
    template_vars['modes'] = api.get_modes()
    template_vars['active_mode'] = api.get_active_mode()
    template_vars['errors'] = errors
  except ValueError:
    logging.info('No configuration loaded')
  
  return render(request, 'django_gui/index.html', template_vars)

################################################################################
# Page to display messages from the openrvdas server
def display(request, page_path=None):
  if not page_path:
    # Ideally this would provide the listing using the display/ url
    # but there are many higher priorities at this point.
    return redirect('/static/widgets')
  
  with open(STATIC_ROOT + '/html/' + page_path) as f:
    page_content = f.read()
    return HttpResponse(page_content)

################################################################################
# Page to display messages from the openrvdas server
def server_messages(request, log_level=logging.INFO):
  global api
  if api is None:
    api = DjangoServerAPI()

  template_vars = {'websocket_server': WEBSOCKET_DATA_SERVER,
                   'log_level': int(log_level)}
  return render(request, 'django_gui/server_messages.html', template_vars)

################################################################################
# Some hacks so that the display pages can find their JS and CSS
def js(request, js_path=None):
  with open(STATIC_ROOT + '/js/' + js_path) as f:
    page_content = f.read()
    return HttpResponse(page_content)

def css(request, css_path=None):
  with open(STATIC_ROOT + '/css/' + css_path) as f:
    page_content = f.read()
    return HttpResponse(page_content)

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
    'field_list_string': field_list,
    'field_list': field_list.split(',') if field_list else [],
    'is_superuser': True,
    'websocket_server': WEBSOCKET_DATA_SERVER,
  }

  # Render what we've ended up with
  return render(request, 'django_gui/widget.html', template_vars)
