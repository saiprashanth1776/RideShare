import enum
import subprocess
from logging.config import dictConfig
from threading import Lock
import requests
from flask import Flask, request
from flask_api import status
from flask_restful import Api, Resource
from kazoo.client import KazooClient

zk = KazooClient(hosts='zook:2181')

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
mutex = Lock()
class JOB(enum.Enum):
    NONE = 0
    MASTER = 1
    SLAVE = 2
    SYNC = 3
job_type = JOB.NONE #worker is not started by default
listeners = dict()
job_dict = {0:JOB.NONE,1:JOB.MASTER,2:JOB.SLAVE,3:JOB.SYNC}

db = requests.get("http://persdb:8500/internal/v1/getdb") #getdb file while starting
if (db.status_code == 200):
    databasefile = open("data.db","wb")
    databasefile.write(db.content) #write to the db file
    databasefile.close()
else:
    app.logger.info("ERROR: Unable to retrieve DB")

sychro = subprocess.Popen(["python3","./synchro.py"]) #start synchronisation subprocess
class Start(Resource):
    def post(self):
        global job_type, mutex, listeners, app, zk
        args = request.get_json()
        job = args['job']
        pid = args['pid']
        myjob = JOB.NONE
        mutex.acquire()
        if (job_type != JOB.NONE):
            #already started return 403 forbidden
            mutex.release()
            return status.HTTP_403_FORBIDDEN
        else:
            job_type = job_dict[job]
            myjob = job_type
        mutex.release()
        zk.start() #start session only when job assigned
        zk.create('/conts/cont_' + str(pid), ephemeral = True, makepath = True) #ephemeral node deleted when session closed (crashed), makepath ensures /conts node is created first
        if (myjob == JOB.MASTER):
            app.logger.info('Starting Master')
            listeners[JOB.MASTER] = subprocess.Popen(["python3","./master.py"])    # launch master subprocess
        elif (myjob == JOB.SLAVE):
            app.logger.info("Starting Slave")
            listeners[JOB.SLAVE] = subprocess.Popen(["python3","./slave.py"])  # launch slave subprocess
        return status.HTTP_200_OK

class Stop(Resource):
    def get(self):
        global job_type, mutex,listeners,app, zk
        mutex.acquire() #mutex to protect against concurrent edits
        temp_job = None
        if (job_type == JOB.NONE):
            #not started return 403 forbidden
            mutex.release() 
            return status.HTTP_403_FORBIDDEN
        else:
            temp_job = job_type
            job_type = JOB.NONE
        mutex.release()
        if (temp_job == JOB.MASTER):
            listeners[JOB.MASTER].terminate() #terminate the subprocess
        else:
            if (temp_job == JOB.SLAVE):
                listeners[JOB.SLAVE].terminate() #terminate the subprocess
        zk.stop() #close session, triggering watch on slave
        return status.HTTP_200_OK


class GetStatus(Resource):
    def get(self):
        global job_type
        return [int(job_type.value)], status.HTTP_200_OK


api.add_resource(Start, "/control/v1/start")
api.add_resource(Stop, "/control/v1/stop")
api.add_resource(GetStatus, "/control/v1/getstatus")


if __name__ == "__main__":
    app.run(host="0.0.0.0",port = 80)
