import json
import boto3

polly_client = boto3.client('polly')
s3_client = boto3.client('s3')

def handler(event, context):
    text = event['text']
    bucket_name = event['bucket_name']
    key = event['key']
    
    response = polly_client.synthesize_speech(
        OutputFormat='mp3',
        Text=text,
        VoiceId='Joanna'
    )
    
    # Save the audio stream to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=response['AudioStream'].read()
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps('Synthesis complete')
    }
