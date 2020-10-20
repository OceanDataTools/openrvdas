from django.contrib.auth import authenticate, login
from .django_server_api import DjangoServerAPI
from django_gui.settings import FILECHOOSER_DIRS
from django_gui.settings import WEBSOCKET_DATA_SERVER
import json
import logging
import sys

from json import JSONDecodeError
from os import listdir
from os.path import dirname, realpath, isfile, isdir, abspath
from yaml.scanner import ScannerError

from django.shortcuts import render, redirect
from django.http import HttpResponse

sys.path.append(dirname(dirname(realpath(__file__))))

# Read in JSON with comments
from logger.utils.read_config import parse, read_config  # noqa: E402


############################
# We're going to interact with the Django DB via its API class
api = None


def login_user(request):
    template_vars = {}
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            if not username:
                template_vars['empty_username'] = 'Please enter username'
            elif not password:
                template_vars['empty_password'] = 'Please enter password'
            elif user is None:
                template_vars['invalid'] = 'Username and password do not match'

    return render(request, 'django_gui/login_user.html', template_vars)


def log_request(request, cmd):
    global api
    if api:
        user = request.user
        host = request.get_host()
        elements = ', '.join(['%s:%s' % (k, v) for k, v in request.POST.items()
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
    # cruise_id = ''
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

        elif 'reload_button' in request.POST:
            logging.info('reloading current configuration file')
            try:
                cruise = api.get_configuration()
                filename = cruise['config_filename']

                # Load the file to memory and parse to a dict. Add the name
                # of the file we've just loaded to the dict.
                config = read_config(filename)
                if 'cruise' in config:
                    config['cruise']['config_filename'] = filename
                api.load_configuration(config)
            except ValueError as e:
                logging.warning('Error reloading current configuration: %s', str(e))

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
        configuration = api.get_configuration()
        template_vars['cruise_id'] = configuration.get('id', 'Cruise')
        template_vars['filename'] = configuration.get('config_filename', '-none-')
        template_vars['loggers'] = api.get_loggers()
        template_vars['modes'] = api.get_modes()
        template_vars['active_mode'] = api.get_active_mode()
        template_vars['errors'] = errors
    except (ValueError, AttributeError):
        logging.info('No configuration loaded')

    return render(request, 'django_gui/index.html', template_vars)


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
def edit_config(request, logger_id):
    global api
    if api is None:
        api = DjangoServerAPI()

    ############################
    # If we've gotten a POST request, they've selected a new config
    if request.method == 'POST':

        # If they've hit the "Save" button
        if 'save' in request.POST:
            # First things first: log the request
            log_request(request, '%s edit_config' % logger_id)

            # Now figure out what they selected
            new_config = request.POST['select_config']
            logging.warning('selected config: %s', new_config)
            api.set_active_logger_config(logger_id, new_config)

        else:
            logging.debug('User canceled request')

        # Close window once we've done our processing
        return HttpResponse('<script>window.close()</script>')

    # If not a POST, render the selector page:
    # What's our current mode? What's the default config for this logger
    # in this mode?
    active_mode = api.get_active_mode()
    config_options = api.get_logger_config_names(logger_id)
    default_config = api.get_logger_config_name(logger_id, active_mode)
    current_config = api.get_logger_config_name(logger_id)

    # dict of config_name: config_json
    config_map = {config_name: api.get_logger_config(config_name)
                  for config_name in config_options}

    return render(request, 'django_gui/edit_config.html',
                  {
                      'logger_id': logger_id,
                      'current_config': current_config,
                      'config_map': json.dumps(config_map),
                      'default_config': default_config,
                      'config_options': config_options
                  })


################################################################################
def choose_file(request, selection=None):
    """Render a chooser to pick and load a configuration file from the
    server side.

    Files can be navigated/selected starting at a base defined by the list in
    django_gui.settings.FILECHOOSER_DIRS.
    """
    global api
    if api is None:
        api = DjangoServerAPI()

    ##################
    # Internal function to create listing from dirname
    def get_dir_contents(dir_name):
        # If at root, set empty selection, otherwise, allow to pop back up a level
        contents = {'..': '' if abspath(dir_name) in FILECHOOSER_DIRS
                    else abspath(dir_name + '/..')}
        for filename in listdir(dir_name):
            path = dir_name + '/' + filename
            if isdir(path):
                filename += '/'
            contents[filename] = abspath(path)
        return contents

    ##################
    # Start of choose_file() code
    target_file = None  # file we're going to load
    load_errors = []    # where we store any errors

    # If post, figure out what user selected
    if request.method == 'POST':
        dir_name = request.POST.get('dir_name', None)
        selection = [request.POST.get('select_file', '')]

        # Was this a request to load the target file?
        target_file = request.POST.get('target_file', None)
        if target_file:
            try:
                # Load the file to memory and parse to a dict. Add the name of
                # the file we've just loaded to the dict.
                with open(target_file, 'r') as config_file:
                    configuration = parse(config_file.read())
                    if 'cruise' in configuration:
                        configuration['cruise']['config_filename'] = target_file

                    # Load the config and set to the default mode
                    api.load_configuration(configuration)
                    default_mode = api.get_default_mode()
                    if default_mode:
                        api.set_active_mode(default_mode)
            except (JSONDecodeError, ScannerError) as e:
                load_errors.append('Error loading "%s": %s' % (target_file, str(e)))
            except ValueError as e:
                load_errors.append(str(e))

            # If no errors, go home; otherwise reset back to previous page
            if not load_errors:
                return HttpResponse('<script>window.close()</script>')
            else:
                logging.warning('Errors loading cruise definition: %s', load_errors)
                target_file = None

        # Okay, it wasn't a request to load a target file. Do we have a
        # selection? If no target and no selection, it means they canceled
        # the choice.
        elif selection is None or selection[0] is None:
            return HttpResponse('<script>window.close()</script>')

    # If we don't have a selection, use the complete listing from our settings.
    if not selection or selection == ['']:
        logging.debug('No selection, so setting up with: %s', FILECHOOSER_DIRS)
        dir_name = ''
        selection = FILECHOOSER_DIRS

    # Here, we should have a selection of *some* sort. Figure out how to
    # display it: if a single element and a directory, expand the
    # directory. If single element and a file, it's our target file. If
    # multiple elements, just display list of elements.
    if len(selection) == 1:
        # If it's a file, designate it as the target_file; we won't bother
        # with a listing.
        if isfile(selection[0]):
            target_file = selection[0]
            listing = []

        # If it's a directory, fetch/expand its contents into the listing
        else:
            dir_name = selection[0]
            listing = get_dir_contents(dir_name)

    # If here, 'selection' is a list of files/dirs; use them as our listing
    else:
        # If selection includes one of our top dirs, use the complete
        # listing from our settings.
        if set(selection).intersection(FILECHOOSER_DIRS):
            dir_name = ''
            selection = FILECHOOSER_DIRS
        listing = {f.split('/')[-1]: f for f in selection}

    # Render the page
    return render(request, 'django_gui/choose_file.html',
                  {'target_file': target_file,
                   'dir_name': dir_name,
                   'listing': listing,
                   'load_errors': load_errors})


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


################################################################################
def fields(request):
    global logger_server

    template_vars = {
        'websocket_server': WEBSOCKET_DATA_SERVER,
    }

    # Render what we've ended up with
    return render(request, 'django_gui/fields.html', template_vars)
