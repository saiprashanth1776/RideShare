from datetime import datetime

from flask import Flask, jsonify, request, current_app, abort
from flask_restful import Api, Resource, reqparse
import pandas as pd
import flask_restful
from requests import post, get
from werkzeug.exceptions import HTTPException
import os

app = Flask(__name__)
api = Api(app)

USER_URL = "http://users"  # Needs to be replaced with load balancer URL while deploying
if (os.getenv("BALANCER") != None):
    USER_URL = "http://"+os.getenv("BALANCER")
    print("USER MODE SET TO CLOUD DEPLOYMENT")
else:
    print("USER MODE SET TO LOCAL DEPLOYMENT")

DB_URL = "http://orchestrator:9500"
if (os.getenv("ORCHHOST") != None and os.getenv("ORCHPORT") != None):
    DB_URL = "http://"+os.getenv("ORCHHOST")+":"+os.getenv("ORCHPORT")
    print("DB MODE SET TO CLOUD DEPLOYMENT")
else:
    print("DB MODE SET TO LOCAL DEPLOYMENT")
    
PUBLIC_IP_OF_RIDES = "http://localhost:8080"  # To set header for request to users service.
if (os.getenv("MYHOST") != None and os.getenv("MYPORT") != None):
    PUBLIC_IP_OF_RIDES = "http://"+os.getenv("MYHOST")+":"+os.getenv("MYPORT")
    print("HEADER MODE SET TO CLOUD DEPLOYMENT")
else:
    print("HEADER MODE SET TO LOCAL DEPLOYMENT")

@app.before_request
def log_request_info():
    if (request.path == '/api/v1/rides' or request.path.startswith('/api/v1/rides/')):
        #  Increment Count
        req = {
            'query': 'update',
            'table': 'apicount',
            'values': {
                'count': 'count + 1'
            },
            'condition': {
                'service_name': "rides"
            }
        }
        post(DB_URL + "/api/v1/db/write", json=req)


@app.after_request
def after(response):
    with open("rides_log.csv", 'a') as log:
        if os.stat("rides_log.csv").st_size == 0:
            print('Type;Path;Request Body;Incremented API Count?;Response Code;Response Body', file=log)
        if request.path == '/api/v1/db/write' or request.path == '/api/v1/db/read' or request.path == '/':
            pass
        else:
            print(request.method, end=";", file=log)
            print(request.path, end=";", file=log)
            # print(str(request.headers).strip(), end=";",file=log)
            print(request.json, end=";", file=log)
            if request.path == '/api/v1/rides' or request.path.startswith('/api/v1/rides/'):
                print("yes", end=";", file=log)
            else:
                print("no", end=";", file=log)
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


class Rides(Resource):
    def post(self):
        reqparser = RequestParser()
        reqparser.add_argument(Argument('created_by', type=str, required=True))
        reqparser.add_argument(Argument('timestamp', type=mydatetime, required=True))
        reqparser.add_argument(Argument('source', type=int, required=True))
        reqparser.add_argument(Argument('destination', type=int, required=True))
        args = reqparser.parse_args(strict=True)  # 400 if incorrect timestamp format, any extra/less fields
        created_by = args['created_by']
        timestamp = args['timestamp']
        source = args['source']
        destination = args['destination']

        # Check for username

        res = get(USER_URL + "/api/v1/users", headers={"Origin": PUBLIC_IP_OF_RIDES})
        if res.status_code == 204:
            return {}, 400  # no users

        matched = False
        for user in res.json():
            if user == created_by:
                matched = True
                break
        if (not matched):
            return {}, 400

        enum = pd.read_csv('AreaNameEnum.csv')
        if source in enum['Area No'] and destination in enum['Area No'] and source != destination:
            req = {
                'query': 'insert',
                'table': 'rides',
                'values': {
                    'created_by': created_by,
                    'timestamp': timestamp,
                    'source': source,
                    'destination': destination
                }
            }
            res1 = post(DB_URL + "/api/v1/db/write", json=req)
            if res1.status_code == 200:
                return {}, 201
        return {}, 400  # if source/destination same or incorrect or username doesnt exist

    def get(self):
        reqparser = RequestParser()
        reqparser.add_argument(Argument('source', location='args', type=int, required=True))
        reqparser.add_argument(Argument('destination', location='args', type=int, required=True))
        args = reqparser.parse_args(strict=True)
        source = args['source']
        destination = args['destination']

        enum = pd.read_csv('AreaNameEnum.csv')
        if source in enum['Area No'] and destination in enum['Area No'] and source != destination:
            req = {
                'table': 'rides',
                'columns': ['rideId', 'created_by', 'timestamp'],
                'condition': {
                    'source': source,
                    'destination': destination
                }
            }
            res = post(DB_URL + "/api/v1/db/read", json=req)
            res_json = [ride for ride in res.json() if
                        datetime.strptime(ride['timestamp'], '%d-%m-%Y:%S-%M-%H') > datetime.now()]
            for ride in res_json:
                ride['username'] = ride.pop('created_by')
            return res_json, (200 if res_json else 204)  # 204 if no rides
        return {}, 400  # if source/destination same or incorrect


