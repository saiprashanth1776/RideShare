import pika
import json
import sys
from requests import post

def do_master_work(ch, method, properties, body):
    global sync_channel
    url = "http://persdb:8500"
    print(" [x] Received %r" % body)
    request = json.loads(body) #deserialize the string to a JSON
    if (request['query'] == 'clear'):
        result = post(url+"/internal/v1/db/clear")
    else:
        result = post(url+"/internal/v1/db/write",json=request)
    if (result.status_code == 200): #action is successful
        output_structure = {'request':request}
        #send message to syncQ
        print("SYNCHRONIZE")
        sync_channel.basic_publish(exchange='syncQ',routing_key='',body = json.dumps(output_structure))
    ch.basic_publish(exchange='',routing_key=properties.reply_to,properties=pika.BasicProperties(correlation_id = properties.correlation_id),body=json.dumps({"data":result.json(),"status":result.status_code})) #uses reply_to to send it back to the RPC
    ch.basic_ack(delivery_tag=method.delivery_tag) #Acknowledge the message


connection = pika.BlockingConnection(pika.ConnectionParameters(host='bunny'))
write_channel = connection.channel()
write_channel.queue_declare("writeQ")
write_channel.basic_consume(queue = 'writeQ', on_message_callback = do_master_work)
sync_channel = connection.channel()
sync_channel.exchange_declare(exchange = "syncQ",exchange_type='fanout') #fanout exhange to allow multiple consumers to get the message
print("MASTER",file=sys.stdout)
write_channel.start_consuming()
