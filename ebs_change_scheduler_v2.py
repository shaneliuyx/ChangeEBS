import json
import zlib
import boto3
import botocore
import base64
import random
import string

TemplateURL = ""


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


def create_cloudformation(stack_name, parameter1, parameter2, volume_id, client):
    print ("Create cloudformation stack: %s" % stack_name)
    try:
        response = client.create_stack(StackName=stack_name, TemplateURL=TemplateURL, Parameters=[
            {'ParameterKey': 'TargetEBSVolumeInfo', 'ParameterValue': parameter1}, {'ParameterKey': 'ScheduleExpression', 'ParameterValue': parameter2}, ], Capabilities=['CAPABILITY_IAM'])
    except Exception as ex:
        print ex.message


def update_cloudformation(stack_name, parameter1, parameter2, volume_id, client):
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


def check_valid_stack(stack_name, client):
    try:
        response = client.describe_stacks()
    except Exception as ex:
        print ex.message
    for stack in response['Stacks']:
        if stack_name in stack['StackName']:
            return True


def build_ebs_volume_change_schedule(stack_name, target_schedule, volume_id, client):
    target_type = target_schedule.split(':')
    parameter1 = volume_id + ":" + target_type[0] + ":" + target_type[1]
    parameter2 = "cron" + target_type[2]
    print ("CloudForamtion template parameters:{},{}".format(
        parameter1, parameter2))
    print ("Volume %s will be changed to %s, IOPS is %s" %
           (volume_id, target_type[0], target_type[1]))
    print ("This task will be executed based on %s" % target_type[2])
    if check_valid_stack(stack_name, client):
        try:
            cloudformation = boto3.resource('cloudformation')
            try:
                stack = cloudformation.Stack(stack_name)
            except Exception as ex:
                print ex.message
            stack_status = stack.stack_status
            print ("Stack (%s) status: %s" % (stack_name, stack_status))
            if stack_status == "ROLLBACK_COMPLETE" or stack_status == "ROLLBACK_FAILED" or stack_status == "DELETE_FAILED":
                try:
                    response = client.delete_stack(StackName=stack_name)
                    waiter = client.get_waiter('stack_delete_complete')
                    waiter.wait(StackName=stack_name)
                except Exception as ex:
                    print ex.message
            if stack_status == "CREATE_IN_PROGRESS":
                waiter = client.get_waiter('stack_create_complete')
                waiter.wait(StackName=stack_name)
            if stack_status == "DELETE_IN_PROGRESS":
                waiter = client.get_waiter('stack_delete_complete')
                waiter.wait(StackName=stack_name)
            if stack_status == "UPDATE_IN_PROGRESS":
                waiter = client.get_waiter('stack_update_complete')
                waiter.wait(StackName=stack_name)
        except Exception as ex:
            print ex.message
    if check_valid_stack(stack_name, client):
        update_cloudformation(stack_name, parameter1, parameter2,
                              volume_id, client)
        waiter = client.get_waiter('stack_update_complete')
    else:
        create_cloudformation(stack_name, parameter1, parameter2,
                              volume_id, client)
        waiter = client.get_waiter('stack_create_complete')


def delete_ebs_volume_change_schedule(volume_id, client):
    response = client.describe_stacks()
    for stack in response['Stacks']:
        if volume_id in stack['StackName']:
            try:
                print("Delete cloudformation stack: %s" %
                      stack['StackName'])
                response = client.delete_stack(
                    StackName=stack['StackName'])
            except Exception as ex:
                print ex.message


def lambda_handler(event, context):
    volume_id = []
    global TemplateURL
    export = {}
    client = boto3.client('cloudformation')
    print (event)
    export = client.list_exports()
    for item in export['Exports']:
        if item['Name'] == 'CFUrl':
            TemplateURL = item['Value']
    print ("CF URL: %s" % TemplateURL)
    cloudtrail_event = get_cloudtrail_event(event)
    for log_event in cloudtrail_event['logEvents']:
        trail_message = get_message_from_cloudtrail_event(log_event)
        volume_id = trail_message['requestParameters']['resourcesSet']['items'][0]['resourceId']
        if trail_message['eventName'] == "CreateTags":
            for item in trail_message['requestParameters']['tagSet']['items']:
                if item['key'] == 'ChangeEBSType':
                    cf_parameter = item['value']
                    break
    if trail_message['eventName'] == "CreateTags":
        start_stop = cf_parameter.split(',')
        i = 0
        for schedule in start_stop:
            stack_name = "change-ebs-type-" + str(i) + "-" + volume_id
            build_ebs_volume_change_schedule(
                stack_name, schedule, volume_id, client)
            i = i + 1
    if trail_message['eventName'] == "DeleteTags":
        delete_ebs_volume_change_schedule(volume_id, client)
