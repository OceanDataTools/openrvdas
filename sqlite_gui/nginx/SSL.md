## Generating a certificate
If your organization does not already have a plan for generating certifcates
for securing your websites or you just need a quick and dirty certificate
to get yourself started, you can whip one out running
`bash make_certificate.notes`. 

## How to make your browser trust the certifcate
The script does not just generate a certificate that just signed itself.
It generates a fake certificate authority and signs the server certificate
with that.  So if you import the certicate authority certificate into
your browser as a trusted root, any certicate signed by that will
be trusted.
