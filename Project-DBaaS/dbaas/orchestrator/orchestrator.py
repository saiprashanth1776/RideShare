import json
import os
import time
import traceback
import uuid
from datetime import datetime
from logging.config import dictConfig
from multiprocessing import Value

import atexit
from apscheduler.schedulers.background import BackgroundScheduler

import docker
import pika
from flask import Flask, request
from flask_restful import Api, Resource
from requests import get, post

import enum
import sys
from kazoo.client import KazooClient

zk = KazooClient(hosts='zook:2181')
zk.start()
#if any nodes exist from previous run
if zk.exists('/slavecount'):
    zk.delete('/slavecount')
if zk.exists('/conts'):
    zk.delete('/conts', recursive = True)
#create slavecount node with no data
zk.create('/slavecount')

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

connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
channel_r = connection.channel()
channel_r.queue_declare("readQ")
channel_w = connection.channel()
channel_w.queue_declare("writeQ")

counter = Value('i', 0)


class JOB(enum.Enum):
    NONE = 0
    MASTER = 1
    SLAVE = 2
    SYNC = 3

#triggered when master node crashes
def watchmaster(event):
    client = docker.from_env()
    cls = client.containers.list(filters={"ancestor": "worker"})
    min_pid_ip = None
    min_pid = sys.maxsize
    for cont in cls:
        ip_add = cont.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']
        res = get("http://" + ip_add + "/control/v1/getstatus")
        if res.json()[0] == JOB.SLAVE.value:
            d = dict(cont.top())
            pid = int(d["Processes"][0][2]) if d["Processes"][0][0] == "root" else int(d["Processes"][0][0])
            if (pid < min_pid):
                min_pid_ip = ip_add
                min_pid = pid
    #selection of lowest pid slave
    if min_pid != sys.maxsize:
        get("http://" + min_pid_ip + "/control/v1/stop") #remove role as slave
        res = post("http://" + min_pid_ip + "/control/v1/start", json = { 'job': JOB.MASTER.value, 'pid': min_pid }) #change role to master
        if res.status_code != 200:
            raise Exception("Setting container job did not succeed.")
        zk.get('/conts/cont_' + str(min_pid), watch = watchmaster) #set new watch on this node as master
        spawn_container(JOB.SLAVE) #spawn new slave

#triggered when slave crashes or role changes to master (deleted and recreated same znode)
def watchslave(event):
    time.sleep(2) #wait if slave is just being changed to master and not deleted
    if not zk.exists(event.path): #only if deleted
        cur_count = len(zk.get_children('/conts')) -1 #dont include master

        data, stat = zk.get('/slavecount')
        slavecount = int(data.decode("utf-8"))
        if cur_count < slavecount: #spawn only if slaves dipped below number of required
            spawn_container(JOB.SLAVE)
        


def spawn_container(job_id):
    global zk
    client = docker.from_env()
    container = client.containers.run("worker", detach=True, network="dbaas-net")
    time.sleep(5)  # Wait till container starts up

    # Get container object with updated information post startup (e.g. container IP Address)
    container = client.containers.get(container.id)

    # Getting IP address of this new container.
    ip_add = container.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']

    # Why not use container name?
    # For some reason does not work! Very weird behavior.
    # What's weirder is that if we give a custom name to the container while creating it,
    # then using container name here works?!
    d = dict(container.top())
    pid = int(d["Processes"][0][2]) if d["Processes"][0][0] == "root" else int(d["Processes"][0][0])

    res = post("http://" + ip_add + "/control/v1/start", json = { 'job': job_id.value, 'pid': pid })
    if res.status_code != 200:
        raise Exception("Setting container job did not succeed.")
    watchfun = None #set watch function according to job id
    if job_id.value == 1:
        watchfun = watchmaster
    elif job_id.value == 2:
        watchfun = watchslave
    zk.get('/conts/cont_' + str(pid), watch = watchfun) #set watch on node
    app.logger.info("Spawned Container with Job %s (IP: %s)", job_id, ip_add)


def scaling():
    with counter.get_lock():
        global zk
        no_of_slaves = int((counter.value-1)/20)+1
        zk.set('/slavecount', str(no_of_slaves).encode('utf-8')) #set new value of slavecount
        app.logger.info("Required no. of slaves: %s", no_of_slaves)
        client = docker.from_env()
        cls = client.containers.list(filters={"ancestor": "worker"})
        cur_count = 0
        for cont in cls:
            ip_add = cont.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']
            res = get("http://" + ip_add + "/control/v1/getstatus")
            if res.json()[0] == JOB.SLAVE.value:
                cur_count += 1
        dif = cur_count-no_of_slaves
        app.logger.info("Current no. of slaves: %s", cur_count)
        s = "Spawning "+str(abs(dif))+" new slaves " if dif <= 0 else "Removing "+str(dif)+" slaves"
        app.logger.info(s)

        while dif < 0:
            # Scale Up!
            spawn_container(JOB.SLAVE)  # Make a new slave container
            dif += 1

        i = 0
        while dif > 0 and i < len(cls):
            # Remove slave containers
            container = cls[i]
            ip_add = container.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']
            res = get("http://" + ip_add + "/control/v1/getstatus")
            if res.json()[0] == JOB.SLAVE.value:
                app.logger.info("Removing Slave Container with name: %s", container.name)
                container.remove(force=True)
                dif -= 1
            i += 1
        counter.value = 0


@app.before_first_request
def start_timer():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=scaling, trigger="interval", seconds=120)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())


