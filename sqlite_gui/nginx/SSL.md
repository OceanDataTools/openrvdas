## Generating a certificate
Many organizations these days have a plan/policy for managing webserver
certificates.  Those can be a private PKI server, LetsEncrypt, or a
curated list of powershell scripts to run.  For those who do not have
a plan in place, or just want to do some quick and dirty testing, this
script might be of assistance.
`GenerateCertificate.sh`. 

## How to make your browser trust the certifcate
The script does not just generate a certificate that just signed itself.
It generates a fake certificate authority and signs the server certificate
with that.  So if you import the certicate authority certificate into
your browser as a trusted root, any certicate signed by that will
be trusted.