class Ride(Resource):
    def get(self, id):
        if not request.get_json():
            req = {
                'table': 'rides',
                'columns': ['rideId', 'created_by', 'timestamp', 'source', 'destination'],
                'condition': {
                    'rideId': id
                }
            }
            res = post(DB_URL + "/api/v1/db/read", json=req)
            if res.json():
                res_json = res.json()[0]
                req = {
                    'table': 'riders',
                    'columns': ['user'],
                    'condition': {
                        'rideId': id
                    }
                }
                resr = post(DB_URL + "/api/v1/db/read", json=req)
                res_json['users'] = [i['user'] for i in resr.json()]
                return res_json, 200
            return {}, 204  # if no rides found
        return {}, 400  # if request json is not empty
        # idk 405 here

    def post(self, id):
        reqparser = RequestParser()
        reqparser.add_argument(Argument('username', type=str, required=True))
        args = reqparser.parse_args(strict=True)  # 400 if any extra or less fields
        username = args['username']

        # Get all usernames
        res = get(USER_URL + "/api/v1/users", headers={"Origin": PUBLIC_IP_OF_RIDES})

        # Checking if there are any usernames or not
        if res.status_code == 204:
            return {}, 400  # No usernames

        # Checking if user requesting to join ride is a valid user
        matched = False
        for user in res.json():
            if user == username:
                matched = True
                break
        if (not matched):
            return {}, 400  # username not found in list of usernames

        # Get details of ride being requested to join.
        req = {
            'table': 'rides',
            'columns': ['rideId', 'created_by'],
            'condition': {
                'rideId': id
            }
        }

        res = post(DB_URL + "/api/v1/db/read", json=req)

        for ride in res.json():
            if ride["created_by"] == username:  # user trying to join is ride creator
                return {}, 400

        if res.json():  # If this ride exists
            req = {
                'table': 'rides',
                'columns': ['created_by'],
                'condition': {
                    'created_by': username
                }
            }
            resr = post(DB_URL + "/api/v1/db/read", json=req)
            req = {
                'query': 'insert',
                'table': 'riders',
                'values': {
                    'rideId': id,
                    'user': username
                }
            }
            resw = post(DB_URL + "/api/v1/db/write", json=req)

            return {}, (200 if (resw.status_code == 200) else 400)
        return {}, 204  # ride not found

    def delete(self, id):
        if not request.get_json():
            req = {
                'table': 'rides',
                'columns': ['rideId'],
                'condition': {
                    'rideId': id
                }
            }
            res = post(DB_URL + "/api/v1/db/read", json=req)
            if res.json():
                req = {
                    'query': 'delete',
                    'table': 'riders',
                    'condition': {
                        'rideId': id
                    }
                }
                post(DB_URL + "/api/v1/db/write", json=req)
                req = {
                    'query': 'delete',
                    'table': 'rides',
                    'condition': {
                        'rideId': id
                    }
                }
                post(DB_URL + "/api/v1/db/write", json=req)
                return {}, 200
        return {}, 400  # if request json not empty or ride not found


class ReqCount(Resource):
    def get(self):
        req = {
            'table': 'apicount',
            'columns': ['count'],
            'condition': {
                'service_name': "rides"
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
                'service_name': "rides"
            }
        }
        res = post(DB_URL + "/api/v1/db/write", json=req)
        return {}, res.status_code

class RideCount(Resource):
    def get(self):
        req = {
            'table': 'rides',
            'columns': ['count(*)'],
        }
        res = post(DB_URL + "/api/v1/db/read", json=req)
        for row in res.json():
            return [row["count(*)"]], 200
        return {}, 400

class Health(Resource):
    def get(self):
        return 200

api.add_resource(Health, '/');
api.add_resource(Rides, '/api/v1/rides')
api.add_resource(Ride, '/api/v1/rides/<int:id>')
api.add_resource(ReqCount, '/api/v1/rides/_count')
api.add_resource(RideCount, '/api/v1/rides/count')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
