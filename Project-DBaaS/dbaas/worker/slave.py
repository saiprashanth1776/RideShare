import pika
from database import execute, fetchone, fetchall
import json
import sys

def db_read(table,columns,condition=None):
    if columns:
        select_query = '''
            SELECT ''' + ','.join(columns) + '''
            FROM ''' + table + '''
            ''' + ('WHERE ' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(),
                                                condition.values())) if condition else '')
        rows = fetchall(select_query)
        res = []
        if rows:
            for row in rows:
                res.append({columns[i]: row[i] for i in range(len(columns))})
        return res, 200
    return {}, 400

def do_slave_work(ch, method, properties, body):
    #global response_channel
    print(" [x] Received %r" % body)
    request = json.loads(body) #deserialize the string to a JSON
    if ("condition" in request):
        result = db_read(request["table"],request['columns'],request['condition']) #perform the actual read
    else:
        result = db_read(request["table"],request['columns'])
    output_structure = {'status':result[1],'data':result[0]}
    #publish the output to the reply_to queue (RPC) in order to return data
    ch.basic_publish(exchange='',routing_key=properties.reply_to,properties=pika.BasicProperties(correlation_id = properties.correlation_id),body=json.dumps(output_structure))
    ch.basic_ack(delivery_tag=method.delivery_tag) #Acknowledge the message


connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
read_channel = connection.channel()
read_channel.queue_declare("readQ")
read_channel.basic_consume(queue = 'readQ', on_message_callback = do_slave_work)
print("SLAVE",file=sys.stdout)
read_channel.start_consuming()
