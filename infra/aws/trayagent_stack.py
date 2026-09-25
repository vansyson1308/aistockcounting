"""TrayAgent on AWS: one EC2 Graviton host behind CloudFront (SPEC §6).

    viewer --HTTPS--> CloudFront --HTTP:80--> EC2 t4g/c7g (Elastic IP, public subnet)
                                               docker compose: nginx, frontend,
                                               backend (OpenCV 5 + agent), postgres
    backend --> S3 evidence bucket, CloudWatch metrics (namespace TrayAgent)
    containers --awslogs--> CloudWatch Logs;  images <-- ECR (arm64)

The stack is environment-agnostic in the account and never looks anything up at
synth time, so `cdk synth` and the unit tests run without AWS credentials.

Host configuration (app.env, the compose file, the nginx config and update.sh)
is rendered into SSM Parameter Store. User data only bootstraps Docker and
runs /opt/trayagent/update.sh, which reads those parameters; a `cdk deploy`
followed by update.sh (scripts/aws/deploy.sh does both) therefore applies any
change without replacing the instance or its Postgres data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aws_cdk import (
    Aws,
    CfnCondition,
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy" / "aws"

GRAVITON_FAMILIES = ("t4g", "c7g")
METRIC_NAMESPACE = "TrayAgent"
METRIC_DIMENSIONS = {"Service": "trayagent"}
# docker compose v2 plugin release (the last v2 line); aarch64 binary + .sha256.
COMPOSE_VERSION = "v2.40.3"
CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST = "com.amazonaws.global.cloudfront.origin-facing"
# Standard-tier SSM parameters hold at most 4 KB (free; advanced tier is paid).
SSM_STANDARD_MAX_CHARS = 4096

ESCALATION_RATE_THRESHOLD_PCT = 50
ESCALATION_MIN_RUNS = 5  # below this many runs per hour the rate is noise
LATENCY_P95_THRESHOLD_MS = 15_000


def _as_bool(value: Any, default: bool) -> bool:
    """Context values from `-c key=value` arrive as strings, from cdk.json as JSON."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class TrayAgentConfig:
    """Deploy-time settings, read from CDK context (see infra/aws/README.md)."""

    instance_type: str = "t4g.large"
    enable_bedrock: bool = False
    bedrock_model_id: str = ""
    alarm_email: str = ""
    model_s3_key: str = ""
    retain_data: bool = False
    # Optional: skip the deploy-time lookup of the CloudFront prefix list.
    cloudfront_prefix_list_id: str = ""
    # Optional: pin the AMI (otherwise the latest AL2023 arm64 AMI is used).
    ami_id: str = ""
    default_tenant_key: str = "demo"

    @classmethod
    def from_context(cls, scope: Construct) -> TrayAgentConfig:
        ctx = scope.node.try_get_context

        def text(key: str, default: str = "") -> str:
            value = ctx(key)
            return default if value is None else str(value).strip()

        return cls(
            instance_type=text("instanceType", cls.instance_type),
            enable_bedrock=_as_bool(ctx("enableBedrock"), False),
            bedrock_model_id=text("bedrockModelId"),
            alarm_email=text("alarmEmail"),
            model_s3_key=text("modelS3Key").lstrip("/"),
            retain_data=_as_bool(ctx("retainData"), False),
            cloudfront_prefix_list_id=text("cloudFrontPrefixListId"),
            ami_id=text("amiId"),
            default_tenant_key=text("defaultTenantKey", cls.default_tenant_key),
        )

    def validate(self) -> None:
        family = self.instance_type.split(".", 1)[0]
        if family not in GRAVITON_FAMILIES:
            raise ValueError(
                f"instanceType {self.instance_type!r} is not Graviton; "
                f"use one of the {GRAVITON_FAMILIES} families (arm64 images)"
            )
        if self.enable_bedrock and not self.bedrock_model_id:
            raise ValueError(
                "enableBedrock=true needs -c bedrockModelId=<model or inference profile id>"
            )
        if self.model_s3_key and not self.model_s3_key.endswith(".onnx"):
            raise ValueError("modelS3Key must point to an .onnx file")


