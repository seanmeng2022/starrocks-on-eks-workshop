# Starrocks on EKS workshop
## 说明
该workshop会针对Starrocks在AWS EKS上的部署进行逐步演示和说明。

## 环境准备

### 搭建基础环境（Cloud9/VPC/EKS/Aurora等）
* 通过Cloudformation部署cloud9以及VPC环境
* 进入AWS Cloud9控制台，登录Cloud9实例
<img width="1327" alt="image" src="https://github.com/user-attachments/assets/d993a3c1-5d94-4b11-ba00-1f2180825012" />

* Git clone下载本次Workshop所需要的代码文件
* 关闭Cloud9 AWS Managed temporary credential功能开关
<img width="1329" alt="image" src="https://github.com/user-attachments/assets/7795bd37-2040-4ca5-898d-683b0f61b906" />

<img width="1330" alt="image" src="https://github.com/user-attachments/assets/7bc4e69f-1ad0-4c27-a327-6a812b3dd55e" />


* 配置aws账号的ak，sk

```
Admin:~/environment $ aws configure
AWS Access Key ID [None]: <您的AK>
AWS Secret Access Key [None]: <您的SK>
Default region name [None]: us-east-1
Default output format [None]:
```

* 运行cloud9环境初始化脚本，该脚本会安装后续workshop需要的相关环境，如helm，kubetcl，扩展EBS磁盘等

```
Admin:~/environment $ sh starrocks-on-eks-workshop/cloud9/cloud9.sh 
```
* 部署cdk资源----这里要添加writer endpoint的输出
```
Admin:~/environment $ cd starrocks-on-eks-workshop/cdk-stack/
Admin:~/environment $ pip3 install -r requirement.txt
Admin:~/environment $ cdk bootstrap
Admin:~/environment $ cdk deploy
```

* 记录以下CDK输出

```
Outputs:
StarrocksOnEksStack.BucketName = starrocks-on-eks-workshop-436103886277-us-east-1
StarrocksOnEksStack.ClusterEndpoint = starrocksoneksstack-auroracluster23d869c0-3dezvmq1vogu.cluster-co2wcr3kjcuz.us-east-1.rds.amazonaws.com
StarrocksOnEksStack.EKSClusterName = StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316
StarrocksOnEksStack.FlinkCdcRepositoryUri = 436103886277.dkr.ecr.us-east-1.amazonaws.com/flink-cdc-pipeline
StarrocksOnEksStack.StarrocksEKSClusterConfigCommand324EAEDF = aws eks update-kubeconfig --name StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316 --region us-east-1 --role-arn arn:aws:iam::436103886277:role/StarrocksOnEksStack-EksMastersRoleD1AE213C-E95o0FOZ5SKh
StarrocksOnEksStack.StarrocksEKSClusterGetTokenCommand3DE05C2D = aws eks get-token --cluster-name StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316 --region us-east-1 --role-arn arn:aws:iam::436103886277:role/StarrocksOnEksStack-EksMastersRoleD1AE213C-E95o0FOZ5SKh
StarrocksOnEksStack.WriterEndpoint = starrocksoneksstack-auroracluster23d869c0-3dezvmq1vogu.cluster-co2wcr3kjcuz.us-east-1.rds.amazonaws.com
Stack ARN:
arn:aws:cloudformation:us-east-1:436103886277:stack/StarrocksOnEksStack/6aad7a70-1f64-11f0-8445-12a81ae52fad
```

### 准备基础数据
* 配置相关环境变量
```
Admin:~/environment $ export DB_USERNAME=admin
Admin:~/environment $ export DB_PASSWORD=starrocks
Admin:~/environment $ export DB_HOST=<您的aurora writer endpoint>
有问题：Admin:~/environment $ export STARROCKS_JDBC_HOST=k8s-starrock-astarroc-2606d8b1bf-bfe3718aa734999f.elb.us-east-1.amazonaws.com
有问题：Admin:~/environment $ export STARROCKS_LOAD_HOST=k8s-starrock-astarroc-a2f8705a78-adbc392a7a321fc0.elb.us-east-1.amazonaws.com
```
* 导入数据到Aurora Mysql
```
Admin:~/environment $ python3 load_events.py 
```

### 配置EKS
* 配置EKS访问权限
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ aws eks update-kubeconfig --name StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316 --region us-east-1 --role-arn arn:aws:iam::436103886277:role/StarrocksOnEksStack-EksMastersRoleD1AE213C-E95o0FOZ5SKh
```
* 配置环境变量
```
export EKS_Cluster_ID=<您的集群ID>
export AWS_Account_ID=<您的aws账号ID>
export ECR_ID=<您的ECR地址>
```

* 开启OpenID Provider
```
eksctl utils associate-iam-oidc-provider \
    --cluster $EKS_Cluster_ID \
    --approve
