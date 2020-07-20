import pika
from database import execute, fetchone, fetchall
import json

def do_synchronize(ch,method,properties,body):
    #sync local dbase for eventual consistency
    action = json.loads(body)['request'] #deserialize the body
    print("SYNCHRO RECEIVED")
    print(action)
    if (action['query'] == "clear"):
        db_clear()
    else:
        CONDITION = None
        VALUES = None
        QUERY = action["query"]
        TABLE = action["table"]
        if ("condition" in action):
            CONDITION = action["condition"]
        if ("values" in action):
            VALUES = action["values"]
        db_write(QUERY,TABLE,VALUES,CONDITION)

    ch.basic_ack(delivery_tag=method.delivery_tag) #Acknowledge the message

def db_clear():
    tables = ["rides", "riders", "users"]
    for table in tables:
        delete_query = '''
        DELETE FROM ''' + table
        execute(delete_query)
    query = '''UPDATE APICOUNT SET COUNT=0'''
    execute(query)
    return {}, 200

def db_write(query,table,values=None,condition=None):
    query = query
    table = table
    if query == 'insert':
        if values:
            #values = values
            insert_query = '''
                INSERT INTO ''' + table + '(' + ','.join(values.keys()) + ') ' + '''
                VALUES ''' + '(' + ','.join(map(repr, values.values())) + ')'
            if execute(insert_query):
                return 200
        return 400
    elif query == 'delete':
        if condition:
            delete_query = '''
                DELETE FROM ''' + table + '''
                WHERE ''' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(), condition.values()))
            execute(delete_query)
            return 200
        return 400
    elif query == 'update':
        if condition:
            update_query = '''
                       UPDATE ''' + table + ''' 
                       SET ''' + ','.join(map(lambda x, y: x + ' = ' + y, values.keys(), values.values())) + ''' 
                       WHERE ''' + ' AND '.join(map(lambda x, y: x + '=' + repr(y), condition.keys(), condition.values()))
            execute(update_query)
            return 200
        return 400

connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
sync_channel = connection.channel()
r = sync_channel.queue_declare("",exclusive=True)
sync_channel.exchange_declare(exchange = "syncQ",exchange_type='fanout') #fanout exchange to allow multiple consumers to receive the message simultaneously
sync_channel.queue_bind(exchange='syncQ',queue=r.method.queue,routing_key='')
sync_channel.basic_consume(queue = r.method.queue, on_message_callback = do_synchronize)
print("SYNCHRO")
sync_channel.start_consuming()
