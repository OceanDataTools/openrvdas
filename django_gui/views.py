from django.contrib import auth
from .django_server_api import DjangoServerAPI
from django_gui.settings import FILECHOOSER_DIRS
from django_gui.settings import WEBSOCKET_DATA_SERVER
import logging
import yaml

from os import listdir
from os.path import dirname, isfile, isdir, abspath, relpath

from django.shortcuts import render, redirect
from django.http import HttpResponse


# Read in JSON with comments
from logger.utils.read_config import read_config, expand_cruise_definition  # noqa: E402


############################
# We're going to interact with the Django DB via its API class
api = None


################################################################################
def load_cruise_definition(filename, preserve_mode=False):
    """Read the cruise definition in the named file and, if it is valid,
    load it. Return a list of error messages, which will be empty if the
    definition was loaded. If the list is not empty, the definition was
    not loaded, and whatever definition was previously loaded (if any) is
    still in effect.

    filename       Path of the cruise definition file to load.

    preserve_mode  If False, switch to the definition's default mode. If
                   True (which is what we want when reloading a definition
                   whose file has changed), keep any unchanged loggers
                   running and don't revert to the default mode.
    """
    global api
    if api is None:
        api = DjangoServerAPI()

    errors = []
    try:
        # Load the file to memory and parse to a dict. Passing in "errors"
        # gets us the reason if the file can't be read or parsed, and gets
        # us all of the problems in the definition, rather than just the
        # first one.
        config = read_config(filename, errors=errors)
        if not errors:
            config = expand_cruise_definition(config, errors=errors)
        if errors:
            return errors

        # Add the name of the file we've just loaded to the dict.
        if 'cruise' in config:
            config['cruise']['config_filename'] = filename

        # Signal that we want to preserve the mode by slipping some side
        # information into the config.
        if preserve_mode:
            config['preserve_mode'] = True

        api.load_configuration(config)

        if not preserve_mode:
            default_mode = api.get_default_mode()
            if default_mode:
                api.set_active_mode(default_mode)

    except ValueError as e:
        errors.append(str(e))

    # We don't know what else a malformed definition might provoke, but
    # whatever it is, we want the user to see it.
    except Exception as e:
        logging.exception('Unexpected error loading cruise definition "%s"', filename)
        errors.append('Unexpected error (%s): %s' % (type(e).__name__, str(e)))

    return errors


def login(request):
    template_vars = {}
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(request, username=username, password=password)
        if user is not None:
            auth.login(request, user)
            return redirect('/')
        else:
            if not username:
                template_vars['errors'] = 'Please enter username'
            elif not password:
                template_vars['errors'] = 'Please enter password'
            elif user is None:
                template_vars['errors'] = 'Username and password do not match'

    return render(request, 'django_gui/login.html', template_vars)


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
    load_errors = []         # any errors reloading the cruise definition
    load_error_summary = ''  # what we were trying to do when we got them
    if request.method == 'POST':
        logging.debug('POST: %s', request.POST)

        # First things first: log the request
        log_request(request, 'index')

        # Are they deleting a cruise?(!)
        if 'delete_cruise' in request.POST:
            logging.info('deleting cruise')
            api.delete_configuration()

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
                filename = api.get_configuration()['config_filename']
            except (ValueError, AttributeError, KeyError, TypeError):
                filename = None

            if not filename:
                load_error_summary = 'Could not reload the cruise definition.'
                load_errors = ['There is no cruise definition file to reload.']
            else:
                # Since we're reloading, we'd like to keep any unchanged
                # loggers running and not revert to the cruise's default
                # mode.
                load_errors = load_cruise_definition(filename, preserve_mode=True)
                if load_errors:
                    load_error_summary = (
                        'Could not reload "%s". The definition that was '
                        'already loaded is still in effect.' % filename)

            if load_errors:
                logging.warning('Error reloading current configuration: %s',
                                load_errors)

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
        'load_errors': load_errors,
        'load_error_summary': load_error_summary,
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
def change_mode(request):
    """Change logger manager mode and view logger manager stderr.
    """
    global api
    if api is None:
        api = DjangoServerAPI()

    ############################
    # If we've gotten a POST request
    # cruise_id = ''
    if request.method == 'POST':
        logging.debug('POST: %s', request.POST)

        # First things first: log the request
        log_request(request, 'index')

        if 'close' in request.POST:
            return HttpResponse('<script>window.close()</script>')
        # Did we get a mode selection?
        elif 'select_mode' in request.POST:
            new_mode_name = request.POST['select_mode']
            logging.info('switching to mode "%s"', new_mode_name)
            try:
                api.set_active_mode(new_mode_name)
            except ValueError as e:
                logging.warning('Error trying to set mode to "%s": %s',
                                new_mode_name, str(e))
        # Else unknown post
        else:
            logging.warning('Unknown POST request: %s', request.POST)

    # Assemble information to draw page
    template_vars = {
        'websocket_server': WEBSOCKET_DATA_SERVER,
    }
    try:
        template_vars['modes'] = api.get_modes()
        template_vars['active_mode'] = api.get_active_mode()
    except (ValueError, AttributeError) as e:
        logging.info('Unknown error: %s', str(e))

    return render(request, 'django_gui/change_mode.html', template_vars)


