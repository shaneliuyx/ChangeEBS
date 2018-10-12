import boto3

# Get the service resource, in this case SQS Resource from boto3 module
sqs = boto3.resource('sqs')

# Create a new queue named test passing a few attributes, in this case just DelaySeconds
#queue = sqs.create_queue(QueueName='test', Attributes={'DelaySeconds': '5'})
queue = sqs.create_queue(QueueName='test')
# We can now access identifiers and attributes
print(queue.url)
print(queue.attributes.get('DelaySeconds'))

response = queue.send_message(
    MessageBody='https://s3.cn-north-1.amazonaws.com.cn/shane/change_ebs_type.json')
queue = sqs.get_queue_by_name(QueueName='test')
for message in queue.receive_messages():
    print(message.body)
    #   message.delete()
