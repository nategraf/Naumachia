from flask import Flask, abort, request
from os import path, environ
from datetime import datetime
import os
import registrar
import json

script_dir = path.dirname(__file__)

app = Flask(__name__)

port                = int(environ.get("REGISTRAR_PORT", 3960))
app.secret_key      = environ.get("REGISTRAR_SECRET", "K2ptdnpfjLnFrA2c")
#cert_path           = environ.get("CERT_PATH", "/certs/localhost.cert")
#key_path            = environ.get("KEY_PATH", "/certs/localhost.key")

registrars = {}

@app.route('/<chal>/<action>')
def register(chal, action):
    try:
        regi = registrars[chal]
    except KeyError:
        abort(404)

    try:
        if action == 'add':
            result = regi.add_cert(request.args['cn'])
        elif action == 'get':
            result = regi.get_config(request.args['cn'])
        elif action == 'list':
            result = regi.list_certs(request.args.get('cn', None))
        elif action == 'revoke':
            result = regi.revoke_cert(request.args['cn'])
        elif action == 'remove':
            result = regi.remove_cert(request.args['cn'])
        else:
            abort(400)
    except KeyError:
        abort(400)
    except registrar.EntryNotFoundError:
        abort(404)

    return json.dumps(result, cls=registrar.RegistrarEncoder)

if __name__ == '__main__':
    for dirname in os.listdir(registrar.OPENVPN_BASE):
        registrars[dirname] = registrar.Registrar(dirname)

    app.run(debug=True, host='0.0.0.0', port=port)# ssl_context=(cert_path, key_path))
