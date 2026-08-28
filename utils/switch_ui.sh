#!/bin/bash -e

# OpenRVDAS is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openrvdas
#
# This script switches an existing OpenRVDAS installation between the
# Django web UI and the React/FastAPI web UI (or turns the web UI off
# entirely) without re-running install_openrvdas.sh.
#
# INVOCATION
#
#   bash utils/switch_ui.sh [django|react|none|status] [options]
#
# Options:
#   -y, --yes         Don't ask for confirmation before switching
#   -n, --dry-run     Show what would change, but don't change anything
#       --no-restart  Rewrite configs but don't stop/start supervisor processes
#   -h, --help        Show this message
#
# WHAT IT DOES
#
# install_openrvdas.sh writes supervisord entries for both UIs, with the
# entries for the UI you didn't choose commented out:
#
#   openrvdas_django.{conf,ini}          nginx + uwsgi   -> [group:django]
#   openrvdas_react.{conf,ini}           nginx + uvicorn -> [group:react_ui]
#   openrvdas_logger_manager.{conf,ini}  logger_manager --database django|fastapi
#
# Only one of the two may be active at a time, because both define
# [program:nginx]. This script flips which one is commented out, points
# logger_manager at the matching database backend, updates DEFAULT_UI_TYPE
# in the install preferences file (so a later re-run of the installer
# doesn't silently switch you back), and restarts the affected processes.
#
# It does NOT build anything. Switching to a UI that was never installed
# (no React build, or no uwsgi config) is refused with an explanation --
# re-run install_openrvdas.sh and choose that UI to build the missing
# pieces. Once both have been installed at least once, this script can
# flip between them freely.
#
# The script is idempotent: switching to the UI that is already active
# reports that and exits without touching anything.
#
# For non-standard installs, SUPERVISOR_DIR, SUPERVISOR_SUFFIX and
# OPENRVDAS_ROOT may be preset in the environment to override the locations
# the script would otherwise work out for itself.

###########################################################################
###########################################################################
function exit_gracefully {
    echo Exiting.
    exit 1
}

#########################################################################
#########################################################################
# Return a normalized yes/no for a value
yes_no() {
    QUESTION=$1
    DEFAULT_ANSWER=$2

    while true; do
        read -p "$QUESTION ($DEFAULT_ANSWER) " yn
        case $yn in
            [Yy]* )
                YES_NO_RESULT=yes
                break;;
            [Nn]* )
                YES_NO_RESULT=no
                break;;
            "" )
                YES_NO_RESULT=$DEFAULT_ANSWER
                break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

###########################################################################
###########################################################################
function usage {
    cat <<EOF
Usage: bash utils/switch_ui.sh [django|react|none|status] [options]

  django   Serve the classic Django web console (nginx + uwsgi)
  react    Serve the React/FastAPI web console (nginx + uvicorn)
  none     Disable the web console entirely (headless)
  status   Report which UI is currently configured, and exit

Options:
  -y, --yes         Don't ask for confirmation before switching
  -n, --dry-run     Show what would change, but don't change anything
      --no-restart  Rewrite configs but don't stop/start supervisor processes
  -h, --help        Show this message
EOF
}

###########################################################################
###########################################################################
# Set OS_TYPE to MacOS, CentOS or Ubuntu. Simplified from the version in
# install_openrvdas.sh -- we only need the family, not the version.
function get_os_type {
    if [[ `uname -s` == 'Darwin' ]];then
        OS_TYPE=MacOS
    elif [[ `uname -s` == 'Linux' ]];then
        if [[ ! -z `grep -E 'NAME="(Ubuntu|Linux Mint|Debian|Raspbian)' /etc/os-release` ]];then
            OS_TYPE=Ubuntu
        elif [[ ! -z `grep -E 'NAME="(CentOS|Red Hat Enterprise Linux|Rocky Linux|AlmaLinux)' /etc/os-release` ]];then
            OS_TYPE=CentOS
        else
            echo "Sorry - unknown Linux variant!"
            exit_gracefully
        fi
    else
        echo Unknown OS type: `uname -s`
        exit_gracefully
    fi
}

