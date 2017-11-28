from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from registrar import ovpn_config

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

if __name__ == "__main__":
    # Create server
    server = SimpleXMLRPCServer(("0.0.0.0", 3960), requestHandler=RequestHandler)
    server.register_introspection_functions()
    server.register_function(ovpn_config)
    server.serve_forever()
