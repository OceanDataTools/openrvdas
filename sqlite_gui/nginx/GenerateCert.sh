#!/bin/bash

# Quick and dirty script to generaate a cert/key pair for nginx.


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

###### For generate_certs.sh script ######
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

## Script to generate a SAN Cert

function generate_self_signed_ca() {
    echo "Generaing domain key"
    openssl genrsa -out ${DOMAIN}.key 4096 2>/dev/null
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating domain key"
        return
    fi

    echo "Generaing domain certificate"
    openssl req -x509 -new -nodes -sha512 -days 3653 \
    -subj "/C=${C}/ST=${ST}/L=${L}/O=${O}/OU=${OU}/CN=${COMMON_NAME}" \
    -key ${DOMAIN}.key \
    -out ${DOMAIN}.crt 2>/dev/null
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating domain cert"
    fi
}

function generate_server_certificate() {
    echo "Generaing server key"
    openssl genrsa -out openrvdas.key 4096 2>/dev/null
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating server key"
        return
    fi

    echo "Generaing Certificate Signing Request"
    openssl req -sha512 -new \
        -subj "/C=${C}/ST=${ST}/L=${L}/O=${O}/OU=${OU}/CN=${COMMON_NAME}" \
        -key openrvdas.key \
        -out openrvdas.csr 2>/dev/null
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error creating CSR"
        return
    fi

# For future consideration, consider OCSP, too
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

    openssl x509 -req -sha512 -days 3653 \
        -extfile v3.ext \
        -CA ${DOMAIN}.crt -CAkey ${DOMAIN}.key -CAcreateserial \
        -in openrvdas.csr \
        -out openrvdas.cert 2>/dev/null
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error signing request"
        return
    fi
    rm -f ${DOMAIN}.srl
    rm -f openrvdas.csr
    rm -f v3.ext


    openssl x509 -inform PEM -in openrvdas.cert -out openrvdas.crt
    STATUS=$?
    if [ $STATUS != 0 ] ; then
        echo "Error converting PEM to cert"
        return
    fi
    rm -f openrvdas.cert

}

function copy_certificates_to_destination() {
    mkdir -p ${CERT_DIR}
    cp ${CERTS_DIR}/${FILE_NAME}.crt ${CERT_DIR}
    cp ${CERTS_DIR}/${FILE_NAME}.key ${CERT_DIR}
}

function update_linux_cert_store() {
    # This is for debian-style distros
    cp ${CERTS_DIR}/${FILE_NAME}.crt /usr/local/share/ca-certificates
    update-ca-certificates
}

generate_self_signed_ca
generate_server_certificate
#copy_certificates_to_destination


