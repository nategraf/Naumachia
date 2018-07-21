"""
Gunicorn config for the Naumachia registrar service

Options:
* BINDING_ADDR      (default: '0.0.0.0')
* BINDING_PORT      (default: 3960)
* ACCESS_LOG        (default: /var/log/gunicorn/access.log)
* ERROR_LOG         (default: /var/log/gunicorn/error.log)
* TLS_ENBALED       (default: False)
* TLS_VERIFY_CLIENT (default: False)
* TLS_KEY           (default: /etc/ssl/registrar.crt)
* TLS_CERT          (default: /etc/ssl/registrar.key)
* TLS_CA            (default: /etc/ssl/ca.crt)
"""

import os
import ssl

# Get the environment variables
BINDING_ADDR = os.environ.get('BINDING_ADDR', '0.0.0.0')
BINDING_PORT = int(os.environ.get('BINDING_PORT', 3960))
ACCESS_LOG = os.environ.get('ACCESS_LOG', '/var/log/gunicorn/access.log')
ERROR_LOG = os.environ.get('ERROR_LOG', '/var/log/gunicorn/error.log')

TLS_ENABLED = os.environ.get('TLS_ENABLED', 'False')
TLS_VERIFY_CLIENT = os.environ.get('TLS_VERIFY_CLIENT', 'False')
TLS_KEY = os.environ.get('TLS_KEY', '/etc/ssl/registrar.crt')
TLS_CERT = os.environ.get('TLS_CERT', '/etc/ssl/registrar.key')
TLS_CA = os.environ.get('TLS_CA', '/etc/ssl/ca.crt')

# Workers and binding
workers = 1
bind = '{:s}:{:d}'.format(BINDING_ADDR, BINDING_PORT)

# Configure logging
os.makedirs(os.path.dirname(ACCESS_LOG), exist_ok=True)
os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
accesslog=ACCESS_LOG
errorlog=ERROR_LOG

# Configure TLS
if TLS_ENABLED.lower() == 'true':
    keyfile = TLS_KEY
    certfile = TLS_CERT
    ca_certs = TLS_CA
    if TLS_VERIFY_CLIENT.lower() == 'true':
        cert_reqs = ssl.CERT_REQUIRED
