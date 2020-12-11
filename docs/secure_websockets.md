# Using Secure Websockets with OpenRVDAS
© 2020 David Pablo Cohn - DRAFT 2020-12-11

## Overview

OpenRVDAS uses websockets to relay logger data and status information to
the [CachedDataServer](cached_data_server.md), which then support
display of near-realtime updates to the web console and display widgets.
While on-server websocket communication is conducted (insecurely) on port
8766, in some environments security may dictate restricting off-server access
to that port. For this reason, NGINX is configured to also make the cached
data server available on the default web console port at path `/cds-ws`. 
The [OpenRVDAS installation script](../utils/install_openrvdas.sh) allows
configuring NGINX to require secure websockets (`wss://`) for off-server
access along this path.

If, during installation, the user specifies that secure websockets should
be used, they will be prompted to either specify the location of a `.crt`
and `.key` certificate files, or will be coached through creation of those
files via a self-signed certificate.

## Getting browsers to accept your self-signed certificate

If the server already has a valid certificate, nothing more needs to be done.
If the user follows the prompts to create a self-signed certificate, most browsers
will balk at accepting them without a little extra work. You will need to first
create a `.pem` file which, in this case, should just be a renamed copy of the
public part of the certificate:

```cp my_created_certificate.crt my_created_certificate.pem```

Copy this `.pem` file to the machine on which you will be running the browser
and import it into your keychain.

As of 2020-12-11, on a Macintosh, you would do this as follows:

  1. Open the Keychain Access app and select `File > Import Items...`
  1. Navigate to the `.pem` file you've copied to your machine and import it.
  1. You should now see the imported certificate under the "Certificates"
     header in the Keychain Access app. Double-click it and expand the `Trust`
     section of the new window.
  1. In the "When using this certificate..." drop-down, select "Always Trust"
     and close the window. 
  1. The first time you navigate your browser to the server, you will still get
     a certificate warning but, if you select the "Advanced" link at the bottom 
     of the warning (in Chrome, at least), it will give you an option to continue
     to the page.

The method of accepting self-signed certificates will undoubtedly continue to
change and make these instructions obsolete. At the very least, you can ask
Google for the latest concerting your specific browser and OS: 

E.g.: [install certificate in chrome on macos](https://www.google.com/search?q=install+certificate+in+chrome+on+macos)
