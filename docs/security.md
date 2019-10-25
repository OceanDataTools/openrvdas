# OpenRVDAS Security
© 2019 David Pablo Cohn - DRAFT 2019-09-15

At present, OpenRVDAS makes very broad security assumptions, most of
which should be tightened up:

* **Server machine is physically secure**: This assumption seems
    relatively safe. It's hard to protect against physical hardware
    attacks.

* **Root and "rvdas" user accounts are secure**: We assume that both
    the root account and that the user `rvdas` account on the
    OpenRVDAS server are secure from malicious actors. A malicious
    actor could change code and/or configuration.

    We do not assume that other user accounts are secure from
    malicious actors, so in theory the server could be attacked by a
    user subjecting the machine to a heavy load, or filling up
    available disk.

* **Network is free of malicious actors**: We assume that the system
    is running on a ship's internal network, and thus that the servers
    are not going to be subject to DOS attacks or maliciously
    malformed requests.

    The Django interface allows any user to view the console and
    display pages, but only allows authenticated Django superusers
    (typically user `rvdas`) to load configurations and start/stop
    loggers.

    At present, the system loads cruise definitions using a browser
    file chooser. This allows anyone who has the Django superuser
    password to upload and run an arbitrary logger. Because the
    TextFileReader and TextFileWriter components read/write text files
    (as their names suggest), this would in theory allow a user to
    read and/or overwriter any server file that user rvdas has access
    to. This is a major security flaw described in Issue #145.
  
