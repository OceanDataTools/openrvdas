#!/bin/bash

# Quick and dirty script to generaate a cert/key pair for nginx.

exec 2> debug.log

QUERY='fields=status,message,countryCode,regionName,city,lat,lon'
curl -s "http://ip-api.com/json/?${QUERY}" > ip-api.com
cat ip-api.com | tr ',' '\n' > whereami.txt
rm -f ip-api.com

#{"status":"success"
#"countryCode":"CL"
#"regionName":"Region of Magallanes"
#"city":"Punta Arenas"
#"lat":-53.1471
#"lon":-70.9156}
grep -q "status.*:.*success" whereami.txt
SUCCESS=$?

if (( ${SUCCESS} == 0 )) ; then
    C=`grep countryCode whereami.txt | cut -f2 -d':'`
    if [ -n ${C} ] ; then
        C=${C:1:-1} # strip quotes 
    fi
    ST=`grep regionName whereami.txt | cut -f2 -d':'`
    if [ -n "${ST}" ] ; then
        ST=${ST:1:-1} # strip quotes 
    fi
    L=`grep city whereami.txt | cut -f2 -d':'`
    if [ -n "${L}" ] ; then
        L=${L:1:-1} # strip quotes 
    fi
fi
rm -f whereami.txt

# Values for standard cert stuff
C=${C:-'IO'}
ST=${ST:-'Not in'}
L=${L:-'Kansas'}
O='OpenRVDAS'
OU='DAS'

DOMAIN=`hostname -d`
IP=`hostname -I`
WILDCARD="*.${DOMAIN}"

COMMON_NAME=${HOSTNAME}
SAN_NAME_1=${HOSTNAME}
SAN_NAME_2=localhost
SAN_NAME_3=${WILDCARD}
SERVER_IP_1=${IP}
SERVER_IP_2=127.0.0.1
SERVER_IP_3=127.0.1.1

# Script will generate a SAN enabled wildcard Cert
function generate_self_signed_ca() {
    echo "Generaing domain key"
    echo "Generaing domain key" >&2
    openssl genrsa -out ${DOMAIN}.key 4096
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating domain key"
        echo "See debug.log for more details"
        return
    fi

    echo "Generaing domain certificate"
    openssl req -x509 -new -nodes -sha512 -days 3653 \
    -subj "/C=${C}/ST=${ST}/L=${L}/O=${O}/OU=${OU}/CN=${COMMON_NAME}" \
    -key ${DOMAIN}.key \
    -out ${DOMAIN}.crt
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating domain cert"
        echo "See debug.log for more details"
    fi
}

function generate_server_certificate() {
    echo "Generaing server key"
    echo >&2
    echo "Generaing server key" >&2
    openssl genrsa -out openrvdas.key 4096 
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating server key"
        echo "See debug.log for more details"
        return
    fi

    echo "Generaing Certificate Signing Request"
    echo >&2
    echo "Generaing Certificate Signing Request" >&2
    openssl req -sha512 -new \
        -subj "/C=${C}/ST=${ST}/L=${L}/O=${O}/OU=${OU}/CN=${COMMON_NAME}" \
        -key openrvdas.key \
        -out openrvdas.csr
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating CSR"
        echo "See debug.log for more details"
        return
    fi

# For future consideration, consider OCSP, too
    echo >&2
    echo "Creating v3 extentions file" >&2
cat > v3.ext <<-EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1=${SAN_NAME_1}
DNS.2=${SAN_NAME_2}
DNS.3=${SAN_NAME_3}
IP.1=${SERVER_IP_1}
IP.2=${SERVER_IP_2}
IP.3=${SERVER_IP_3}
EOF

    echo "Signing request"
    echo >&2
    echo "Signing request" >&2
    openssl x509 -req -sha512 -days 3653 \
        -extfile v3.ext \
        -CA ${DOMAIN}.crt -CAkey ${DOMAIN}.key -CAcreateserial \
        -in openrvdas.csr \
        -out openrvdas.cert
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error signing request"
        echo "See debug.log for more details"
        return
    fi
    rm -f ${DOMAIN}.srl
    rm -f openrvdas.csr
    rm -f v3.ext

    echo "Converting PEM to crt"
    echo >&2
    echo "Converting PEM to crt" >&2
    openssl x509 -inform PEM -in openrvdas.cert -out openrvdas.crt
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error converting PEM to cert"
        echo "See debug.log for more details"
        return
    fi
    rm -f openrvdas.cert
}