class ReadRpcClient(object): #Reading API call
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
        self.channel = self.connection.channel()
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(queue=self.callback_queue, on_message_callback=self.on_response, auto_ack=True)

    def on_response(self, ch, method, props, body): #upon response of a message callback
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body)

    def call(self, request):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        #publish onto the readQ with a reply_to queue (required since this is an RPC)
        self.channel.basic_publish(
            exchange='',
            routing_key='readQ',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps(request))
        retries = 0
        while self.response is None:
            if (retries == 5): #if unable to get a response within 5 retries, consider non available worker and return 503
                break
            retries += 1
            self.connection.process_data_events() #continue with any other events to process
            time.sleep(0.5 * retries) #back off for the RPC

        if (self.response):
            return self.response["data"], self.response["status"] #return data to client
        else:
            return {}, 503  # service unavailable


class WriteRpcClient(object): #write API call
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
        self.channel = self.connection.channel()
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(queue=self.callback_queue, on_message_callback=self.on_response, auto_ack=True)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body)

    def call(self, request):

        self.response = None
        self.corr_id = str(uuid.uuid4())
        #publish message to the writeQ (needs a reply_to since this is an RPC)
        self.channel.basic_publish(
            exchange='',
            routing_key='writeQ',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps(request))
        retries = 0
        while self.response is None:
            if (retries == 5): #try 5 times before quitting
                break
            retries += 1
            self.connection.process_data_events()
            time.sleep(0.5 * retries) #backoff for waiting time
        if (self.response):
            return self.response["data"], self.response["status"] #return data to the client
        else:
            return {}, 503  # service unavailable


# @app.after_request
def after(response):
    with open("orchestrator_logs.csv", 'a') as log:
        if os.stat("orchestrator_logs.csv").st_size == 0:
            print('Type;Path;Request Body;;Response Code;Response Body', file=log)
        else:
            print(request.method, end=";", file=log)
            print(request.path, end=";", file=log)
            # print(str(request.headers).strip(), end=";",file=log)
            print(request.json, end=";", file=log)
            print(response.status, end=";", file=log)
            # print(response.headers, end=";", file=log)
            print(response.json, file=log)
    return response


def mydatetime(value):
    datetime.strptime(value, '%d-%m-%Y:%S-%M-%H')
    return value


class DBWrite(Resource):
    def post(self):
        # write request received, add to the writeQ

        writer = WriteRpcClient()
        response = writer.call(request.get_json()) # RPC
        return response


class DBRead(Resource):
    def post(self):
        # read request received, add to the readQ

        # Incrementing Read API Count (this is thread and process safe)
        with counter.get_lock():
            counter.value += 1
            app.logger.info("Read API Count: %s", counter.value)

        reader = ReadRpcClient()
        response = reader.call(request.get_json()) #RPC
        return response


class DBClear(Resource):
    def post(self):
        # clear request (write), add to the writeQ
        data = {"query": "clear"}
        writer = WriteRpcClient()
        response = writer.call(data) #RPC
        return response


class WorkerList(Resource):
    def get(self):
        client = docker.from_env()
        cls = client.containers.list(filters={"ancestor": "worker"})
        pids = []
        for cont in cls:
            d = dict(cont.top())
            pids.append(int(d["Processes"][0][2]) if d["Processes"][0][0] == "root" else int(d["Processes"][0][0]))
        return sorted(map(int, pids))


class CrashMaster(Resource):
    def post(self):
        client = docker.from_env()
        cls = client.containers.list(filters={"ancestor": "worker"})
        for cont in cls:
            ip_add = cont.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']
            res = get("http://" + ip_add + "/control/v1/getstatus")
            app.logger.info(res)
            if res.json()[0] == JOB.MASTER.value:
                # Get PID
                d = dict(cont.top())
                pid = int(d["Processes"][0][2]) if d["Processes"][0][0] == "root" else int(d["Processes"][0][0])
                app.logger.info("Crash Master with PID: %s", pid)
                # Crash Master
                cont.remove(force=True)
                return [pid]
        return {}, 400  # No master found


class CrashSlave(Resource):
    def post(self):
        client = docker.from_env()
        cls = client.containers.list(filters={"ancestor": "worker"})
        max_pid_cont = None
        max_pid = -1
        for cont in cls:
            ip_add = cont.attrs['NetworkSettings']['Networks']['dbaas-net']['IPAddress']
            res = get("http://" + ip_add + "/control/v1/getstatus")
            if res.json()[0] == JOB.SLAVE.value:
                # Get PID
                d = dict(cont.top())
                pid = int(d["Processes"][0][2]) if d["Processes"][0][0] == "root" else int(d["Processes"][0][0])
                # Check if pid higher than max pid
                if (pid > max_pid):
                    max_pid_cont = cont
                    max_pid = pid
        if max_pid != -1:
            # Crash Slave
            app.logger.info("Crashed Slave with PID: %s", max_pid)
            max_pid_cont.remove(force=True)
            return [max_pid]
        return {}, 400  # No slave found


@app.route("/cleanup", methods=['DELETE'])
def destroy_containers():
    print("Doing container clean up.")
    client = docker.from_env()
    cls = client.containers.list(filters={"ancestor": "worker"})
    for cont in cls:
        cont.remove(force=True)
    return {}, 200


api.add_resource(DBWrite, '/api/v1/db/write')
api.add_resource(DBRead, '/api/v1/db/read')
api.add_resource(DBClear, '/api/v1/db/clear')
api.add_resource(WorkerList, '/api/v1/worker/list')
api.add_resource(CrashMaster, '/api/v1/crash/master')
api.add_resource(CrashSlave, '/api/v1/crash/slave')

if __name__ == '__main__':
    try:
        # Spawning one master and slave container each to begin with
        spawn_container(JOB.MASTER)
        spawn_container(JOB.SLAVE)
        app.run(host='0.0.0.0', port=9500, debug=True, use_reloader=False)
    except Exception:
        print(traceback.format_exc())
    finally:
        # Always clean up spawned containers
        destroy_containers()
