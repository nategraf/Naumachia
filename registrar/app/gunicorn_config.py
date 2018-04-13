import os

# Get the environment variables
REGISTRAR_PORT = int(os.environ.get("REGISTRAR_PORT", 3960))
REGISTRAR_ACCESS_LOG = os.environ.get("REGISTRAR_ACCESS_LOG", "/var/log/gunicorn/access.log")
REGISTRAR_ERROR_LOG = os.environ.get("REGISTRAR_ERROR_LOG", "/var/log/gunicorn/error.log")

# Workers and binding
workers = 1
bind = "0.0.0.0:{:d}".format(REGISTRAR_PORT)

# Configure logging
os.makedirs(os.path.dirname(REGISTRAR_ACCESS_LOG), exist_ok=True)
os.makedirs(os.path.dirname(REGISTRAR_ERROR_LOG), exist_ok=True)
accesslog=REGISTRAR_ACCESS_LOG
errorlog=REGISTRAR_ERROR_LOG
