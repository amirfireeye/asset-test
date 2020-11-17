import hashlib
import os

from aws_cdk import (
    core,
    aws_lambda as _lambda,
    pipelines,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_iam as iam,
)


class BaseStack(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        _lambda.Function(
            self,
            "hello",
            code=_lambda.Code.from_asset(
                path="code",
                bundling={
                    "image": _lambda.Runtime.PYTHON_3_8.bundling_docker_image,
                    "command": ["bash",  "-c", "cp -r /asset-input/* /asset-output/"],
                },
                source_hash=hashlib.sha256(b"hello").hexdigest(),
            ),
            handler="hello.world",
            runtime=_lambda.Runtime.PYTHON_3_8,
        )

        _lambda.Function(
            self,
            "world",
            code=_lambda.Code.from_asset(
                path="code",
                bundling={
                    "image": _lambda.Runtime.PYTHON_3_8.bundling_docker_image,
                    "command": ["bash",  "-c", "cp -r /asset-input/* /asset-output/ && touch /asset-output/foo.py"],
                },
                source_hash=hashlib.sha256(b"world").hexdigest(),
            ),
            handler="hello.world",
            runtime=_lambda.Runtime.PYTHON_3_8,
        )


class BaseStage(core.Stage):
    def __init__(self, scope: core.Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        BaseStack(self, "stack")


class PipelineStack(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        source_artifact = codepipeline.Artifact()
        cloud_assembly_artifact = codepipeline.Artifact()

        source_action = codepipeline_actions.GitHubSourceAction(
            action_name="Github.com",
            output=source_artifact,
            oauth_token=core.SecretValue.secrets_manager(secret_id="asset-test", json_field="github_token"),  # TODO
            owner="amirfireeye",
            repo="asset-test",
            branch="master",
        )

        synth_action = pipelines.SimpleSynthAction(
            source_artifact=source_artifact,
            cloud_assembly_artifact=cloud_assembly_artifact,
            environment=dict(privileged=True),
            install_commands=[
                "pip install poetry",
                "npm install -g aws-cdk@1.73.0",
                "DOCKERHUB_USERNAME=`aws secretsmanager get-secret-value --secret-id asset-test --query SecretString --output text | jq -r .docker_username`",
                "DOCKERHUB_PASSWORD=`aws secretsmanager get-secret-value --secret-id asset-test --query SecretString --output text | jq -r .docker_password`",
                "docker login -u ${DOCKERHUB_USERNAME} -p ${DOCKERHUB_PASSWORD}",
            ],
            synth_command="poetry install && poetry run cdk synth && cat cdk.out/assembly-*/*.assets.json",
            role_policy_statements=[
                # for docker secret
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "secretsmanager:ListSecrets",
                        "secretsmanager:GetSecretValue"
                    ],
                    resources=["*"]
                ),
            ]
        )

        pipeline = pipelines.CdkPipeline(
            self, "pipeline",
            cloud_assembly_artifact=cloud_assembly_artifact,
            source_action=source_action,
            synth_action=synth_action,
        )

        stage = BaseStage(self, "stage")
        pipeline.add_application_stage(stage)


app = core.App()
pipeline_stack = PipelineStack(app, "pipelinestack")
