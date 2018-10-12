import json
import zlib
import boto3
import botocore
import base64
import random
import string

TemplateURL = 'https://s3.cn-north-1.amazonaws.com.cn/shane/change_ebs_type.json'


def get_cloudtrail_event(event):
    data = base64.b64decode(event['awslogs']['data'])
    data = zlib.decompress(data, 16 + zlib.MAX_WBITS)
    cloudtrail_event = json.loads(data)
    return cloudtrail_event


def get_message_from_cloudtrail_event(log_event):
    old_str = '\\"'
    new_str = '"'
    message = log_event['message']
    message = message.replace(old_str, new_str)
    return json.loads(message)


def create_cloudformation(parameter1, parameter2, volume_id, client):
    stack_name = "change-ebs-type-" + volume_id
    print ("Create cloudformation stack: %s" % stack_name)
    response = client.create_stack(StackName=stack_name, TemplateURL=TemplateURL, Parameters=[
        {'ParameterKey': 'TargetEBSVolumeInfo', 'ParameterValue': parameter1}, {'ParameterKey': 'ScheduleExpression', 'ParameterValue': parameter2}, ], Capabilities=['CAPABILITY_IAM'])


def update_cloudformation(parameter1, parameter2, volume_id, client):
    stack_name = "change-ebs-type-" + volume_id
    print ("Update cloudformation stack: %s" % stack_name)
    try:
        response = client.update_stack(StackName=stack_name, UsePreviousTemplate=True, Parameters=[
            {'ParameterKey': 'TargetEBSVolumeInfo', 'ParameterValue': parameter1}, {'ParameterKey': 'ScheduleExpression', 'ParameterValue': parameter2}, ], Capabilities=['CAPABILITY_IAM'])
    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']
        if error_message == 'No updates are to be performed.':
            print("No changes")
        else:
            raise


def check_valid_stack(volume_id, client):
    response = client.describe_stacks()
    for stack in response['Stacks']:
        if stack['StackName'] == "change-ebs-type-" + volume_id:
            return True


def lambda_handler(event, context):
    volume_id = []
    client = boto3.client('cloudformation')
    print (event)
    cloudtrail_event = get_cloudtrail_event(event)
    for log_event in cloudtrail_event['logEvents']:
        trail_message = get_message_from_cloudtrail_event(log_event)
        volume_id = trail_message['requestParameters']['resourcesSet']['items'][0]['resourceId']
        for item in trail_message['requestParameters']['tagSet']['items']:
            if item['key'] == 'ChangeEBSType':
                cf_parameter = item['value']
                break

    type = cf_parameter.split(':')
    parameter1 = volume_id + ":" + type[0] + ":" + type[1]
    parameter2 = "cron" + type[2]
    print ("CloudForamtion template paraters:{},{}".format(
        parameter1, parameter2))
    print ("Volume %s will be changed to %s, IOPS is %s" %
           (volume_id, type[0], type[1]))
    print ("This task will be executed based on %s" % type[2])
    if check_valid_stack(volume_id, client):
        update_cloudformation(parameter1, parameter2,
                              volume_id, client)
        waiter = client.get_waiter('stack_update_complete')
    else:
        create_cloudformation(parameter1, parameter2,
                              volume_id, client)
        waiter = client.get_waiter('stack_create_complete')
