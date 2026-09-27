#!/usr/bin/env python3
"""CDK app for the TrayAgent AWS deployment. See README.md in this directory.

Context (all optional; pass with `-c key=value`):
  stackName               CloudFormation stack name        (default TrayAgent)
  region                  target region                     (default ap-southeast-1)
  instanceType            t4g.* or c7g.* (Graviton)         (default t4g.large)
  enableBedrock           grant bedrock:InvokeModel and use the Bedrock planner (default false)
  bedrockModelId          model or inference profile id; required with enableBedrock
  alarmEmail              subscribe this address to the alarm SNS topic
  modelS3Key              S3 key of the ONNX model in the evidence bucket (enables DETECTOR_BACKEND=onnx)
  retainData              keep bucket, ECR repos and logs on `cdk destroy` (default false)
  cloudFrontPrefixListId  skip the deploy-time lookup of the CloudFront prefix list
  amiId                   pin the AMI instead of the latest Amazon Linux 2023 arm64
"""

import aws_cdk as cdk
from trayagent_stack import TrayAgentConfig, TrayAgentStack

app = cdk.App()
stack_name = app.node.try_get_context("stackName") or "TrayAgent"
region = app.node.try_get_context("region") or "ap-southeast-1"

TrayAgentStack(
    app,
    stack_name,
    config=TrayAgentConfig.from_context(app),
    # Region only: the account stays unresolved, so nothing is looked up at synth.
    env=cdk.Environment(region=region),
    description="TrayAgent: OpenCV 5 tray-counting agent on EC2 Graviton + CloudFront + S3 + CloudWatch",
)
cdk.Tags.of(app).add("Project", "TrayAgent")

app.synth()