###########################################################################
###########################################################################
# Work out where supervisor's config files live, using the same locations
# install_openrvdas.sh writes them to.
function get_supervisor_dir {
    # Locations may be preset in the environment for non-standard installs.
    if [ $OS_TYPE == 'MacOS' ]; then
        HOMEBREW_PREFIX=${HOMEBREW_PREFIX:-$( [ "$(uname -m)" = "arm64" ] && echo /opt/homebrew || echo /usr/local )}
        SUPERVISOR_DIR=${SUPERVISOR_DIR:-${HOMEBREW_PREFIX}/etc/supervisor.d}
        SUPERVISOR_SUFFIX=${SUPERVISOR_SUFFIX:-ini}
    elif [ $OS_TYPE == 'CentOS' ]; then
        SUPERVISOR_DIR=${SUPERVISOR_DIR:-/etc/supervisord.d}
        SUPERVISOR_SUFFIX=${SUPERVISOR_SUFFIX:-ini}
    else  # Ubuntu/Debian
        SUPERVISOR_DIR=${SUPERVISOR_DIR:-/etc/supervisor/conf.d}
        SUPERVISOR_SUFFIX=${SUPERVISOR_SUFFIX:-conf}
    fi

    DJANGO_FILE=$SUPERVISOR_DIR/openrvdas_django.${SUPERVISOR_SUFFIX}
    REACT_FILE=$SUPERVISOR_DIR/openrvdas_react.${SUPERVISOR_SUFFIX}
    LOGGER_MANAGER_FILE=$SUPERVISOR_DIR/openrvdas_logger_manager.${SUPERVISOR_SUFFIX}

    if [ ! -d "$SUPERVISOR_DIR" ]; then
        echo "ERROR: supervisor config directory not found: $SUPERVISOR_DIR"
        echo "Has install_openrvdas.sh been run on this machine?"
        exit_gracefully
    fi
    if [ ! -f "$LOGGER_MANAGER_FILE" ]; then
        echo "ERROR: no OpenRVDAS supervisor config found at $LOGGER_MANAGER_FILE"
        echo "Has install_openrvdas.sh been run on this machine?"
        exit_gracefully
    fi
}

###########################################################################
###########################################################################
# Find the openrvdas installation these supervisor configs refer to. Trust
# the installed config over this script's own location, since the script may
# be run from a different clone than the one that was installed.
function get_openrvdas_root {
    if [ -n "${OPENRVDAS_ROOT:-}" ] && [ -d "$OPENRVDAS_ROOT" ]; then
        return
    fi
    OPENRVDAS_ROOT=$(grep '^directory=' "$LOGGER_MANAGER_FILE" 2>/dev/null | head -1 | cut -d= -f2-)

    if [ -z "$OPENRVDAS_ROOT" ] || [ ! -d "$OPENRVDAS_ROOT" ]; then
        OPENRVDAS_ROOT=$(dirname "$(dirname "$(realpath "$0")")")
        echo "Could not read install location from $LOGGER_MANAGER_FILE;"
        echo "falling back to this script's location."
    fi

    if [ ! -d "$OPENRVDAS_ROOT" ]; then
        echo "ERROR: could not locate the openrvdas installation directory."
        exit_gracefully
    fi
}

###########################################################################
###########################################################################
# Locate the install preferences file so we can keep DEFAULT_UI_TYPE in
# sync. The installer writes it to whatever directory it was run from, so
# check the likely candidates.
function find_preferences_file {
    PREFERENCES_FILE=
    for CANDIDATE in \
        "${OPENRVDAS_ROOT}/.install_openrvdas_preferences" \
        "$(dirname "${OPENRVDAS_ROOT}")/.install_openrvdas_preferences" \
        "${HOME}/.install_openrvdas_preferences" \
        "./.install_openrvdas_preferences"; do
        if [ -f "$CANDIDATE" ]; then
            PREFERENCES_FILE=$CANDIDATE
            break
        fi
    done
}

###########################################################################
###########################################################################
# Is the UI in $1 ('django' or 'react') currently enabled? A file is enabled
# if it has at least one uncommented [program:...] section.
function ui_is_enabled {
    case "$1" in
        django) UI_FILE=$DJANGO_FILE ;;
        react)  UI_FILE=$REACT_FILE ;;
    esac
    [ -f "$UI_FILE" ] && grep -q '^\[program:' "$UI_FILE"
}

