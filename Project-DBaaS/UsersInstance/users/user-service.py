from datetime import datetime

from flask import Flask, jsonify, request, current_app, abort
from flask_restful import Api, Resource, reqparse
import flask_restful
from requests import post
from werkzeug.exceptions import HTTPException
import os

app = Flask(__name__)
api = Api(app)

DB_URL = "http://orchestrator:9500"
if (os.getenv("ORCHHOST") != None and os.getenv("ORCHPORT") != None):
    DB_URL = "http://"+os.getenv("ORCHHOST")+":"+os.getenv("ORCHPORT")
    print("MODE SET TO CLOUD DEPLOYMENT")
else:
    print("MODE SET TO LOCAL DEPLOYMENT")


@app.before_request
def log_request_info():
    if request.path == '/api/v1/users' or request.path.startswith('/api/v1/users/'):
        #  Increment Count
        req = {
            'query': 'update',
            'table': 'apicount',
            'values': {
                'count': 'count + 1'
            },
            'condition': {
                'service_name': "users"
            }
        }
        post(DB_URL + "/api/v1/db/write", json=req)


@app.after_request
def after(response):
    with open("users_log.csv", 'a') as log:
        if os.stat("users_log.csv").st_size == 0:
            print('Type;Path;Request Body;Incremented API Count?;Response Code;Response Body',file=log)
        if request.path == '/api/v1/db/write' or request.path == '/api/v1/db/read' or request.path=='/':
            pass
        else:
            print(request.method, end=";", file=log)
            print(request.path, end=";", file=log)
            # print(str(request.headers).strip(), end=";",file=log)
            print(request.json, end=";", file=log)
            if request.path == '/api/v1/users' or request.path.startswith('/api/v1/users/'):
                print("yes",end=";", file=log)
            else:
                print("no",end=";", file=log)
            print(response.status, end=";", file=log)
            # print(response.headers, end=";", file=log)
            print(response.json, file=log)
    return response


def sha1(value):
    if len(value) == 40:
        int(value, 16)
        return value
    raise ValueError('Length is not 40')


def mydatetime(value):
    datetime.strptime(value, '%d-%m-%Y:%S-%M-%H')
    return value

class Argument(reqparse.Argument):
    def handle_validation_error(self, error, bundle_errors):
        """Called when an error is raised while parsing. Aborts the request
        with a 400 status and an error message
        :param error: the error that was raised
        :param bundle_errors: do not abort when first error occurs, return a
            dict with the name of the argument and the error message to be
            bundled
        """
        # error_str = six.text_type(error)
        # error_msg = self.help.format(error_msg=error_str) if self.help else error_str
        # msg = {self.name: error_msg}
        msg = {}
        if current_app.config.get("BUNDLE_ERRORS", False) or bundle_errors:
            return error, msg
        # flask_restful.abort(400, message=msg)
        try:
            abort(400)
        except HTTPException as e:
            e.data = {}
            raise


class RequestParser(reqparse.RequestParser):
    def parse_args(self, req=None, strict=False, http_error_code=400):
        """Parse all arguments from the provided request and return the results
        as a Namespace
        :param req: Can be used to overwrite request from Flask
        :param strict: if req includes args not in parser, throw 400 BadRequest exception
        :param http_error_code: use custom error code for `flask_restful.abort()`
        """
        if req is None:
            req = request

        namespace = self.namespace_class()

        # A record of arguments not yet parsed; as each is found
        # among self.args, it will be popped out
        req.unparsed_arguments = dict(self.argument_class('').source(req)) if strict else {}
        errors = {}
        for arg in self.args:
            value, found = arg.parse(req, self.bundle_errors)
            if isinstance(value, ValueError):
                errors.update(found)
                found = None
            if found or arg.store_missing:
                namespace[arg.dest or arg.name] = value
        if errors:
            flask_restful.abort(http_error_code, message=errors)

        if strict and req.unparsed_arguments:
            # raise exceptions.BadRequest('Unknown arguments: %s'
            # % ', '.join(req.unparsed_arguments.keys()))
            try:
                abort(400)
            except HTTPException as e:
                e.data = {}
                raise

        return namespace


class Users(Resource):
    def put(self):
        reqparser = RequestParser()
        reqparser.add_argument(Argument('username', type=str, required=True))
        reqparser.add_argument(Argument('password', type=sha1, required=True))
        args = reqparser.parse_args(strict=True)  # 400 if extra or less fields, non sha1 password
        username = args['username']
        password = args['password']
        req = {
            'query': 'insert',
            'table': 'users',
            'values': {
                'username': username,
                'password': password
            }
        }
        res = post(DB_URL + "/api/v1/db/write", json=req)
        return {}, (201 if res.status_code == 200 else 400)  # 400 if insert fail

    def get(self):
        if not request.get_json():
            req = {
                'table': 'users',
                'columns': ['username']
            }
            res = post(DB_URL + "/api/v1/db/read", json=req)
            res_json = [user["username"] for user in res.json()]
            return res_json, (200 if res_json else 204)
        return {}, 400  # non empty request json or username doesnt exist
        # 405?


class User(Resource):
    def delete(self, username):
        if not request.get_json():
            req = {
                'table': 'users',
                'columns': ['username'],
                'condition': {
                    'username': username
                }
            }
            res = post(DB_URL + "/api/v1/db/read", json=req)
            if res.json():
                req = {
                    'query': 'delete',
                    'table': 'users',
                    'condition': {
                        'username': username
                    }
                }
                post(DB_URL + "/api/v1/db/write", json=req)
                return {}, 200
        return {}, 400  # non empty request json or username doesnt exist


class ReqCount(Resource):
    def get(self):
        req = {
            'table': 'apicount',
            'columns': ['count'],
            'condition': {
                'service_name': "users"
            }
        }
        res = post(DB_URL + "/api/v1/db/read", json=req)
        for row in res.json():
            return [row["count"]], 200
        return {}, 503


    def delete(self):
        #  Reset Count to 0
        req = {
            'query': 'update',
            'table': 'apicount',
            'values': {
                'count': '0'
            },
            'condition': {
                'service_name': "users"
            }
        }
        res = post(DB_URL + "/api/v1/db/write", json=req)
        return {}, res.status_code
    
class Health(Resource):
    def get(self):
        return 200

api.add_resource(Health, '/');
api.add_resource(Users, '/api/v1/users')
api.add_resource(User, '/api/v1/users/<string:username>')
api.add_resource(ReqCount, '/api/v1/users/_count')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
