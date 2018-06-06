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

############################
# We're going to interact with the Django DB via its API class
from .django_server_api import DjangoServerAPI
api = DjangoServerAPI()

def log_request(request, cmd):
  global api
  user = request.user
  host = request.get_host()
  elements = ', '.join(['%s:%s' % (k,v) for k, v in request.POST.items()
                        if k not in ['csrfmiddlewaretoken']])
  api.message_log(source='Django', user='(%s@%s)' % (user, host),
                  log_level=api.INFO, message='post: %s' % elements)
  
################################################################################
def index(request, cruise_id=None):
  """Home page - render logger states and cruise information.
  """
  if not cruise_id:
    template_vars = {
      'websocket_server': WEBSOCKET_SERVER,
      'cruise': None,
      'cruise_list': api.get_cruises(),
      'errors': '',
    }
    return render(request, 'django_gui/index.html', template_vars)
   
  ############################
  # If we've gotten a POST request
  if request.method == 'POST':
    # First things first: log the request
    log_request(request, cruise_id + ' index')

    # Did we get a cruise selection?
    if request.POST.get('select_cruise', None):
      cruise_id = request.POST['select_cruise']
      logging.info('switching to cruise "%s"', cruise_id)

    # Are they deleting a cruise?(!)
    if request.POST.get('delete_cruise', None):
      logging.info('deleting cruise "%s"', cruise_id)
      api.delete_cruise(request.POST['delete_cruise'])

    # Did we get a mode selection?
    elif request.POST.get('select_mode', None):
      new_mode_name = request.POST['select_mode']
      logging.info('switching to mode "%s"', new_mode_name)
      api.set_mode(cruise_id, new_mode_name)

    # Else unknown post
    else:
      logging.warning('Unknown POST request: %s', request.POST)

  # Now assemble the information needed to display the page.
  cruise_list = api.get_cruises()
  modes = api.get_modes(cruise_id)
  current_mode = api.get_mode(cruise_id)

  # Get config corresponding to current mode for each logger
  loggers = {}
  for logger_id in api.get_loggers(cruise_id):
    logger_config = api.get_logger_config_name(cruise_id, logger_id)
    loggers[logger_id] = logger_config
    logging.warning('config for %s is %s', logger_id, logger_config)

  template_vars = {
    'is_superuser': True,
    'websocket_server': WEBSOCKET_SERVER,
    'cruise_id': cruise_id,
    'cruise_list': cruise_list,
    'modes': modes,
    'current_mode': current_mode,
    'loggers': loggers,
    #'status_server_running': get_server_state('StatusServer').running,
    #'logger_server_running': get_server_state('LoggerServer').running,
    'errors': '',
  }
  return render(request, 'django_gui/index.html', template_vars)

################################################################################
run_servers_object = None
run_servers_process = None

################################################################################
# To start/stop/monitor servers

# NOTE: Starting/stopping the ServerRunner process (django_gui/run_servers.py)
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
  return render(request, 'django_gui/servers.html', template_vars)

################################################################################
# Page to display messages from the specified server
def server_messages(request, log_level=logging.INFO, source=None):
  template_vars = {'websocket_server': WEBSOCKET_SERVER,
                   'log_level': log_level,
                   'source': source}
  logging.warning('ll: %s, source: %s', log_level, source)
  return render(request, 'django_gui/server_messages.html', template_vars)

################################################################################
def edit_config(request, cruise_id, logger_id):  
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
def load_cruise_config(request):
  # If not a POST, just draw the page
  if not request.method == 'POST':
    return render(request, 'django_gui/load_cruise_config.html', {})

  # If POST, we've expect there to be a file to process
  else:
    errors = []

    # Did we get a configuration file?
    if request.FILES.get('config_file', None):
      config_file = request.FILES['config_file']
      config_contents = config_file.read() 
      logging.warning('Uploading file "%s"...', config_file.name)

      try:
        config = parse_json(config_contents.decode('utf-8'))
        api.load_cruise(config, config_file.name)
      except JSONDecodeError as e:
        errors.append(str(e))
      except ValueError as e:
        errors.append(str(e))

      # If no errors, close window - we're done.
      if not errors:
        return HttpResponse('<script>window.close()</script>')

    else:
      errors.append('No configuration file selected')

    # If here, there were errors
    return render(request, 'django_gui/load_cruise_config.html',
                  {'errors': ';'.join(errors)})

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
