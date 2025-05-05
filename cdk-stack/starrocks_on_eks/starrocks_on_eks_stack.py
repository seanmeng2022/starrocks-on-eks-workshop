import boto3
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_s3 as s3,
    aws_eks as eks,
    CfnOutput,
    SecretValue,
    lambda_layer_kubectl_v31,
    Tags,
    aws_iam as iam,
    aws_ecr as ecr,
    aws_aps as aps,
    aws_grafana as grafana,
    aws_secretsmanager as secretsmanager,
    CfnJson,
    Fn
)

from constructs import Construct
import os

class StarrocksOnEksStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get EC2 instance details using boto3
        ec2_client = boto3.client('ec2')
        
        # Find EC2 instances with name starting with aws-cloud9
        instances = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'tag:Name',
                    'Values': ['aws-cloud9*']
                },
                {
                    'Name': 'instance-state-name',
                    'Values': ['running']
                }
            ]
        )
        
        if not instances['Reservations'] or not instances['Reservations'][0]['Instances']:
            raise Exception("Could not find any running EC2 instance with name starting with aws-cloud9")
            
        instance_details = instances['Reservations'][0]['Instances'][0]
        vpc_id = instance_details['VpcId']
        private_ip = instance_details['PrivateIpAddress']

        # Use the found VPC and apply tags to its subnets
        vpc = ec2.Vpc.from_lookup(self, "ExistingVPC",
            vpc_id=vpc_id
        )
        
        # Get VPC CIDR range
        vpc_details = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        vpc_cidr = vpc_details['Vpcs'][0]['CidrBlock']

        # Get all subnets in the VPC using boto3
        subnets = ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['Subnets']

        # Tag private and public subnets
        for subnet in subnets:
            # Check if subnet is private (no route to internet gateway)
            routes = ec2_client.describe_route_tables(
                Filters=[{'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}]
            )['RouteTables']
            
            is_private = True
            if routes:
                for route in routes[0]['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        is_private = False
                        break

            # Apply appropriate tags based on subnet type
            if is_private:
                ec2_client.create_tags(
                    Resources=[subnet['SubnetId']],
                    Tags=[{'Key': 'kubernetes.io/role/internal-elb', 'Value': '1'}]
                )
            else:
                ec2_client.create_tags(
                    Resources=[subnet['SubnetId']],
                    Tags=[{'Key': 'kubernetes.io/role/elb', 'Value': '1'}]
                )

        # Create security group for StarRocks ports
        starrocks_ports_sg = ec2.SecurityGroup(self, "StarRocksPortsSecurityGroup",
            vpc=vpc,
            description="Security group for StarRocks ports access",
            allow_all_outbound=True
        )

        # Allow inbound access on ports 8030 and 9030 from Cloud9 VPC CIDR
        starrocks_ports_sg.add_ingress_rule(
            ec2.Peer.ipv4(vpc_cidr),
            ec2.Port.tcp(8030),
            "Allow port 8030 access from Cloud9 VPC CIDR"
        )
        starrocks_ports_sg.add_ingress_rule(
            ec2.Peer.ipv4(vpc_cidr),
            ec2.Port.tcp(9030),
            "Allow port 9030 access from Cloud9 VPC CIDR"
        )

        # Create security group for EKS control plane
        eks_security_group = ec2.SecurityGroup(self, "EKSControlPlaneSecurityGroup",
            vpc=vpc,
            description="Security group for EKS cluster control plane",
            allow_all_outbound=True
        )

        # Allow inbound traffic from VPC CIDR
        eks_security_group.add_ingress_rule(
            ec2.Peer.ipv4(vpc_cidr),
            ec2.Port.all_traffic(),
            "Allow all inbound traffic from VPC CIDR"
        )

        # Create EKS mater role
        masters_role = iam.Role(self, "EksMastersRole",
            assumed_by=iam.AccountRootPrincipal()  
        )


        # Create EKS Cluster
        eks_cluster = eks.Cluster(self, "StarrocksEKSCluster",
            version=eks.KubernetesVersion.V1_31,
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            default_capacity=0,  # We will add a managed node group separately
            kubectl_layer=lambda_layer_kubectl_v31.KubectlV31Layer(self, "kubectl"),
            security_group=eks_security_group,
            masters_role=masters_role
        )
        


        # Add managed node group
        eks_cluster.add_nodegroup_capacity("StarrocksNodeGroup",
            instance_types=[ec2.InstanceType("c6i.8xlarge")],
            min_size=3,
            max_size=3,
            desired_size=3,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # Create Parameter Group for binlog settings
        parameter_group = rds.ParameterGroup(self, "AuroraParameterGroup",
            engine=rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_3_05_2
            ),
            parameters={
                "binlog_format": "ROW",
                "binlog_row_image": "FULL",
                "binlog_checksum": "NONE"
            }
        )


        # Create security group for Aurora
        aurora_security_group = ec2.SecurityGroup(self, "AuroraSecurityGroup",
            vpc=vpc,
            description="Security group for Aurora cluster"
        )

        # Allow inbound MySQL traffic from VPC CIDR
        aurora_security_group.add_ingress_rule(
            ec2.Peer.ipv4(vpc_cidr),
            ec2.Port.tcp(3306),
            "Allow MySQL access from VPC CIDR"
        )


        # Create Aurora Serverless v2 Cluster with removal policy
        cluster = rds.DatabaseCluster(self, "AuroraCluster",
            removal_policy=RemovalPolicy.RETAIN,  # Prevent cluster deletion on stack updates
            security_groups=[aurora_security_group],
            credentials=rds.Credentials.from_password(
                username="admin",
                password=SecretValue.unsafe_plain_text("starrocks")
            ),
            engine=rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_3_05_2
            ),
            vpc=vpc,
            parameter_group=parameter_group,
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2("writer"),
            readers=[
                rds.ClusterInstance.serverless_v2("reader1", scale_with_writer=True)
            ]
        )
        
        
        # ========== 添加 AWS Managed Prometheus ==========
        # 创建 Amazon Managed Service for Prometheus 工作区
        prometheus_workspace = aps.CfnWorkspace(self, "StarrocksPrometheusWorkspace",
            alias="starrocks-prometheus"
        )
        
        
        # First create the prometheus namespace
        prometheus_namespace = eks_cluster.add_manifest("PrometheusNamespace", {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "prometheus"
            }
        })
        
        # 创建 Prometheus 远程写入策略
        prometheus_policy = iam.Policy(self, "AmazonPrometheusRemoteWritePolicy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "aps:RemoteWrite",
                        "aps:GetSeries",
                        "aps:GetLabels",
                        "aps:GetMetricMetadata"
                    ],
                    resources=[prometheus_workspace.attr_arn]
                )
            ]
        )
        
        # 获取 OIDC 提供者信息
        oidc_provider_arn = eks_cluster.open_id_connect_provider.open_id_connect_provider_arn
        oidc_provider = eks_cluster.cluster_open_id_connect_issuer.replace("https://", "")
        
 
        # 创建 CfnJson 对象来处理条件
        condition_json = CfnJson(self, "ConditionJson", 
            value={
                f"{oidc_provider}:sub": "system:serviceaccount:prometheus:amp-iamproxy-ingest-service-account"
            }
        )

        # 创建 Prometheus 采集 IAM 角色
        prometheus_role = iam.Role(self, "AmpIamproxyIngestRole",
            role_name="amp-iamproxy-ingest-role",
            assumed_by=iam.FederatedPrincipal(
                federated=oidc_provider_arn,
                conditions={
                    "StringEquals": condition_json
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            )
        )
        
        # 附加策略到角色
        prometheus_policy.attach_to_role(prometheus_role)

        
        
        # ========== 添加 AWS Managed Grafana ==========
        # 创建 Grafana 工作区
        grafana_workspace = grafana.CfnWorkspace(self, "StarrocksGrafanaWorkspace",
            account_access_type="CURRENT_ACCOUNT",
            authentication_providers=["AWS_SSO"],
            permission_type="SERVICE_MANAGED",
            name="starrocks-grafana",
            data_sources=["PROMETHEUS", "CLOUDWATCH"],
            role_arn=masters_role.role_arn  # 使用主角色作为 Grafana 工作区角色
        )
        
        # 创建安全组用于 Grafana 访问
        grafana_sg = ec2.SecurityGroup(self, "GrafanaSecurityGroup",
            vpc=vpc,
            description="Security group for Grafana access"
        )
        
        # 允许从 VPC CIDR 访问 Grafana 端口
        grafana_sg.add_ingress_rule(
            ec2.Peer.ipv4(vpc_cidr),
            ec2.Port.tcp(3000),
            "Allow Grafana access from VPC CIDR"
        )
        
        # 输出 Prometheus 和 Grafana 相关信息
        CfnOutput(self, "PrometheusWorkspaceId", 
            value=prometheus_workspace.attr_workspace_id
        )
        
        CfnOutput(self, "PrometheusEndpoint", 
            value=f"https://aps-workspaces.{self.region}.amazonaws.com/workspaces/{prometheus_workspace.attr_workspace_id}"
        )
        
        CfnOutput(self, "GrafanaWorkspaceId", 
            value=grafana_workspace.attr_id
        )
        
        CfnOutput(self, "GrafanaEndpoint", 
            value=f"https://{grafana_workspace.attr_endpoint}"
        )
        

        # Output the cluster endpoint
        CfnOutput(self, "ClusterEndpoint",
            value=cluster.cluster_endpoint.hostname
        )
        
        # Output the writer endpoint
        CfnOutput(self, "WriterEndpoint",
            value=cluster.cluster_endpoint.hostname
        )
        
        # Create S3 bucket with consistent name and retention policy
        bucket = s3.Bucket(self, "WorkshopBucket",
            bucket_name=f"starrocks-on-eks-workshop-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.RETAIN,  # Prevent bucket deletion on stack updates
            auto_delete_objects=False
        )
        
        # Output the bucket name
        CfnOutput(self, "BucketName",
            value=bucket.bucket_name
        )

        # Output the EKS cluster name
        CfnOutput(self, "EKSClusterName",
            value=eks_cluster.cluster_name
        )
        
        # Create ECR repository for Flink CDC
        ecr_repository = ecr.Repository(self, "FlinkCdcRepository",
            repository_name="flink-cdc-pipeline",
            removal_policy=RemovalPolicy.RETAIN,  # Prevent repository deletion on stack updates
            image_scan_on_push=True  # Enable vulnerability scanning
        )
        
        # Output the ECR repository URI
        CfnOutput(self, "EcrDomain",
            value=Fn.select(0, Fn.split("/", ecr_repository.repository_uri))
        )
