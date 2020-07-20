from datetime import datetime

from flask import Flask, jsonify, request, current_app, abort
from flask_restful import Api, Resource, reqparse
import flask_restful
from requests import post
from werkzeug.exceptions import HTTPException

from database import execute, fetchone, fetchall

app = Flask(__name__)
api = Api(app)

port = 80
URL = "http://localhost:"+str(port)


@app.before_request
def log_request_info():
    with open("request_log", 'a') as log:
        print(request.headers, request.get_data(), file=log)


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
        res = post(URL + "/api/v1/db/write", json=req)
        return {}, (201 if res.status_code == 200 else 400)  # 400 if insert fail

    def get(self):
        if not request.get_json():
            req = {
                'table': 'users',
                'columns': ['username']
            }
            res = post(URL + "/api/v1/db/read", json=req)
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
            res = post(URL + "/api/v1/db/read", json=req)
            if res.json():
                req = {
                    'query': 'delete',
                    'table': 'users',
                    'condition': {
                        'username': username
                    }
                }
                post(URL + "/api/v1/db/write", json=req)
                return {}, 200
        return {}, 400  # non empty request json or username doesnt exist


class DBWrite(Resource):
    def __init__(self):
        self.reqparser = RequestParser()
        self.reqparser.add_argument(Argument('query', type=str, required=True))
        self.reqparser.add_argument(Argument('table', type=str, required=True))
        self.reqparser.add_argument(Argument('values', type=dict))
        self.reqparser.add_argument(Argument('condition', type=dict))
        super(DBWrite, self).__init__()

    def post(self):
        args = self.reqparser.parse_args()
        query = args['query']
        table = args['table']

        if query == 'insert':
            if 'values' in args:
                values = args['values']
                insert_query = '''
                    INSERT INTO ''' + table + '(' + ','.join(values.keys()) + ') ' + '''
                    VALUES ''' + '(' + ','.join(map(repr, values.values())) + ')'
                if execute(insert_query):
                    return {}, 200
            return {}, 400

        elif query == 'delete':
            if 'condition' in args:
                condition = args['condition']
                delete_query = '''
                    DELETE FROM ''' + table + '''
                    WHERE ''' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(), condition.values()))
                execute(delete_query)
                return {}, 200
            return {}, 400


class DBRead(Resource):
    def post(self):
        args = request.get_json()
        table = args['table']
        if 'columns' in args:
            columns = args['columns']
            select_query = '''
                SELECT ''' + ','.join(columns) + '''
                FROM ''' + table + '''
                ''' + ('WHERE ' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), args['condition'].keys(),
                                                   args['condition'].values())) if 'condition' in args else '')
            rows = fetchall(select_query)
            res = []
            if rows:
                for row in rows:
                    res.append({columns[i]: row[i] for i in range(len(columns))})
            return res, 200
        return {}, 400


class DBClear(Resource):
    def post(self):
        tables = ["users"]
        for table in tables:
            delete_query = '''
            DELETE FROM ''' + table
            execute(delete_query)
        return {}, 200


api.add_resource(Users, '/api/v1/users')
api.add_resource(User, '/api/v1/users/<string:username>')
# api.add_resource(User, '/api/v1/users')
api.add_resource(DBWrite, '/api/v1/db/write')
api.add_resource(DBRead, '/api/v1/db/read')
api.add_resource(DBClear, '/api/v1/db/clear')


@app.after_request
def after(response):
    with open("response_log", 'a') as log:
        print(response.status, response.headers, response.get_data(), file=log)
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
