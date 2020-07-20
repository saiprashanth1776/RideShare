import os
from datetime import datetime
from logging.config import dictConfig

import flask_restful
from database import execute, fetchall
from flask import Flask, request, current_app, abort,send_file
from flask_restful import Api, Resource, reqparse
from werkzeug.exceptions import HTTPException
import threading
filelock = threading.Lock()
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi']
    }
})
app = Flask(__name__)
api = Api(app)

@app.after_request
def after(response):
    with open("persistent_db_log.csv", 'a') as log:
        if os.stat("persistent_db_log.csv").st_size == 0:
            print('Type;Path;Request Body;Response Code;Response Body', file=log)
        else:
            print(request.method, end=";", file=log)
            print(request.path, end=";", file=log)
            # print(str(request.headers).strip(), end=";",file=log)
            print(request.json, end=";", file=log)
            print(response.status, end=";", file=log)
            # print(response.headers, end=";", file=log)
            print(response.json, file=log)
    return response


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

class DBWrite(Resource):
    def __init__(self):
        self.reqparser = RequestParser()
        self.reqparser.add_argument(Argument('query', type=str, required=True))
        self.reqparser.add_argument(Argument('table', type=str, required=True))
        self.reqparser.add_argument(Argument('values', type=dict))
        self.reqparser.add_argument(Argument('condition', type=dict))
        super(DBWrite, self).__init__()

    def post(self):
        global filelock
        args = self.reqparser.parse_args()
        query = args['query']
        table = args['table']
        if query == 'insert':
            if 'values' in args:
                values = args['values']
                insert_query = '''
                    INSERT INTO ''' + table + '(' + ','.join(values.keys()) + ') ' + '''
                    VALUES ''' + '(' + ','.join(map(repr, values.values())) + ')'
                filelock.acquire()
                if execute(insert_query):
                    filelock.release()
                    return {}, 200
                filelock.release()
            return {}, 400

        elif query == 'delete':
            if 'condition' in args:
                condition = args['condition']
                delete_query = '''
                    DELETE FROM ''' + table + '''
                    WHERE ''' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(), condition.values()))
                filelock.acquire()
                execute(delete_query)
                filelock.release()
                return {}, 200
            return {}, 400

        elif query == 'update':
            if 'condition' in args:
                condition = args['condition']
                valuesz = args['values']
                update_query = '''
                    UPDATE ''' + table + ''' 
                    SET ''' + ','.join(map(lambda x, y: x + ' = ' + y, valuesz.keys(), valuesz.values())) + ''' 
                    WHERE ''' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(), condition.values()))
                filelock.acquire()
                execute(update_query)
                filelock.release()
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
        global filelock
        tables = ["rides", "riders", "users"]
        for table in tables:
            delete_query = '''
            DELETE FROM ''' + table
            filelock.acquire()
            execute(delete_query)
            filelock.release()
        query = '''UPDATE APICOUNT SET COUNT=0'''
        filelock.acquire()
        execute(query)
        filelock.release()
        return {}, 200

class getDB(Resource):
    def get(self):
        global filelock
        filelock.acquire()
        res = send_file("persistent.db")
        filelock.release()
        return res

api.add_resource(DBWrite, '/internal/v1/db/write')
api.add_resource(DBRead, '/internal/v1/db/read')
api.add_resource(DBClear, '/internal/v1/db/clear')
api.add_resource(getDB, '/internal/v1/getdb')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8500,debug=True)
