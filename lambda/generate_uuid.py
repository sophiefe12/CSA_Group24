import uuid

def handler(event, context):
    return {
        'uuid': str(uuid.uuid4())
    }