###########################################################################
###########################################################################
# Report which UI the installed supervisor configs currently select.
function get_current_ui {
    CURRENT_UI=none
    if ui_is_enabled django; then
        CURRENT_UI=django
    fi
    if ui_is_enabled react; then
        if [ "$CURRENT_UI" == 'django' ]; then
            # Both active means supervisor sees two [program:nginx] entries
            # and will refuse to start; the switch below will repair it.
            CURRENT_UI=broken
        else
            CURRENT_UI=react
        fi
    fi

    CURRENT_DATABASE=$(sed -n 's/^command=.*--database \([a-z]*\).*/\1/p' "$LOGGER_MANAGER_FILE" | head -1)
}

###########################################################################
###########################################################################
# Decide whether writing the supervisor configs needs sudo. On Linux they
# live under /etc and do; on MacOS they live under a Homebrew prefix that is
# normally owned by the user running brew, and don't. Asking for a password
# we don't need is just friction, so check before demanding one.
function set_write_method {
    WRITE_CP='cp'
    for TARGET_PATH in "$SUPERVISOR_DIR" "$LOGGER_MANAGER_FILE" \
                       "$DJANGO_FILE" "$REACT_FILE"; do
        [ -e "$TARGET_PATH" ] || continue
        if [ ! -w "$TARGET_PATH" ]; then
            WRITE_CP='sudo cp'
            return
        fi
    done
}

###########################################################################
###########################################################################
# Comment out (or uncomment) every directive in a supervisor config file.
#
# install_openrvdas.sh generates these files by prefixing every line with
# ';' when the UI is not selected, leaving the first line -- the file's
# own header comment -- and blank lines alone. Adding or removing exactly
# one leading ';' from lines 2+ reproduces that transformation exactly and
# is fully reversible, including lines like ';user=rvdas' that are meant to
# stay commented out.
#
# The transformation must only ever be applied to a file that is not already
# in the target state: uncommenting an already-uncommented file would strip
# the ';' from ';user=rvdas' and leave nginx trying to run as an unprivileged
# user. So check the current state first and do nothing if it already matches.
function set_file_state {
    FILE=$1
    STATE=$2   # 'enabled' or 'disabled'

    if grep -q '^\[program:' "$FILE"; then
        FILE_STATE=enabled
    else
        FILE_STATE=disabled
    fi
    if [ "$FILE_STATE" == "$STATE" ]; then
        echo "$(basename "$FILE") already ${STATE} - leaving alone."
        return
    fi

    TEMP_FILE=$(mktemp "${TMPDIR:-/tmp}/openrvdas_switch_ui.XXXXXX")

    if [ "$STATE" == 'enabled' ]; then
        awk 'NR==1 || /^[[:space:]]*$/ {print; next} {sub(/^;/, ""); print}' \
            "$FILE" > "$TEMP_FILE"
    else
        awk 'NR==1 || /^[[:space:]]*$/ {print; next} {print ";" $0}' \
            "$FILE" > "$TEMP_FILE"
    fi

    # cp rather than mv, so the destination keeps its existing ownership
    # and permissions.
    $WRITE_CP "$TEMP_FILE" "$FILE"
    rm -f "$TEMP_FILE"
}

###########################################################################
###########################################################################
# Point logger_manager at the database backend that matches the UI: the
# React UI keeps its state in the FastAPI backend's SQLite database, the
# Django UI in the Django database.
function set_logger_manager_database {
    NEW_DATABASE=$1

    TEMP_FILE=$(mktemp "${TMPDIR:-/tmp}/openrvdas_switch_ui.XXXXXX")
    sed -e "s/--database [a-z]*/--database ${NEW_DATABASE}/" \
        "$LOGGER_MANAGER_FILE" > "$TEMP_FILE"
    $WRITE_CP "$TEMP_FILE" "$LOGGER_MANAGER_FILE"
    rm -f "$TEMP_FILE"
}