```

* 添加user
```
Admin:~/environment $ kubectl get configmap aws-auth -n kube-system -o yaml > aws-auth-configmap.yaml

这里有问题：Admin:~/environment $ kubectl patch configmap aws-auth -n kube-system --patch '{"data": {"mapUsers": "- userarn: arn:aws:iam::436103886277:user/Sean\n  username: Sean\n  groups:\n    - system:masters"}}'
```


* 创建CSI Controller的IAM Role和SA
```
eksctl create iamserviceaccount \
    --name ebs-csi-controller-sa \
    --namespace kube-system \
    --cluster $EKS_Cluster_ID \
    --role-name AmazonEKS_EBS_CSI_DriverRole \
    --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
    --approve
```

* 创建ELB Controller的IAM Role和SA
```
curl -O https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.11.0/docs/install/iam_policy.json

aws iam create-policy \
    --policy-name AWSLoadBalancerControllerIAMPolicy \
    --policy-document file://iam_policy.json
    

eksctl create iamserviceaccount \
    --name lb-controller-sa \
    --namespace kube-system \
    --cluster $EKS_Cluster_ID \
    --role-name AmazonEKSLoadBalancerControllerRole \
    --attach-policy-arn=arn:aws:iam::${AWS_Account_ID}:policy/AWSLoadBalancerControllerIAMPolicy \
    --approve 

```

* 安装load balancer controller
```
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$EKS_Cluster_ID\
  --set serviceAccount.create=false \
  --set serviceAccount.name=lb-controller-sa

```

* 安装ebs csi driver
```
eksctl create addon \
    --name aws-ebs-csi-driver \
    --cluster $EKS_Cluster_ID \
    --service-account-role-arn arn:aws:iam::${AWS_Account_ID}:role/AmazonEKS_EBS_CSI_DriverRole \
    --force 
```

* 应用新的gp3 SC
```
kubectl apply -f gp3-sc.yaml
```
## Starrocks存算一体部署模式
### 部署Starrocks集群
* 添加Custom Resource：StarRocksCluster
```
kubectl apply -f https://raw.githubusercontent.com/StarRocks/starrocks-kubernetes-operator/main/deploy/starrocks.com_starrocksclusters.yaml
```

* 使用默认部署StarRocks Operator
```
kubectl apply -f https://raw.githubusercontent.com/StarRocks/starrocks-kubernetes-operator/main/deploy/operator.yaml

```
* (Optional）或下载operator.yaml，自定义部署
```
curl -O https://raw.githubusercontent.com/StarRocks/starrocks-kubernetes-operator/main/deploy/operator.yaml
```

* 查看operator部署状态
```
Admin:~/environment $ kubectl get deployment -n starrocks
```
* 部署Starrocks集群
```
kubectl apply -f starrocks_cluster_with_fe_proxy.yaml
```


* 查看pod部署情况，等待所有fe，be pod部署完成
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl get pod -n starrocks 
NAME                                                 READY   STATUS    RESTARTS   AGE
a-starrocks-with-fe-proxy-be-0                       1/1     Running   0          52s
a-starrocks-with-fe-proxy-be-1                       1/1     Running   0          52s
a-starrocks-with-fe-proxy-be-2                       1/1     Running   0          52s
a-starrocks-with-fe-proxy-fe-0                       1/1     Running   0          2m7s
a-starrocks-with-fe-proxy-fe-1                       1/1     Running   0          2m7s
a-starrocks-with-fe-proxy-fe-2                       1/1     Running   0          2m7s
a-starrocks-with-fe-proxy-fe-proxy-b9b64454d-4v5w4   1/1     Running   0          52s
a-starrocks-with-fe-proxy-fe-proxy-b9b64454d-rmcfg   1/1     Running   0          52s
kube-starrocks-operator-6dd67ccf-4fpts               1/1     Running   0          4m7s
```
* 查看相关service地址
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl  get svc -n starrocks
NAME                                         TYPE           CLUSTER-IP       EXTERNAL-IP                                                                     PORT(S)                                                       AGE
a-starrocks-with-fe-proxy-be-search          ClusterIP      None             <none>                                                                          9050/TCP                                                      118s
a-starrocks-with-fe-proxy-be-service         ClusterIP      172.20.45.148    <none>                                                                          9060/TCP,8040/TCP,9050/TCP,8060/TCP                           118s
a-starrocks-with-fe-proxy-fe-proxy-service   LoadBalancer   172.20.245.252   k8s-starrock-astarroc-58cb41cfa5-564177aa162318c5.elb.us-east-1.amazonaws.com   8080:30180/TCP                                                118s
a-starrocks-with-fe-proxy-fe-search          ClusterIP      None             <none>                                                                          9030/TCP                                                      3m13s
a-starrocks-with-fe-proxy-fe-service         LoadBalancer   172.20.243.241   k8s-starrock-astarroc-1eca21357b-201a35ab525806f4.elb.us-east-1.amazonaws.com   8030:31854/TCP,9020:31172/TCP,9030:32755/TCP,9010:30884/TCP   3m13s
```

* 配置环境变量
```
Admin:~/environment $ export STARROCKS_JDBC_HOST=<a-starrocks-with-fe-proxy-fe-service对应的EXTERNAL-IP地址>
Admin:~/environment $ export STARROCKS_LOAD_HOST=<a-starrocks-with-fe-proxy-fe-proxy-service对应的EXTERNAL-IP地址>
```


### S3批量同步数据到Starrocks
* 上传dataset数据至S3
```
aws s3 cp dataset/ s3://<您的S3存储桶ID> --recursive
```
* 登录Starrocks，创建workshop_db_s3
```
Admin:~/environment $ mysql -h $STARROCKS_JDBC_HOST -P 9030 -u root
```
* 登录Starrocks集群，创建workshop_db_s3
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ mysql -h $STARROCKS_JDBC_HOST -P 9030 -u root
Welcome to the MariaDB monitor.  Commands end with ; or \g.
Your MySQL connection id is 5997
Server version: 8.0.33 3.4.2-c15ba7c

Copyright (c) 2000, 2018, Oracle, MariaDB Corporation Ab and others.

Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

MySQL [(none)]> create database workshop_db_s3;
Query OK, 0 rows affected (0.015 sec)

MySQL [(none)]> use workshop_db_s3;
Database changed
```