################################################################################
def edit_config(request, logger_id):
    global api
    if api is None:
        api = DjangoServerAPI()

    ############################
    # If we've gotten a POST request, they've selected a new config
    if request.method == 'POST':

        # If they've hit the "Update" button
        if 'close' in request.POST:
            return HttpResponse('<script>window.close()</script>')
        elif 'update' in request.POST:
            # First things first: log the request
            log_request(request, '%s edit_config' % logger_id)

            # Now figure out what they selected
            new_config = request.POST['select_config']
            logging.warning('selected config: %s', new_config)
            api.set_active_logger_config(logger_id, new_config)
        else:
            logging.warning('Unrecognized post request?: ' + str(request.POST))

    # If not a POST, render the selector page:
    # What's our current mode? What's the default config for this logger
    # in this mode?
    active_mode = api.get_active_mode()
    config_options = api.get_logger_config_names(logger_id)
    default_config = api.get_logger_config_name(logger_id, active_mode)
    current_config = api.get_logger_config_name(logger_id)

    # dict of config_name: config_yaml. Configs are stored as JSON, but
    # they're written and read by humans as YAML, so that's what we show.
    # sort_keys=False keeps each config's keys in their stored order rather
    # than alphabetizing them.
    config_map = {
        config_name: yaml.safe_dump(api.get_logger_config(config_name),
                                    default_flow_style=False,
                                    sort_keys=False,
                                    allow_unicode=True,
                                    width=100)
        for config_name in config_options
    }

    return render(request, 'django_gui/edit_config.html',
                  {
                      'logger_id': logger_id,
                      'current_config': current_config,
                      'config_map': config_map,
                      'default_config': default_config,
                      'config_options': config_options,
                      'websocket_server': WEBSOCKET_DATA_SERVER
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
        contents = {'↩️': '' if abspath(dir_name) in FILECHOOSER_DIRS
                    else abspath(dir_name + '/..')}
        for filename in listdir(dir_name):
            path = dir_name + '/' + filename
            if isdir(path):
                filename = '📂 ' + filename + '/'
            elif filename.endswith(('.yaml', '.yml')):
                # Include YAML files only
                filename = '📄 ' + filename
            else:
                # Skip everything else
                continue
            contents[filename] = abspath(path)
        return contents

    ##################
    # Start of choose_file() code
    target_file = None  # file we're going to load
    load_errors = []    # where we store any errors
    load_error_summary = ''  # what we were trying to do when we got them

    # If post, figure out what user selected
    if request.method == 'POST':
        dir_name = request.POST.get('dir_name')
        selection = [request.POST.get('select_file', '')]

        # Was this a request to load the target file?
        target_file = request.POST.get('target_file')
        if target_file:
            # Load the definition and set to the default mode
            load_errors = load_cruise_definition(target_file)

            # If no errors, go home; otherwise reset back to previous page
            if not load_errors:
                return HttpResponse('<script>window.close()</script>')
            else:
                logging.warning('Errors loading cruise definition: %s', load_errors)
                load_error_summary = (
                    'Could not load "%s". Any definition that was already '
                    'loaded is still in effect.' % target_file)
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
            for base in FILECHOOSER_DIRS:
                parent_dir = dirname(base)
                if selection[0].startswith(parent_dir):
                    dir_name = './' + relpath(selection[0], parent_dir)
                    break
            # dir_name = selection[0]
            listing = get_dir_contents(selection[0])

    # If here, 'selection' is a list of files/dirs; use them as our listing
    else:
        # If selection includes one of our top dirs, use the complete
        # listing from our settings.
        if set(selection).intersection(FILECHOOSER_DIRS):
            dir_name = ''
            selection = FILECHOOSER_DIRS
        listing = {'📂 ' + f.split('/')[-1] + '/': f for f in selection}

    # Render the page
    return render(request, 'django_gui/choose_file.html',
                  {'target_file': target_file,
                   'dir_name': dir_name,
                   'listing': listing,
                   'load_errors': load_errors,
                   'load_error_summary': load_error_summary})


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
