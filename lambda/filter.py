def handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    if key.startswith('translations/'):
        return {'should_process': False}
    
    return {
        'should_process': True,
        'bucket': bucket,
        'key': key
    }