* 创建相关数据表
```
-- Create game_events table
CREATE TABLE IF NOT EXISTS game_events (
    event_id INT NOT NULL COMMENT "",
    user_id INT NULL COMMENT "",
    event_time DATETIME NULL COMMENT "",
    event_type VARCHAR(50) NULL COMMENT "",
    event_detail TEXT NULL COMMENT "",
    level_id INT NULL COMMENT "",
    result VARCHAR(10) NULL COMMENT "",
    duration INT NULL COMMENT ""
) ENGINE=OLAP 
PRIMARY KEY(event_id)
DISTRIBUTED BY HASH(event_id)
PROPERTIES (
    "compression" = "LZ4",
    "enable_persistent_index" = "true",
    "fast_schema_evolution" = "true",
    "replicated_storage" = "true",
    "replication_num" = "1"
);

-- Create game_progress table
CREATE TABLE IF NOT EXISTS game_progress (
    progress_id INT NOT NULL COMMENT "",
    user_id INT NULL COMMENT "",
    level INT NULL COMMENT "",
    experience INT NULL COMMENT "",
    game_coins INT NULL COMMENT "",
    diamonds INT NULL COMMENT "",
    update_time DATETIME NULL COMMENT "",
    total_play_time INT NULL COMMENT ""
) ENGINE=OLAP 
PRIMARY KEY(progress_id)
DISTRIBUTED BY HASH(progress_id)
PROPERTIES (
    "compression" = "LZ4",
    "enable_persistent_index" = "true",
    "fast_schema_evolution" = "true",
    "replicated_storage" = "true",
    "replication_num" = "1"
);

-- Create payment_transactions table
CREATE TABLE IF NOT EXISTS payment_transactions (
    transaction_id INT NOT NULL COMMENT "",
    user_id INT NULL COMMENT "",
    transaction_time DATETIME NULL COMMENT "",
    amount DECIMAL(10,2) NULL COMMENT "",
    payment_method VARCHAR(50) NULL COMMENT "",
    currency VARCHAR(10) NULL COMMENT "",
    item_id INT NULL COMMENT "",
    item_name VARCHAR(100) NULL COMMENT "",
    item_type VARCHAR(50) NULL COMMENT ""
) ENGINE=OLAP 
PRIMARY KEY(transaction_id)
DISTRIBUTED BY HASH(transaction_id)
PROPERTIES (
    "compression" = "LZ4",
    "enable_persistent_index" = "true",
    "fast_schema_evolution" = "true",
    "replicated_storage" = "true",
    "replication_num" = "1"
);

-- Create user_login table
CREATE TABLE IF NOT EXISTS user_login (
    login_id INT NOT NULL COMMENT "",
    user_id INT NULL COMMENT "",
    login_time DATETIME NULL COMMENT "",
    logout_time DATETIME NULL COMMENT "",
    session_length INT NULL COMMENT "",
    ip_address VARCHAR(50) NULL COMMENT "",
    device_id VARCHAR(50) NULL COMMENT ""
) ENGINE=OLAP 
PRIMARY KEY(login_id)
DISTRIBUTED BY HASH(login_id)
PROPERTIES (
    "compression" = "LZ4",
    "enable_persistent_index" = "true",
    "fast_schema_evolution" = "true",
    "replicated_storage" = "true",
    "replication_num" = "1"
);

-- Create user_profile table
CREATE TABLE IF NOT EXISTS user_profile (
    user_id INT NOT NULL COMMENT "",
    register_time DATETIME NULL COMMENT "",
    channel VARCHAR(50) NULL COMMENT "",
    device_type VARCHAR(50) NULL COMMENT "",
    os_version VARCHAR(50) NULL COMMENT "",
    region VARCHAR(50) NULL COMMENT "",
    gender VARCHAR(10) NULL COMMENT "",
    age INT NULL COMMENT "",
    vip_level INT NULL COMMENT ""
) ENGINE=OLAP 
PRIMARY KEY(user_id)
DISTRIBUTED BY HASH(user_id)
PROPERTIES (
    "compression" = "LZ4",
    "enable_persistent_index" = "true",
    "fast_schema_evolution" = "true",
    "replicated_storage" = "true",
    "replication_num" = "1"
);
```
* 提交导入作业
```

LOAD LABEL game_events
(
    DATA INFILE("s3://starrocks-on-eks-workshop-436103886277-us-east-1/game_events.csv")
    INTO TABLE game_events
    COLUMNS TERMINATED BY ','
    FORMAT AS "CSV"
    (
        skip_header = 1
        enclose = "\""
    )
)
WITH BROKER
(
    "aws.s3.enable_ssl" = "true",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.region" = "us-east-1",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>"
)
PROPERTIES
(
    "timeout" = "72000"
);


LOAD LABEL game_progress
(
    DATA INFILE("s3://starrocks-on-eks-workshop-436103886277-us-east-1/game_progress.csv")
    INTO TABLE game_progress
    COLUMNS TERMINATED BY ','
    FORMAT AS "CSV"
    (
        skip_header = 1
    )
)
WITH BROKER
(
    "aws.s3.enable_ssl" = "true",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.region" = "us-east-1",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>"
)
PROPERTIES
(
    "timeout" = "72000"
);


LOAD LABEL payment_transactions
(
    DATA INFILE("s3://starrocks-on-eks-workshop-436103886277-us-east-1/payment_transactions.csv")
    INTO TABLE payment_transactions
    COLUMNS TERMINATED BY ','
    FORMAT AS "CSV"
    (
        skip_header = 1
    )
)
WITH BROKER
(
    "aws.s3.enable_ssl" = "true",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.region" = "us-east-1",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>"
)
PROPERTIES
(
    "timeout" = "72000"
);


LOAD LABEL user_login
(
    DATA INFILE("s3://starrocks-on-eks-workshop-436103886277-us-east-1/user_login.csv")
    INTO TABLE user_login
    COLUMNS TERMINATED BY ','
    FORMAT AS "CSV"
    (
        skip_header = 1
    )
)
WITH BROKER
(
    "aws.s3.enable_ssl" = "true",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.region" = "us-east-1",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>"
)
PROPERTIES
(
    "timeout" = "72000"
);

LOAD LABEL user_profile
(
    DATA INFILE("s3://starrocks-on-eks-workshop-436103886277-us-east-1/user_profile.csv")
    INTO TABLE user_profile
    COLUMNS TERMINATED BY ','
    FORMAT AS "CSV"
    (
        skip_header = 1
    )
)
WITH BROKER
(
    "aws.s3.enable_ssl" = "true",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.region" = "us-east-1",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>"
)
PROPERTIES
(
    "timeout" = "72000"
);

```
* 您可以通过如下SQL查看导入进度
```
MySQL [workshop_db_s3]> SELECT * FROM information_schema.loads WHERE LABEL = 'game_events';
```

### Mysql实时同步数据到Starrocks
* 安装cert manger
```
Admin:~/environment $ kubectl apply -f https://github.com/jetstack/cert-manager/releases/download/v1.8.2/cert-manager.yaml

```
* 安装flink operator
```
Admin:~/environment $ kubectl create ns flinkcdc 
Admin:~/environment $ helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator --namespace flinkcdc

```
* 查看operator状态
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl get pods -n flinkcdc
NAME                                        READY   STATUS    RESTARTS   AGE
flink-kubernetes-operator-f8997bf9d-99k24   2/2     Running   0          51s
```
* 登录ECR仓库
```
Admin:~/environment $ aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${AWS_Account_ID}.dkr.ecr.us-east-1.amazonaws.com
```
* 构建Docker镜像
```
Admin:~/environment/flink-cdc/docker $ docker build -t $ECR_ID:latest .
```

* 上传Docker镜像
```
Admin:~/environment/flink-cdc/docker $ docker push $ECR_ID:latest
```
























