from flask import Flask, abort, request
from os import path, environ
from datetime import datetime
import os
import registrar
import json

app = Flask(__name__)

app.secret_key = environ.get("REGISTRAR_SECRET", os.urandom(16))
REGISTRAR_PORT = int(environ.get("REGISTRAR_PORT", 3960))

# Initialize the dict of registrars
registrars = {}
for dirname in os.listdir(registrar.OPENVPN_BASE):
    registrars[dirname] = registrar.Registrar(dirname)

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
    # TODO(add blacklist error)

    return json.dumps(result, cls=registrar.RegistrarEncoder)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=REGISTRAR_PORT)
