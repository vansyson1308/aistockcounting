"""Unit tests for the TrayAgent CDK stack (no AWS credentials needed).

Run from infra/aws:  .venv/bin/python -m pytest -q
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

INFRA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = INFRA_DIR.parents[1]
sys.path.insert(0, str(INFRA_DIR))

from trayagent_stack import (  # noqa: E402
    TrayAgentConfig,
    TrayAgentStack,
    strip_comment_lines,
)

# Managed CloudFront policy IDs (fixed across all accounts).
CACHING_DISABLED_ID = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ALL_VIEWER_ID = "216adef6-5c7f-47e4-b989-5492eafa07d3"
FEATURE_FLAGS = json.loads((INFRA_DIR / "cdk.json").read_text())["context"]


@cache
def _synth(config: TrayAgentConfig) -> Template:
    app = cdk.App(context=FEATURE_FLAGS)
    stack = TrayAgentStack(
        app, "TrayAgent", config=config, env=cdk.Environment(region="ap-southeast-1")
    )
    return Template.from_stack(stack)


@pytest.fixture(scope="module")
def template() -> Template:
    return _synth(TrayAgentConfig())


def _only(template: Template, resource_type: str) -> dict[str, Any]:
    resources = template.find_resources(resource_type)
    assert len(resources) == 1, f"expected one {resource_type}, got {list(resources)}"
    return next(iter(resources.values()))


def _policy_statements(template: Template) -> list[dict[str, Any]]:
    statements = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        statements += policy["Properties"]["PolicyDocument"]["Statement"]
    return statements


def _actions(statement: dict[str, Any]) -> list[str]:
    action = statement["Action"]
    return [action] if isinstance(action, str) else action


def _app_env(template: Template) -> str:
    """The app-env SSM parameter, with CloudFormation intrinsics replaced by '<token>'."""
    params = template.find_resources(
        "AWS::SSM::Parameter", {"Properties": {"Name": "/trayagent/TrayAgent/app-env"}}
    )
    (param,) = params.values()
    parts = param["Properties"]["Value"]["Fn::Join"][1]
    return "".join(p if isinstance(p, str) else "<token>" for p in parts)


# ---- Compute -------------------------------------------------------------


def test_instance_is_graviton_on_al2023_arm64(template: Template) -> None:
    props = _only(template, "AWS::EC2::Instance")["Properties"]
    assert props["InstanceType"].split(".")[0] in ("t4g", "c7g")
    image_param = props["ImageId"]["Ref"]
    ami_path = template.to_json()["Parameters"][image_param]["Default"]
    assert ami_path.startswith("/aws/service/ami-amazon-linux-latest/al2023-ami-")
    assert ami_path.endswith("-arm64")


def test_instance_root_volume_imdsv2_and_public_subnet(template: Template) -> None:
    props = _only(template, "AWS::EC2::Instance")["Properties"]
    ebs = props["BlockDeviceMappings"][0]["Ebs"]
    assert ebs == {
        "DeleteOnTermination": True,
        "Encrypted": True,
        "VolumeSize": 30,
        "VolumeType": "gp3",
    }
    assert props["MetadataOptions"] == {
        "HttpTokens": "required",
        "HttpPutResponseHopLimit": 2,
    }
    assert "KeyName" not in props  # SSM only, no SSH key
    template.has_resource_properties(
        "AWS::EC2::EIPAssociation", {"InstanceId": {"Ref": Match.any_value()}}
    )


def test_c7g_is_allowed_and_non_graviton_is_rejected() -> None:
    props = _only(
        _synth(TrayAgentConfig(instance_type="c7g.large")), "AWS::EC2::Instance"
    )["Properties"]
    assert props["InstanceType"] == "c7g.large"
    with pytest.raises(ValueError, match="not Graviton"):
        _synth(TrayAgentConfig(instance_type="t3.large"))


def test_user_data_bootstraps_without_secrets(template: Template) -> None:
    user_data = json.dumps(
        _only(template, "AWS::EC2::Instance")["Properties"]["UserData"]
    )
    assert "dnf install -y docker" in user_data
    assert "docker-compose-linux-aarch64" in user_data
    assert "openssl rand" in user_data  # Postgres password generated on the host
    assert "@@" not in user_data  # every placeholder filled
    # Anywhere in the template, the password is only ever a shell/compose
    # reference ($(openssl ...), ${POSTGRES_PASSWORD}), never a literal value.
    values = re.findall(
        r"POSTGRES_PASSWORD[=:] *([^\s\\\"]+)", json.dumps(template.to_json())
    )
    assert values and all(v.startswith("$") for v in values), values


# ---- Network -------------------------------------------------------------


def test_vpc_has_public_subnets_and_no_nat(template: Template) -> None:
    template.resource_count_is("AWS::EC2::NatGateway", 0)
    subnets = template.find_resources("AWS::EC2::Subnet")
    assert subnets
    assert all(s["Properties"]["MapPublicIpOnLaunch"] for s in subnets.values())


def test_only_port_80_is_open_and_never_22(template: Template) -> None:
    rules = [
        r["Properties"]
        for r in template.find_resources("AWS::EC2::SecurityGroupIngress").values()
    ]
    for sg in template.find_resources("AWS::EC2::SecurityGroup").values():
        rules += sg["Properties"].get("SecurityGroupIngress", [])
    assert rules, "expected an HTTP ingress rule"
    for rule in rules:
        assert rule["IpProtocol"] == "tcp"
        assert not (rule["FromPort"] <= 22 <= rule["ToPort"])
        assert rule["FromPort"] == rule["ToPort"] == 80
        # CloudFront origin-facing prefix list, never the open internet.
        assert "SourcePrefixListId" in rule and "CidrIp" not in rule


def test_prefix_list_is_looked_up_at_deploy_time_or_given(template: Template) -> None:
    template.has_resource_properties(
        "Custom::AWS",
        {
            "Create": Match.string_like_regexp(
                "com.amazonaws.global.cloudfront.origin-facing"
            )
        },
    )
    given = _synth(TrayAgentConfig(cloudfront_prefix_list_id="pl-12345678"))
    given.resource_count_is("Custom::AWS", 0)
    given.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {"SourcePrefixListId": "pl-12345678", "FromPort": 80},
    )


# ---- Storage and registry --------------------------------------------------


def test_bucket_is_private_encrypted_and_ssl_only(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        },
    )
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_bucket_lifecycle_rules(template: Template) -> None:
    rules = _only(template, "AWS::S3::Bucket")["Properties"]["LifecycleConfiguration"][
        "Rules"
    ]
    expiring = {r["Prefix"]: r["ExpirationInDays"] for r in rules if "Prefix" in r}
    assert expiring == {"uploads/": 30, "thumbnails/": 30, "evidence/": 30}
    housekeeping = next(r for r in rules if "Prefix" not in r)
    assert housekeeping["AbortIncompleteMultipartUpload"] == {"DaysAfterInitiation": 7}
    assert housekeeping["NoncurrentVersionExpiration"] == {"NoncurrentDays": 7}
    assert all(r["Status"] == "Enabled" for r in rules)


def test_ecr_repositories_scan_and_keep_last_10(template: Template) -> None:
    repos = template.find_resources("AWS::ECR::Repository")
    assert sorted(r["Properties"]["RepositoryName"] for r in repos.values()) == [
        "trayagent-backend",
        "trayagent-frontend",
    ]
    for repo in repos.values():
        props = repo["Properties"]
        assert props["ImageScanningConfiguration"] == {"ScanOnPush": True}
        (rule,) = json.loads(props["LifecyclePolicy"]["LifecyclePolicyText"])["rules"]
        assert rule["selection"]["countType"] == "imageCountMoreThan"
        assert rule["selection"]["countNumber"] == 10
        assert props["EmptyOnDelete"] is True
        assert repo["DeletionPolicy"] == "Delete"


def test_removal_policy_is_configurable() -> None:
    default = _synth(TrayAgentConfig())
    default.resource_count_is("Custom::S3AutoDeleteObjects", 1)
    assert _only(default, "AWS::S3::Bucket")["DeletionPolicy"] == "Delete"

    kept = _synth(TrayAgentConfig(retain_data=True))
    kept.resource_count_is("Custom::S3AutoDeleteObjects", 0)
    for resource_type in ("AWS::S3::Bucket", "AWS::ECR::Repository"):
        assert all(
            r["DeletionPolicy"] == "Retain"
            for r in kept.find_resources(resource_type).values()
        )
    assert _only(kept, "AWS::S3::Bucket")["DeletionPolicy"] == "Retain"


# ---- CloudFront ------------------------------------------------------------


def test_cloudfront_redirects_to_https_with_60s_origin_timeout(
    template: Template,
) -> None:
    config = _only(template, "AWS::CloudFront::Distribution")["Properties"][
        "DistributionConfig"
    ]
    default = config["DefaultCacheBehavior"]
    assert default["ViewerProtocolPolicy"] == "redirect-to-https"
    assert default["CachePolicyId"] == CACHING_DISABLED_ID
    assert default["OriginRequestPolicyId"] == ALL_VIEWER_ID
    assert set(default["AllowedMethods"]) == {
        "GET",
        "HEAD",
        "OPTIONS",
        "PUT",
        "PATCH",
        "POST",
        "DELETE",
    }
    (origin,) = config["Origins"]
    assert origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "http-only"
    assert origin["CustomOriginConfig"]["HTTPPort"] == 80
    assert origin["CustomOriginConfig"]["OriginReadTimeout"] == 60
    assert "ViewerCertificate" not in config  # default *.cloudfront.net certificate
    # The origin is the EC2 public DNS name derived from the Elastic IP.
    assert "Eip" in json.dumps(origin["DomainName"])


# ---- Observability ---------------------------------------------------------


def test_log_group_retention_is_14_days(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"LogGroupName": "/trayagent/TrayAgent", "RetentionInDays": 14},
    )


def test_alarms_and_thresholds(template: Template) -> None:
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    by_id = {
        logical_id.rstrip("0123456789ABCDEF"): a["Properties"]
        for logical_id, a in alarms.items()
    }
    assert set(by_id) == {"EscalationRateAlarm", "LatencyP95Alarm", "StatusCheckAlarm"}

    escalation = by_id["EscalationRateAlarm"]
    assert escalation["Threshold"] == 50
    assert escalation["ComparisonOperator"] == "GreaterThanThreshold"
    assert escalation["TreatMissingData"] == "notBreaching"
    expression = next(m for m in escalation["Metrics"] if "Expression" in m)
    assert re.fullmatch(
        r"IF\(runs >= \d+, 100 \* esc / runs, 0\)", expression["Expression"]
    )
    periods = {
        m["MetricStat"]["Period"] for m in escalation["Metrics"] if "MetricStat" in m
    }
    assert periods == {3600}

    latency = by_id["LatencyP95Alarm"]
    assert latency["MetricName"] == "AgentLatencyMs"
    assert latency["ExtendedStatistic"] == "p95"
    assert latency["Threshold"] == 15000
    assert latency["Period"] * latency["EvaluationPeriods"] == 900

    status = by_id["StatusCheckAlarm"]
    assert status["Namespace"] == "AWS/EC2"
    assert status["MetricName"] == "StatusCheckFailed"

    topic_id = next(iter(template.find_resources("AWS::SNS::Topic")))
    for alarm in by_id.values():
        assert alarm["AlarmActions"] == [{"Ref": topic_id}]


def test_dashboard_has_agent_widgets(template: Template) -> None:
    body = json.dumps(
        _only(template, "AWS::CloudWatch::Dashboard")["Properties"]["DashboardBody"]
    )
    for needle in (
        "AgentRuns",
        "AgentSteps",
        "Escalated",
        "RecaptureRequested",
        "AgentLatencyMs",
        "p50",
        "p95",
        "CPUUtilization",
    ):
        assert needle in body, needle


def test_alarm_email_subscription_is_optional(template: Template) -> None:
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.resource_count_is("AWS::SNS::Subscription", 0)
    with_email = _synth(TrayAgentConfig(alarm_email="ops@example.com"))
    with_email.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "ops@example.com"}
    )


# ---- IAM -------------------------------------------------------------------


def test_instance_role_permissions(template: Template) -> None:
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "ManagedPolicyArns": Match.array_with(
                [
                    {
                        "Fn::Join": [
                            "",
                            Match.array_with(
                                [
                                    Match.string_like_regexp(
                                        "AmazonSSMManagedInstanceCore"
                                    )
                                ]
                            ),
                        ]
                    }
                ]
            )
        },
    )
    statements = _policy_statements(template)
    metrics = next(s for s in statements if "cloudwatch:PutMetricData" in _actions(s))
    assert metrics["Condition"] == {
        "StringEquals": {"cloudwatch:namespace": "TrayAgent"}
    }
    actions = {a for s in statements for a in _actions(s)}
    assert {
        "ecr:GetAuthorizationToken",
        "ecr:BatchGetImage",
        "s3:PutObject",
        "s3:DeleteObject*",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "ssm:GetParameter",
    } <= actions
    assert not any(a.startswith("bedrock:") for a in actions)


def test_bedrock_only_when_enabled() -> None:
    enabled = _synth(
        TrayAgentConfig(enable_bedrock=True, bedrock_model_id="test.model-v1")
    )
    bedrock = [
        s for s in _policy_statements(enabled) if "bedrock:InvokeModel" in _actions(s)
    ]
    assert len(bedrock) == 1
    env = _app_env(enabled)
    assert (
        "AGENT_PLANNER=bedrock\n" in env and "BEDROCK_MODEL_ID=test.model-v1\n" in env
    )
    with pytest.raises(ValueError, match="bedrockModelId"):
        _synth(TrayAgentConfig(enable_bedrock=True))


# ---- Host configuration ------------------------------------------------------


def test_host_config_parameters(template: Template) -> None:
    params = template.find_resources("AWS::SSM::Parameter")
    names = sorted(p["Properties"]["Name"] for p in params.values())
    assert names == [
        f"/trayagent/TrayAgent/{n}"
        for n in ("app-env", "compose", "nginx", "update-sh")
    ]
    for p in params.values():
        value = p["Properties"]["Value"]
        if isinstance(value, str):
            assert len(value) <= 4096
    env = _app_env(template)
    for line in (
        "DETECTOR_BACKEND=classical\n",
        "AGENT_PLANNER=deterministic\n",
        "MODEL_S3_KEY=\n",
        "DEFAULT_TENANT_KEY=demo\n",
    ):
        assert line in env, line
    for key in (
        "S3_BUCKET",
        "LOG_GROUP",
        "ECR_REGISTRY",
        "BACKEND_IMAGE",
        "FRONTEND_IMAGE",
    ):
        assert f"{key}=<token>" in env, key
    assert "CORS_ORIGINS=https://<token>\n" in env


def test_model_key_switches_detector_to_onnx() -> None:
    env = _app_env(_synth(TrayAgentConfig(model_s3_key="models/trayagent_v1.onnx")))
    assert "DETECTOR_BACKEND=onnx\n" in env
    assert "MODEL_S3_KEY=models/trayagent_v1.onnx\n" in env


def test_compose_file_matches_the_deployment() -> None:
    compose = strip_comment_lines(
        (REPO_ROOT / "deploy" / "aws" / "docker-compose.aws.yml").read_text()
    )
    assert "minio" not in compose.lower()
    assert "public.ecr.aws/docker/library/postgres:16" in compose
    assert "public.ecr.aws/docker/library/nginx:alpine" in compose
    assert compose.count("logging: *awslogs") == 4
    assert "/opt/trayagent/models:/app/models:ro" in compose


# ---- Outputs -----------------------------------------------------------------


def test_outputs(template: Template) -> None:
    outputs = template.to_json()["Outputs"]
    for key in (
        "CloudFrontUrl",
        "BucketName",
        "BackendRepositoryUri",
        "FrontendRepositoryUri",
        "InstanceId",
        "LogGroupName",
        "DashboardUrl",
    ):
        assert key in outputs, key
    url = outputs["CloudFrontUrl"]["Value"]["Fn::Join"][1]
    assert url[0] == "https://"


# ---- Scripts -----------------------------------------------------------------

SHELL_SCRIPTS = sorted(
    [
        *(REPO_ROOT / "scripts" / "aws").glob("*.sh"),
        *(REPO_ROOT / "deploy" / "aws").glob("*.sh"),
    ]
)


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_parse(script: Path) -> None:
    subprocess.run(["bash", "-n", str(script)], check=True)
    # shellcheck-py (requirements-dev.txt) installs the binary next to python.
    shellcheck = shutil.which("shellcheck") or shutil.which(
        "shellcheck", path=str(Path(sys.executable).parent)
    )
    if shellcheck:
        subprocess.run([shellcheck, "-x", str(script)], check=True)
