import logging
import sys

from json import JSONDecodeError

from django.shortcuts import render
from django.http import HttpResponse

#from django.conf import settings

sys.path.append('.')

from .models import load_config_to_models
from .models import Logger, Config, Mode, Cruise
from .models import ConfigState, CruiseState, CurrentCruise

# Read in JSON with comments
from logger.utils.read_json import parse_json

from gui.settings import WEBSOCKET_STATUS_SERVER

################################################################################
def index(request):

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
    try:
      config = Config.objects.get(logger=logger, mode=current_mode)
      logging.warning('config for %s is %s', logger.name, config.name)
    except Config.DoesNotExist:
      config = None
      logging.warning('no config for %s', logger.name)
      
    loggers[logger.name] = config

  template_vars['cruise'] = cruise
  template_vars['modes'] = modes
  template_vars['current_mode'] = current_mode
  template_vars['loggers'] = loggers
  
  if errors:
    template_vars['errors'] = ', '.join(errors),

  # Render what we've ended up with
  return render(request, 'manager/index.html', template_vars)

################################################################################
def edit_config(request, config_id):

  ############################
  # If we've gotten a POST request
  if request.method == 'POST':
    logging.warning('Got POST: %s', request.POST)
    config_id = request.POST.get('config_id', None)
    config = Config.objects.get(pk=config_id)
     
    enabled_text = request.POST.get('enabled', None)
    if not enabled_text in ['enabled', 'disabled']:
      raise ValueError('Got bad "enabled" value: "%s"', enabled_text)
    enabled = enabled_text == 'enabled'

    config.enabled = enabled
    config.save()
     
    # Close window once we've done our processing
    return HttpResponse('<script>window.close()</script>')

  try:
    config = Config.objects.get(pk=config_id)
  except Config.DoesNotExist:
    return HttpResponse('No config with id %s' % config_id)

  return render(request, 'manager/edit_config.html', {'config': config})

################################################################################
def load_config(request):

  # If not a POST, just draw the page
  if not request.method == 'POST':
    return render(request, 'manager/load_config.html', {})

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
    return render(request, 'manager/load_config.html',
                  {'errors': ';'.join(errors)})

  