###########################################################################
###########################################################################
# Keep DEFAULT_UI_TYPE in the preferences file in sync, so that re-running
# install_openrvdas.sh defaults to the UI we just switched to.
function update_preferences {
    NEW_UI=$1

    if [ -z "$PREFERENCES_FILE" ]; then
        echo "No .install_openrvdas_preferences file found - skipping."
        echo "If you re-run install_openrvdas.sh, remember to select '${NEW_UI}'."
        return
    fi

    TEMP_FILE=$(mktemp "${TMPDIR:-/tmp}/openrvdas_switch_ui.XXXXXX")
    if grep -q '^DEFAULT_UI_TYPE=' "$PREFERENCES_FILE"; then
        sed -e "s/^DEFAULT_UI_TYPE=.*/DEFAULT_UI_TYPE=${NEW_UI}/" \
            "$PREFERENCES_FILE" > "$TEMP_FILE"
    else
        cp "$PREFERENCES_FILE" "$TEMP_FILE"
        echo "DEFAULT_UI_TYPE=${NEW_UI}" >> "$TEMP_FILE"
    fi
    cp "$TEMP_FILE" "$PREFERENCES_FILE" 2>/dev/null || sudo cp "$TEMP_FILE" "$PREFERENCES_FILE"
    rm -f "$TEMP_FILE"
    echo "Updated DEFAULT_UI_TYPE=${NEW_UI} in $PREFERENCES_FILE"
}

###########################################################################
###########################################################################
# Warn if the two UIs' nginx configs don't agree about which ports they
# serve on.
#
# Older installers wrote the nginx config only for the UI selected on that
# run, so each UI's config can be a frozen snapshot of the SSL/port answers
# given the last time that UI was installed. Switching then moves the
# console to a different port - the classic symptom being a browser left on
# https://host getting "this site can't be reached" because the incoming UI
# only listens on port 80. Current installers write both configs on every
# run, so re-running the installer resolves this.
function check_nginx_configs {
    DJANGO_NGINX=${OPENRVDAS_ROOT}/django_gui/openrvdas_nginx.conf
    REACT_NGINX=${OPENRVDAS_ROOT}/web_frontend/openrvdas_nginx.conf

    if [ ! -f "$DJANGO_NGINX" ] || [ ! -f "$REACT_NGINX" ]; then
        return
    fi

    DJANGO_LISTEN=$(grep -E '^[[:space:]]*listen' "$DJANGO_NGINX" \
                        | sed -e 's/^[[:space:]]*//' -e 's/;$//' -e 's/  */ /g' \
                        | sort | tr '\n' '|' | sed -e 's/|$//' -e 's/|/, /g')
    REACT_LISTEN=$(grep -E '^[[:space:]]*listen' "$REACT_NGINX" \
                       | sed -e 's/^[[:space:]]*//' -e 's/;$//' -e 's/  */ /g' \
                       | sort | tr '\n' '|' | sed -e 's/|$//' -e 's/|/, /g')

    if [ "$DJANGO_LISTEN" == "$REACT_LISTEN" ]; then
        return
    fi

    echo
    echo "WARNING: the two UIs' nginx configs do not serve the same ports."
    echo "  django (${DJANGO_NGINX}):"
    echo "    ${DJANGO_LISTEN}"
    echo "  react  (${REACT_NGINX}):"
    echo "    ${REACT_LISTEN}"
    echo
    echo "Each UI's nginx config is written when that UI is installed, so one"
    echo "of these is probably left over from an install that answered the"
    echo "SSL/port questions differently. After switching, the console will be"
    echo "served on the target UI's ports - if your browser is pointed at the"
    echo "other UI's port (http:// vs https://, say), it will look like the"
    echo "server is down."
    echo
    echo "To regenerate both configs consistently, re-run:"
    echo "  bash ${OPENRVDAS_ROOT}/utils/install_openrvdas.sh"
}

