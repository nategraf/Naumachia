from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
import logging
import subprocess
import sys

logging.basicConfig(level=logging.DEBUG)

EASYRSA_ALREADY_EXISTS_MSG = b'Request file already exists'

def ovpn_config(cn):
    logging.info("Client configuration Request recieved for '{}'".format(cn))
    try:
        subprocess.check_output(['easyrsa', 'build-client-full', cn, 'nopass'], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and EASYRSA_ALREADY_EXISTS_MSG in e.stderr:
            logging.info("Using existing certs for '{}'".format(cn))
        else:
            logging.error("Building certs for '{}' failed with exit code {} : EXITING".format(cn, e.returncode))
            raise RuntimeError("'easyrsa build-client-full' commnad returned error code {}".format(e.returncode)) from e
    else:
        logging.info("Built new certs for '{}'".format(cn))

    try:
        return subprocess.check_output(['getclient', cn])
    except subprocess.CalledProcessError as e:
        raise RuntimeError("'getclient' command returned error code {}".format(e.returncode)) from e

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

if __name__ == "__main__":
    # Create server
    server = SimpleXMLRPCServer(("0.0.0.0", 3960), requestHandler=RequestHandler)
    server.register_introspection_functions()
    server.register_function(ovpn_config)
    server.serve_forever()