function copy_certificates_to_destination() {
    mkdir -p ${CERT_DIR}
    cp ${CERTS_DIR}/${FILE_NAME}.crt ${CERT_DIR}
    cp ${CERTS_DIR}/${FILE_NAME}.key ${CERT_DIR}
}

function update_cert_store() {
    # I think we should be ruuning as a user, but
    # if we are running as root or script is running sudo, do not sudo
    # SUDO=''
    # if ${UID} != 0 SUDO='/usr/bin/sudo'

    # Get OS flavor, ask if cannot determine
    SUDO="/usr/bin/sudo"
    determine_flavor
    [ -n ${OS_TYPE} ] || ask_os_type

    if [ $OS_TYPE == 'Ubuntu' ] ; then
        DEST=/usr/local/share/ca-certificates
        ${SUDO} /bin/cp ${DOMAIN}.crt ${DEST}
        ${SUDO} update-ca-certificates  # what's the path?
    fi

    if [ $OS_TYPE == 'CentOS' ] ; then
        DEST=/etc/pki/ca-trust/source/anchors
        ${SUDO} /bin/cp ${DOMAIN}.crt ${DEST}
        ${SUDO} /usr/bin/update-ca-trust
    fi

    if [ $OS_TYPE == 'Darwin' ] ; then
        # Darwin (note: no way to test this on my laptop):
        KEYCHAINS='/System/Library/Keychains'
        ROOTCERTS='SystemRootCertificates.keychain'
        KEYCHAIN="${KEYCHAINS}/${ROOTCERTS}"
        ${SUDO} security add-trusted-cert -k ${KEYCHAIN} ${DOMAIN}.crt
    fi
}

function ask_os_type {
    declare -A allowed
    allowed[CentOS]=CentOS
    allowed[Ubuntu]=Ubuntu
    allowed[Darwin]=Darwin
    echo "Cannot determine the OS Type.  Please select"
    while [ -z ${OS_TYPE} ] ; do
        read -p "(CentOS, Ubuntu, Darwin): " reply
        [ -z "${reply}" ] && reply="Argabarg"   # Blank indexes bad
        [[ ${allowed[$reply]+_} ]] && OS_TYPE=$reply
    done
}

function determine_flavor {
    # We don't need to check versions because they're already
    # running OpenRVDAS.  So just get the flavor.
    if [ `uname -s` == 'Darwin' ] ; then
        OS_TYPE=MacOS
        return
    fi
    LIKE=`grep -i "id_like" /etc/os-release`
    # This will work on Fedora, Rocky, RHEL, CentOS, etc.
    [[ ${LIKE} =~ 'rhel' ]] && OS_TYPE='CentOS'
    # This will work on debian, ubuntu, RaspiOS, etc...
    [[ ${LIKE} =~ 'debian' ]] && OS_TYPE='Ubuntu'
    # SUSE/OpenSUSE say "suse" in the id_like
}

if [ -f openrvdas.crt -a -f openrvdas.key ] ; then
    echo "************************************************************"
    echo
    echo "    openrvdas.key and openrvdas.crt alredy exist."
    echo "    If you really want to generate a new cert,"
    echo "    delete/rename the one ones"
    echo
    echo "************************************************************"
    exit
fi

generate_self_signed_ca
generate_server_certificate
# echo "some pithy prompt"
# read reply until reply in yes/no
# if yes, 'update_cert_store'