###########################################################################
###########################################################################
# Verify that the UI we're switching to has actually been installed. We
# only switch configs here; we don't build anything.
function check_prerequisites {
    TARGET=$1
    MISSING=
    MISSING_PACKAGES=

    if [ "$TARGET" == 'django' ]; then
        if [ ! -f "$DJANGO_FILE" ]; then
            MISSING="${MISSING}  $DJANGO_FILE (supervisor config)\n"
        fi
        for REQUIRED in \
            "${OPENRVDAS_ROOT}/django_gui/openrvdas_nginx.conf" \
            "${OPENRVDAS_ROOT}/django_gui/openrvdas_uwsgi.ini" \
            "${OPENRVDAS_ROOT}/venv/bin/uwsgi"; do
            [ -e "$REQUIRED" ] || MISSING="${MISSING}  $REQUIRED\n"
        done

    elif [ "$TARGET" == 'react' ]; then
        if [ ! -f "$REACT_FILE" ]; then
            MISSING="${MISSING}  $REACT_FILE (supervisor config)\n"
        fi
        for REQUIRED in \
            "${OPENRVDAS_ROOT}/web_frontend/openrvdas_nginx.conf" \
            "${OPENRVDAS_ROOT}/web_frontend/dist/index.html" \
            "${OPENRVDAS_ROOT}/web_backend/.venv/bin/uvicorn" \
            "${OPENRVDAS_ROOT}/web_backend/.env"; do
            [ -e "$REQUIRED" ] || MISSING="${MISSING}  $REQUIRED\n"
        done

        # uvicorn runs out of web_backend/.venv, but logger_manager runs out of
        # the MAIN venv - and with --database fastapi it imports web_backend's
        # async API, so FastAPI's packages have to be in the main venv too. The
        # installer puts them there only while installing the React UI, so an
        # install that has since been re-run for Django (which recreates the
        # venv) ends up with a complete-looking React tree whose logger_manager
        # dies on startup with "No module named 'fastapi'".
        MAIN_PYTHON="${OPENRVDAS_ROOT}/venv/bin/python"
        if [ -x "$MAIN_PYTHON" ] && \
           ! "$MAIN_PYTHON" -c 'import fastapi, sqlalchemy, aiosqlite, greenlet, pydantic_settings' \
             > /dev/null 2>&1; then
            MISSING_PACKAGES="yes"
        fi
    fi

    if [ -n "$MISSING" ] || [ -n "$MISSING_PACKAGES" ]; then
        echo
        echo "ERROR: the '${TARGET}' UI does not look fully installed."

        if [ -n "$MISSING" ]; then
            echo
            echo "Missing files:"
            echo -e "$MISSING"
        fi

        if [ -n "$MISSING_PACKAGES" ]; then
            echo
            echo "The React UI's files are present, but ${OPENRVDAS_ROOT}/venv is"
            echo "missing the packages logger_manager needs to talk to the FastAPI"
            echo "database. Switching now would leave logger_manager dead with"
            echo "\"No module named 'fastapi'\". Install them into the main venv:"
            echo
            echo "  ${OPENRVDAS_ROOT}/venv/bin/pip install \\"
            echo "      'fastapi>=0.135.0' 'sqlalchemy>=2.0' 'aiosqlite>=0.22' \\"
            echo "      'greenlet>=3.2' 'pydantic>=2.0' 'pydantic-settings>=2.0'"
            echo
            echo "then run this script again."
        fi

        if [ -n "$MISSING" ]; then
            echo "This script only switches between UIs that have already been"
            echo "installed; it does not build them. To install the '${TARGET}' UI,"
            echo "re-run the installer and select it:"
            echo
            echo "  bash ${OPENRVDAS_ROOT}/utils/install_openrvdas.sh"
            echo
            echo "After that, this script can switch back and forth freely."
        fi
        exit_gracefully
    fi
}

###########################################################################
###########################################################################
# Find a supervisorctl we can talk to, with or without sudo.
function get_supervisorctl {
    SUPERVISORCTL=$(command -v supervisorctl || true)
    if [ -z "$SUPERVISORCTL" ]; then
        echo "WARNING: supervisorctl not found in PATH; skipping restart."
        echo "Configs have been updated; restart supervisor by hand to apply."
        SUPERVISORCTL_CMD=
        return
    fi

    if $SUPERVISORCTL version > /dev/null 2>&1; then
        SUPERVISORCTL_CMD="$SUPERVISORCTL"
    elif sudo $SUPERVISORCTL version > /dev/null 2>&1; then
        SUPERVISORCTL_CMD="sudo $SUPERVISORCTL"
    else
        echo "WARNING: could not connect to supervisord; skipping restart."
        echo "Configs have been updated; restart supervisor by hand to apply."
        SUPERVISORCTL_CMD=
    fi
}

