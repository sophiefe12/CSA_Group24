from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3_notifications as s3n,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets,
    RemovalPolicy,
    App, Stack
)
from constructs import Construct

class TranslationPipelineStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for uploading audio files
        bucket = s3.Bucket(
            self, "TranslationBucket",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # IAM role for Step Functions to interact with other AWS services
        step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com")
        )

        step_functions_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaRole")
        )

        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                resources=["*"],
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                    "translate:TranslateText",
                    "polly:SynthesizeSpeech",
                    "states:StartExecution"
                ]
            )
        )

        # Lambda function to generate UUID
        uuid_lambda = _lambda.Function(
            self, "GenerateUUIDFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="generate_uuid.handler",
            code=_lambda.Code.from_asset("lambda")
        )

        # Lambda function for filtering
        filter_lambda = _lambda.Function(
            self, "FilterFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="filter.handler",
            code=_lambda.Code.from_asset("lambda")
        )

        # Lambda function for Polly synthesis
        polly_lambda = _lambda.Function(
            self, "SynthesizeSpeechFunction",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="polly.handler",
            code=_lambda.Code.from_asset("lambda")
        )

        # Grant FilterFunction permission to start the Step Function execution
        filter_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=["arn:aws:states:eu-west-1:471112856816:stateMachine:TranslationStateMachine65E7A269-rjqOb69GwgXO"]
            )
        )

        # Step Function Definition
        uuid_task = tasks.LambdaInvoke(
            self, "Generate UUID",
            lambda_function=uuid_lambda,
            output_path="$.Payload"
        )

        filter_task = tasks.LambdaInvoke(
            self, "Filter",
            lambda_function=filter_lambda,
            result_path="$.filter_result"
        )

        choice = sfn.Choice(self, "Should Process?")
        is_process = sfn.Condition.boolean_equals("$.filter_result.should_process", True)

        transcribe_task = tasks.CallAwsService(
            self, "Transcribe",
            service="transcribe",
            action="startTranscriptionJob",
            parameters={
                "TranscriptionJobName.$": "States.Format('transcription-{}', $.uuid)",
                "LanguageCode": "auto",
                "Media": {
                    "MediaFileUri.$": "States.Format('s3://{}/{}', $.filter_result.bucket, $.filter_result.key)"
                },
                "OutputBucketName": bucket.bucket_name,
                "OutputKey.$": "States.Format('transcriptions/{}.json', $.uuid)"
            },
            iam_resources=["*"],
            result_path="$.transcription_result"
        )

        get_transcription_task = tasks.CallAwsService(
            self, "Get Transcription",
            service="transcribe",
            action="getTranscriptionJob",
            parameters={
                "TranscriptionJobName.$": "$.transcription_result.TranscriptionJob.TranscriptionJobName"
            },
            iam_resources=["*"],
            result_selector={
                "transcript.$": "$.TranscriptionJob.Transcript.TranscriptFileUri"
            },
            result_path="$.transcription_output"
        )

        translate_task = tasks.CallAwsService(
            self, "Translate",
            service="translate",
            action="translateText",
            parameters={
                "Text.$": "States.JsonToString($.transcription_output.transcript)",
                "SourceLanguageCode": "auto",
                "TargetLanguageCode": "en"
            },
            iam_resources=["*"],
            result_path="$.translation_result"
        )

        polly_task = tasks.LambdaInvoke(
            self, "Synthesize Speech",
            lambda_function=polly_lambda,
            payload=sfn.TaskInput.from_object({
                "text": sfn.JsonPath.string_at("$.translation_result.TranslatedText"),
                "bucket_name": bucket.bucket_name,
                "key": sfn.JsonPath.string_at("States.Format('translations/{}.mp3', $.uuid)")
            })
        )

        # Define the state machine
        definition = (
            filter_task.next(
                choice.when(is_process, uuid_task.next(transcribe_task).next(get_transcription_task).next(translate_task).next(polly_task))
                .otherwise(sfn.Pass(self, "Do Nothing"))
            )
        )

        state_machine = sfn.StateMachine(
            self, "TranslationStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),  # Use definition_body
            role=step_functions_role
        )

        # EventBridge rule to trigger Step Function on S3 file upload
        rule = events.Rule(
            self, "Rule",
            event_pattern={
                "source": ["aws.s3"],
                "detail": {
                    "bucket": {
                        "name": [bucket.bucket_name]
                    },
                    "object": {
                        "key": [{
                            "prefix": "uploads/"
                        }]
                    }
                }
            }
        )

        rule.add_target(targets.SfnStateMachine(state_machine))

        # S3 bucket notification to trigger the Step Function
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(filter_lambda)
        )

app = App()
TranslationPipelineStack(app, "TranslationPipelineStack")
app.synth()