def strip_comment_lines(text: str) -> str:
    """Drop full-line comments (keeps a shebang) so files fit a 4 KB SSM parameter."""
    kept = [
        line
        for line in text.splitlines()
        if line.startswith("#!") or not line.lstrip().startswith("#")
    ]
    return "\n".join(kept) + "\n"


def _read_config_file(path: Path) -> str:
    content = strip_comment_lines(path.read_text())
    if len(content) > SSM_STANDARD_MAX_CHARS:
        raise ValueError(
            f"{path} is {len(content)} chars without comments; the SSM limit is 4096"
        )
    return content


class TrayAgentStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: TrayAgentConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        config.validate()
        self.config = config
        removal = RemovalPolicy.RETAIN if config.retain_data else RemovalPolicy.DESTROY
        destroy = not config.retain_data
        param_prefix = f"/trayagent/{self.stack_name}"

        # ---- Network: public subnets only, no NAT gateway (cost). ----------
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                )
            ],
        )

        # Port 80 only, and only from CloudFront's origin-facing IP ranges. No
        # port 22: shell access goes through SSM Session Manager.
        sg = ec2.SecurityGroup(
            self,
            "InstanceSg",
            vpc=vpc,
            allow_all_outbound=True,
            description="TrayAgent host: HTTP from CloudFront only",
        )
        sg.add_ingress_rule(
            ec2.Peer.prefix_list(self._cloudfront_prefix_list_id()),
            ec2.Port.tcp(80),
            "HTTP from the CloudFront origin-facing prefix list",
        )

        # ---- Storage, registry, logs. -------------------------------------
        bucket = s3.Bucket(
            self,
            "EvidenceBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=removal,
            auto_delete_objects=destroy,
            lifecycle_rules=[
                *[
                    s3.LifecycleRule(
                        id=f"expire-{prefix}",
                        prefix=f"{prefix}/",
                        expiration=Duration.days(30),
                    )
                    for prefix in ("uploads", "thumbnails", "evidence")
                ],
                s3.LifecycleRule(
                    id="housekeeping",
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                    noncurrent_version_expiration=Duration.days(7),
                    expired_object_delete_marker=True,
                ),
            ],
        )

        repos = {
            name: ecr.Repository(
                self,
                f"{name.capitalize()}Repo",
                repository_name=f"trayagent-{name}",
                image_scan_on_push=True,
                removal_policy=removal,
                empty_on_delete=destroy,
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description="Keep the last 10 images",
                        max_image_count=10,
                        tag_status=ecr.TagStatus.ANY,
                    )
                ],
            )
            for name in ("backend", "frontend")
        }

        log_group = logs.LogGroup(
            self,
            "ContainerLogs",
            log_group_name=f"/trayagent/{self.stack_name}",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=removal,
        )

        # ---- Instance role. -----------------------------------------------
        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="TrayAgent EC2 host",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )
        for repo in repos.values():
            repo.grant_pull(role)  # includes ecr:GetAuthorizationToken
        bucket.grant_read_write(role)  # includes s3:DeleteObject*
        log_group.grant_write(role)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="PutTrayAgentMetrics",
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],  # PutMetricData has no resource-level permissions
                conditions={"StringEquals": {"cloudwatch:namespace": METRIC_NAMESPACE}},
            )
        )
        if config.enable_bedrock:
            # The Converse API is authorised as bedrock:InvokeModel. Allow both
            # foundation models and (cross-region) inference profiles.
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="BedrockPlanner",
                    actions=["bedrock:InvokeModel"],
                    resources=[
                        f"arn:{Aws.PARTITION}:bedrock:*::foundation-model/*",
                        f"arn:{Aws.PARTITION}:bedrock:*:{Aws.ACCOUNT_ID}:inference-profile/*",
                    ],
                )
            )

        # ---- Elastic IP and CloudFront. -----------------------------------
        # The EIP is created first and associated after the instance exists, so
        # CloudFront and user data can reference its address without a cycle.
        eip = ec2.CfnEIP(self, "Eip", domain="vpc")
        # CloudFront origins need a DNS name, not an IP: build the EC2 public
        # DNS name of the EIP (ec2-1-2-3-4.<region>.compute.amazonaws.com). It
        # stays valid even if the instance is replaced.
        compute_suffix = Fn.condition_if(
            self._is_us_east_1().logical_id,
            "compute-1.amazonaws.com",
            f"{Aws.REGION}.compute.amazonaws.com",
        ).to_string()
        origin_dns = Fn.join(
            "",
            [
                "ec2-",
                Fn.join("-", Fn.split(".", eip.attr_public_ip)),
                ".",
                compute_suffix,
            ],
        )

        origin = origins.HttpOrigin(
            origin_dns,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
            # Agent runs take up to ~20 s; nginx allows 75 s behind this.
            read_timeout=Duration.seconds(60),
        )
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment=f"TrayAgent ({self.stack_name})",
            price_class=cloudfront.PriceClass.PRICE_CLASS_200,  # includes Asian edges
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                # AllViewer (not AllViewerExceptHostHeader): the origin is plain
                # nginx, which accepts any Host, and forwarding the viewer's Host
                # (xxx.cloudfront.net) keeps it equal to the browser's Origin
                # header. Next.js compares the two for Server Actions, and
                # FastAPI/Next build absolute URLs and redirects from it. The
                # ExceptHost variant is for origins that need their own Host
                # header (API Gateway, Lambda URLs, S3).
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
            ),
            additional_behaviors={
                # Next.js build assets have content-hashed names: safe to cache.
                "/_next/static/*": cloudfront.BehaviorOptions(
                    origin=origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                ),
            },
        )
        site_url = f"https://{distribution.distribution_domain_name}"

        # ---- Host configuration in SSM Parameter Store. -------------------
        detector = "onnx" if config.model_s3_key else "classical"
        app_env = {
            "AWS_REGION": Aws.REGION,
            "S3_BUCKET": bucket.bucket_name,
            "LOG_GROUP": log_group.log_group_name,
            "ECR_REGISTRY": Fn.select(
                0, Fn.split("/", repos["backend"].repository_uri)
            ),
            "BACKEND_IMAGE": repos["backend"].repository_uri,
            "FRONTEND_IMAGE": repos["frontend"].repository_uri,
            "DETECTOR_BACKEND": detector,
            "MODEL_S3_KEY": config.model_s3_key,
            "AGENT_PLANNER": "bedrock" if config.enable_bedrock else "deterministic",
            "BEDROCK_MODEL_ID": config.bedrock_model_id
            if config.enable_bedrock
            else "",
            "CORS_ORIGINS": site_url,
            "DEFAULT_TENANT_KEY": config.default_tenant_key,
        }
        host_files = {
            "app-env": "".join(f"{key}={value}\n" for key, value in app_env.items()),
            "compose": _read_config_file(DEPLOY_DIR / "docker-compose.aws.yml"),
            "nginx": _read_config_file(REPO_ROOT / "nginx" / "nginx.aws.conf"),
            "update-sh": _read_config_file(DEPLOY_DIR / "update.sh"),
        }
        params = [
            ssm.StringParameter(
                self,
                f"Param-{name}",
                parameter_name=f"{param_prefix}/{name}",
                string_value=value,
                tier=ssm.ParameterTier.STANDARD,
                description=f"TrayAgent host file ({name}), read by /opt/trayagent/update.sh",
            )
            for name, value in host_files.items()
        ]
        for param in params:
            param.grant_read(role)

        # ---- Instance. ----------------------------------------------------
        user_data_script = strip_comment_lines(
            (DEPLOY_DIR / "user-data.sh").read_text()
        )
        for placeholder, value in {
            "@@REGION@@": Aws.REGION,
            "@@PARAM_PREFIX@@": param_prefix,
            "@@ELASTIC_IP@@": eip.attr_public_ip,
            "@@COMPOSE_VERSION@@": COMPOSE_VERSION,
        }.items():
            user_data_script = user_data_script.replace(placeholder, value)

        if config.ami_id:
            machine_image = ec2.MachineImage.generic_linux({self.region: config.ami_id})
        else:
            # SSM parameter /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64,
            # resolved by CloudFormation at deploy time (no synth-time lookup).
            machine_image = ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            )

        instance = ec2.Instance(
            self,
            "Host",
            instance_name=f"trayagent-{self.stack_name}",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(config.instance_type),
            machine_image=machine_image,
            security_group=sg,
            role=role,
            user_data=ec2.UserData.custom(user_data_script),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            # IMDSv2 only. Hop limit 2 lets the containers (one extra network
            # hop on the Docker bridge) get instance-role credentials.
            http_tokens=ec2.HttpTokens.REQUIRED,
            http_put_response_hop_limit=2,
        )
        # First boot reads these parameters, so they must exist before launch.
        for param in params:
            instance.node.add_dependency(param)
        ec2.CfnEIPAssociation(
            self,
            "EipAssociation",
            allocation_id=eip.attr_allocation_id,
            instance_id=instance.instance_id,
        )

        # ---- Observability. -----------------------------------------------
        topic = sns.Topic(
            self, "AlarmTopic", display_name="TrayAgent alarms", enforce_ssl=True
        )
        if config.alarm_email:
            topic.add_subscription(subs.EmailSubscription(config.alarm_email))
        alarm_action = cw_actions.SnsAction(topic)

        def app_metric(name: str, statistic: str, period: Duration) -> cw.Metric:
            return cw.Metric(
                namespace=METRIC_NAMESPACE,
                metric_name=name,
                dimensions_map=METRIC_DIMENSIONS,
                statistic=statistic,
                period=period,
            )

        hour = Duration.hours(1)
        five_min = Duration.minutes(5)
        runs_5m = app_metric("AgentRuns", "Sum", five_min)
        # Escalated / RecaptureRequested are 0/1 per run, so Sum/Sum is a rate.
        escalation_rate_1h = cw.MathExpression(
            expression=f"IF(runs >= {ESCALATION_MIN_RUNS}, 100 * esc / runs, 0)",
            using_metrics={
                "runs": app_metric("AgentRuns", "Sum", hour),
                "esc": app_metric("Escalated", "Sum", hour),
            },
            period=hour,
            label="Escalation rate % (1 h)",
        )
        escalation_rate_5m = cw.MathExpression(
            expression="100 * esc / runs",
            using_metrics={
                "runs": runs_5m,
                "esc": app_metric("Escalated", "Sum", five_min),
            },
            period=five_min,
            label="Escalation rate %",
        )
        recapture_rate_5m = cw.MathExpression(
            expression="100 * rec / runs",
            using_metrics={
                "runs": runs_5m,
                "rec": app_metric("RecaptureRequested", "Sum", five_min),
            },
            period=five_min,
            label="Recapture rate %",
        )
        latency_p95_15m = app_metric("AgentLatencyMs", "p95", Duration.minutes(15))
        cpu = cw.Metric(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions_map={"InstanceId": instance.instance_id},
            statistic="Average",
            period=five_min,
        )

        alarms = [
            cw.Alarm(
                self,
                "EscalationRateAlarm",
                alarm_description=(
                    f"More than {ESCALATION_RATE_THRESHOLD_PCT}% of agent runs escalated to a human "
                    f"in the last hour (only evaluated with >= {ESCALATION_MIN_RUNS} runs)."
                ),
                metric=escalation_rate_1h,
                threshold=ESCALATION_RATE_THRESHOLD_PCT,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                evaluation_periods=1,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            ),
            cw.Alarm(
                self,
                "LatencyP95Alarm",
                alarm_description="Agent run latency p95 above 15 s over 15 minutes.",
                metric=latency_p95_15m,
                threshold=LATENCY_P95_THRESHOLD_MS,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                evaluation_periods=1,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            ),
            cw.Alarm(
                self,
                "StatusCheckAlarm",
                alarm_description="EC2 instance or system status check failed.",
                metric=cw.Metric(
                    namespace="AWS/EC2",
                    metric_name="StatusCheckFailed",
                    dimensions_map={"InstanceId": instance.instance_id},
                    statistic="Maximum",
                    period=Duration.minutes(1),
                ),
                threshold=1,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                evaluation_periods=2,
            ),
        ]
        for alarm in alarms:
            alarm.add_alarm_action(alarm_action)

        dashboard = cw.Dashboard(
            self, "Dashboard", dashboard_name=f"TrayAgent-{self.stack_name}"
        )
        dashboard.add_widgets(
            cw.GraphWidget(title="Agent runs (sum / 5 min)", left=[runs_5m], width=8),
            cw.GraphWidget(
                title="Agent steps per run (avg)",
                left=[app_metric("AgentSteps", "Average", five_min)],
                width=8,
            ),
            cw.GraphWidget(
                title="Escalation and recapture rate (%)",
                left=[escalation_rate_5m, recapture_rate_5m],
                left_y_axis=cw.YAxisProps(min=0, max=100),
                width=8,
            ),
        )
        dashboard.add_widgets(
            cw.GraphWidget(
                title="Agent latency (ms)",
                left=[
                    app_metric("AgentLatencyMs", "p50", five_min),
                    app_metric("AgentLatencyMs", "p95", five_min),
                ],
                left_annotations=[
                    cw.HorizontalAnnotation(
                        value=LATENCY_P95_THRESHOLD_MS, label="p95 alarm"
                    )
                ],
                width=8,
            ),
            cw.GraphWidget(
                title="Planner fallbacks (sum / 5 min)",
                left=[app_metric("PlannerFallbacks", "Sum", five_min)],
                width=8,
            ),
            cw.GraphWidget(title="EC2 CPU utilization (%)", left=[cpu], width=8),
        )
        dashboard.add_widgets(
            cw.AlarmStatusWidget(title="Alarms", alarms=alarms, width=24)
        )

        # ---- Outputs (read by scripts/aws/*.sh). --------------------------
        outputs = {
            "CloudFrontUrl": site_url,
            "BucketName": bucket.bucket_name,
            "BackendRepositoryUri": repos["backend"].repository_uri,
            "FrontendRepositoryUri": repos["frontend"].repository_uri,
            "InstanceId": instance.instance_id,
            "LogGroupName": log_group.log_group_name,
            "DashboardUrl": (
                f"https://{Aws.REGION}.console.aws.amazon.com/cloudwatch/home"
                f"?region={Aws.REGION}#dashboards:name={dashboard.dashboard_name}"
            ),
            "ConfigParameterPrefix": param_prefix,
            "AlarmTopicArn": topic.topic_arn,
        }
        for key, value in outputs.items():
            CfnOutput(self, key, value=value)

    def _is_us_east_1(self) -> CfnCondition:
        """us-east-1 is the one region whose EC2 DNS suffix is compute-1.amazonaws.com."""
        return CfnCondition(
            self, "IsUsEast1", expression=Fn.condition_equals(Aws.REGION, "us-east-1")
        )

    def _cloudfront_prefix_list_id(self) -> str:
        """ID of the CloudFront origin-facing managed prefix list in this region.

        The ID differs per region. Unless it is given as context, it is looked
        up by a custom resource at deploy time (DescribeManagedPrefixLists), so
        synth needs no credentials.
        """
        if self.config.cloudfront_prefix_list_id:
            return self.config.cloudfront_prefix_list_id
        sdk_call = cr.AwsSdkCall(
            service="EC2",
            action="describeManagedPrefixLists",
            parameters={
                "Filters": [
                    {
                        "Name": "prefix-list-name",
                        "Values": [CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST],
                    }
                ]
            },
            physical_resource_id=cr.PhysicalResourceId.of(
                CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST
            ),
            output_paths=["PrefixLists.0.PrefixListId"],
        )
        lookup = cr.AwsCustomResource(
            self,
            "CloudFrontPrefixListLookup",
            on_create=sdk_call,
            on_update=sdk_call,
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
            install_latest_aws_sdk=False,
            log_group=logs.LogGroup(
                self,
                "PrefixListLookupLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        return lookup.get_response_field("PrefixLists.0.PrefixListId")