###########################################################################
###########################################################################
# Stop the outgoing UI, load the new configs, start the incoming UI, and
# restart logger_manager so it picks up its new database backend.
function restart_services {
    NEW_UI=$1

    # Both UI groups are stopped unconditionally below, so the outgoing UI
    # doesn't need to be named here.

    get_supervisorctl
    if [ -z "$SUPERVISORCTL_CMD" ]; then
        return
    fi

    # Stop whatever UI was running first: both UI configs define
    # [program:nginx], so the old one has to release the port and the
    # program name before the new one is loaded.
    for GROUP in django react_ui; do
        if $SUPERVISORCTL_CMD status "${GROUP}:*" > /dev/null 2>&1; then
            echo "Stopping ${GROUP}..."
            $SUPERVISORCTL_CMD stop "${GROUP}:*" || true
        fi
    done

    echo "Rereading supervisor configuration..."
    $SUPERVISORCTL_CMD reread || true
    $SUPERVISORCTL_CMD update || true

    echo "Restarting logger_manager (--database ${LOGGER_DATABASE})..."
    $SUPERVISORCTL_CMD restart logger_manager || true

    case "$NEW_UI" in
        django)
            echo "Starting django..."
            $SUPERVISORCTL_CMD start 'django:*' || true
            ;;
        react)
            echo "Starting react_ui..."
            $SUPERVISORCTL_CMD start 'react_ui:*' || true
            ;;
    esac

    echo
    $SUPERVISORCTL_CMD status || true
}

###########################################################################
###########################################################################
###########################################################################
###########################################################################
# Start of actual script
###########################################################################
###########################################################################

TARGET_UI=
ASSUME_YES=no
DRY_RUN=no
RESTART=yes

while [ $# -gt 0 ]; do
    case "$1" in
        django|react|none|status)
            TARGET_UI=$1 ;;
        -y|--yes)
            ASSUME_YES=yes ;;
        -n|--dry-run)
            DRY_RUN=yes ;;
        --no-restart)
            RESTART=no ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "Unknown argument: $1"
            echo
            usage
            exit_gracefully ;;
    esac
    shift
done

get_os_type
get_supervisor_dir
get_openrvdas_root
find_preferences_file
get_current_ui

echo "#####################################################################"
echo "OpenRVDAS installation: ${OPENRVDAS_ROOT}"
echo "Supervisor configs:     ${SUPERVISOR_DIR}"
echo "Currently configured web UI: ${CURRENT_UI}"
echo "logger_manager database:     ${CURRENT_DATABASE:-unknown}"

if [ "$CURRENT_UI" == 'broken' ]; then
    echo
    echo "WARNING: both the Django and React supervisor entries are enabled."
    echo "Supervisor cannot run both (each defines [program:nginx]). Switching"
    echo "to a single UI below will repair this."
fi

# 'status' (or no argument at all) just reports and exits.
if [ -z "$TARGET_UI" ] || [ "$TARGET_UI" == 'status' ]; then
    get_supervisorctl
    if [ -n "$SUPERVISORCTL_CMD" ]; then
        echo
        $SUPERVISORCTL_CMD status || true
    fi
    if [ -z "$TARGET_UI" ]; then
        echo
        usage
    fi
    exit 0
fi

if [ "$TARGET_UI" == "$CURRENT_UI" ]; then
    echo
    echo "Web UI is already set to '${TARGET_UI}' - nothing to do."
    echo "(Use 'status' to see whether its processes are actually running.)"
    exit 0
fi

# React keeps its state in the FastAPI backend's database, Django in the
# Django database. 'none' leaves logger_manager on the Django database,
# matching what install_openrvdas.sh does for a headless install.
if [ "$TARGET_UI" == 'react' ]; then
    LOGGER_DATABASE=fastapi
else
    LOGGER_DATABASE=django
fi

if [ "$TARGET_UI" != 'none' ]; then
    check_prerequisites $TARGET_UI
    check_nginx_configs
fi

echo
echo "#####################################################################"
echo "Switching web UI: ${CURRENT_UI} -> ${TARGET_UI}"
echo
echo "This will:"
if [ "$TARGET_UI" == 'django' ]; then
    echo "  - enable  nginx + uwsgi   in $DJANGO_FILE"
    echo "  - disable nginx + uvicorn in $REACT_FILE"
elif [ "$TARGET_UI" == 'react' ]; then
    echo "  - enable  nginx + uvicorn in $REACT_FILE"
    echo "  - disable nginx + uwsgi   in $DJANGO_FILE"
else
    echo "  - disable both UI entries (no web console will be served)"
fi
echo "  - set logger_manager to --database ${LOGGER_DATABASE}"
if [ -n "$PREFERENCES_FILE" ]; then
    echo "  - set DEFAULT_UI_TYPE=${TARGET_UI} in $PREFERENCES_FILE"
fi
if [ $RESTART == 'yes' ]; then
    echo "  - restart the affected supervisor processes"
fi

if [ "$CURRENT_DATABASE" != "$LOGGER_DATABASE" ]; then
    echo
    echo "NOTE: the Django and React UIs store logger configurations in"
    echo "separate databases, and logger_manager is being repointed from"
    echo "'${CURRENT_DATABASE:-unknown}' to '${LOGGER_DATABASE}'. Any cruise definition loaded"
    echo "under the old UI will not appear under the new one until you load"
    echo "it there as well. No data is deleted - the old database is left"
    echo "untouched and comes back if you switch back."
fi

if [ $DRY_RUN == 'yes' ]; then
    echo
    echo "--dry-run given; no changes made."
    exit 0
fi

if [ $ASSUME_YES == 'no' ]; then
    echo
    yes_no "Proceed?" yes
    if [ $YES_NO_RESULT == 'no' ]; then
        exit_gracefully
    fi
fi

# Writing into the supervisor conf dir may need root - check whether it
# actually does before asking for a password.
set_write_method
if [ "$WRITE_CP" == 'sudo cp' ] && [ "$EUID" -ne 0 ]; then
    echo "This script requires sudo to update the supervisor configuration."
    if ! sudo -v; then
        echo "ERROR: Could not obtain sudo privileges."
        exit_gracefully
    fi
fi

echo
echo "#####################################################################"
if [ "$TARGET_UI" == 'django' ]; then
    [ -f "$REACT_FILE" ] && set_file_state "$REACT_FILE" disabled
    set_file_state "$DJANGO_FILE" enabled
elif [ "$TARGET_UI" == 'react' ]; then
    [ -f "$DJANGO_FILE" ] && set_file_state "$DJANGO_FILE" disabled
    set_file_state "$REACT_FILE" enabled
else
    [ -f "$DJANGO_FILE" ] && set_file_state "$DJANGO_FILE" disabled
    [ -f "$REACT_FILE" ] && set_file_state "$REACT_FILE" disabled
fi
echo "Supervisor UI configuration updated."

set_logger_manager_database $LOGGER_DATABASE
echo "logger_manager set to --database ${LOGGER_DATABASE}."

update_preferences $TARGET_UI

if [ $RESTART == 'yes' ]; then
    echo
    echo "#####################################################################"
    echo "Restarting services..."
    restart_services "$TARGET_UI"
else
    echo
    echo "--no-restart given. To apply the new configuration, run:"
    echo "  supervisorctl reread && supervisorctl update"
fi

echo
echo "#####################################################################"
echo "Web UI is now: ${TARGET_UI}"
if [ "$TARGET_UI" != 'none' ]; then
    echo
    echo "Point a browser at this machine to reach the ${TARGET_UI} console."
    echo "If it doesn't come up, check:"
    echo "  supervisorctl status"
    echo "  /var/log/openrvdas/nginx.stderr"
    if [ "$TARGET_UI" == 'react' ]; then
        echo "  /var/log/openrvdas/uvicorn.stderr"
    else
        echo "  /var/log/openrvdas/uwsgi.stderr"
    fi
fi
echo
