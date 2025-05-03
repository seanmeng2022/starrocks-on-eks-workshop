# Starrocks on EKS workshop
## 说明
该workshop会针对Starrocks在AWS EKS上的部署（包括存算一体，存算分离模式），和相关数据同步方式（批同步，CDC同步）进行说明和Demo。


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
* 部署cdk资源
```
Admin:~/environment $ cd starrocks-on-eks-workshop/cdk-stack/
Admin:~/environment $ pip3 install -r requirement.txt
Admin:~/environment $ cdk bootstrap
Admin:~/environment $ cdk deploy
```


```
Outputs:
StarrocksOnEksStack.BucketName = starrocks-on-eks-workshop-436103886277-us-east-1
StarrocksOnEksStack.ClusterEndpoint = starrocksoneksstack-auroracluster23d869c0-3dezvmq1vogu.cluster-co2wcr3kjcuz.us-east-1.rds.amazonaws.com
StarrocksOnEksStack.EKSClusterName = StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316
StarrocksOnEksStack.FlinkCdcRepositoryUri = 436103886277.dkr.ecr.us-east-1.amazonaws.com/flink-cdc-pipeline
这里要增加一个ECR的地址输出
StarrocksOnEksStack.StarrocksEKSClusterConfigCommand324EAEDF = aws eks update-kubeconfig --name StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316 --region us-east-1 --role-arn arn:aws:iam::436103886277:role/StarrocksOnEksStack-EksMastersRoleD1AE213C-E95o0FOZ5SKh
StarrocksOnEksStack.StarrocksEKSClusterGetTokenCommand3DE05C2D = aws eks get-token --cluster-name StarrocksEKSCluster3A432E2B-bb3cea276eb24eb8a36a274fcee16316 --region us-east-1 --role-arn arn:aws:iam::436103886277:role/StarrocksOnEksStack-EksMastersRoleD1AE213C-E95o0FOZ5SKh
StarrocksOnEksStack.WriterEndpoint = starrocksoneksstack-auroracluster23d869c0-3dezvmq1vogu.cluster-co2wcr3kjcuz.us-east-1.rds.amazonaws.com
Stack ARN:
arn:aws:cloudformation:us-east-1:436103886277:stack/StarrocksOnEksStack/6aad7a70-1f64-11f0-8445-12a81ae52fad
```


* 记录以上CDK输出，其中：
    *  StarrocksOnEksStack.BucketName：后续存放数据集的S3桶
    *  StarrocksOnEksStack.WriterEndpoint：Aurora Cluster的写入Endpoint，后续数据会同步写入到Aurora
    *  StarrocksOnEksStack.EKSClusterName：EKS集群ID
    *  StarrocksOnEksStack.StarrocksEKSClusterConfigCommand324EAEDF：您的EKS访问权限配置命令
 
  
### 准备基础数据
* 配置相关环境变量
```
Admin:~/environment $ export DB_USERNAME=admin
Admin:~/environment $ export DB_PASSWORD=starrocks
Admin:~/environment $ export DB_HOST=<您的aurora writer endpoint>
```
* 导入数据到Aurora Mysql
```
Admin:~/environment $ python3 load_events.py 
```

### 配置EKS
* 配置EKS访问权限
```
Admin:~/environment $ 上述CDK输出的EKS集群访问权限配置命令（StarrocksOnEksStack.StarrocksEKSClusterConfigCommand）
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

这里有问题，要确认workshop账号是什么user：Admin:~/environment $ kubectl patch configmap aws-auth -n kube-system --patch '{"data": {"mapUsers": "- userarn: arn:aws:iam::436103886277:user/Sean\n  username: Sean\n  groups:\n    - system:masters"}}'
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
## 部署存算一体模式Starrocks集群
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


## 部署存算分离模式Starrocks集群（Optional）

### 清除前期资源
如果您的集群中已经部署了第二章存算一体Starrocks集群，可以先将资源清除。
* 删除Starrocks集群
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl delete -f starrocks_cluster_with_fe_proxy.yaml
Admin:~/environment/starrocks-on-eks-workshop/flink-cdc (main) $ kubectl delete -f flink-cdc-pipeline-job.yaml
```
### 部署集群
```
Admin:~/environment (main) $ kubectl apply -f starrocks_cluster_shared_data_mode.yaml 

```

* 确认FE，BE pod已正常启动
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl get pod -n starrocks 
NAME                                                       READY   STATUS    RESTARTS   AGE
a-starrocks-in-share-data-mode-cn-0                        1/1     Running   0          2m24s
a-starrocks-in-share-data-mode-cn-1                        1/1     Running   0          2m24s
a-starrocks-in-share-data-mode-cn-2                        1/1     Running   0          2m24s
a-starrocks-in-share-data-mode-fe-0                        1/1     Running   0          3m9s
a-starrocks-in-share-data-mode-fe-1                        1/1     Running   0          3m9s
a-starrocks-in-share-data-mode-fe-2                        1/1     Running   0          3m9s
a-starrocks-in-share-data-mode-fe-proxy-6775cd659d-qv7zq   1/1     Running   0          2m24s
a-starrocks-in-share-data-mode-fe-proxy-6775cd659d-rt4rz   1/1     Running   0          2m24s
kube-starrocks-operator-6dd67ccf-4fpts                     1/1     Running   0          27h


Admin:~/environment/starrocks-on-eks-workshop (main) $ kubectl get svc -n starrocks
NAME                                              TYPE           CLUSTER-IP       EXTERNAL-IP                                                                     PORT(S)                                                       AGE
a-starrocks-in-share-data-mode-cn-search          ClusterIP      None             <none>                                                                          9050/TCP                                                      3m57s
a-starrocks-in-share-data-mode-cn-service         ClusterIP      172.20.29.125    <none>                                                                          9060/TCP,8040/TCP,9050/TCP,8060/TCP                           3m57s
a-starrocks-in-share-data-mode-fe-proxy-service   LoadBalancer   172.20.155.46    k8s-starrock-astarroc-9c493cedcb-3e77538ba6ecf2ce.elb.us-east-1.amazonaws.com   8080:30180/TCP                                                3m57s
a-starrocks-in-share-data-mode-fe-search          ClusterIP      None             <none>                                                                          9030/TCP                                                      4m42s
a-starrocks-in-share-data-mode-fe-service         LoadBalancer   172.20.120.188   k8s-starrock-astarroc-602a0cdd84-3f9fad20e72d8118.elb.us-east-1.amazonaws.com   8030:31944/TCP,9020:31284/TCP,9030:32516/TCP,9010:30699/TCP   4m42s
```

* 配置相关环境变量
```
Admin:~/environment/starrocks-on-eks-workshop (main) $ export STARROCKS_JDBC_HOST=k8s-starrock-astarroc-602a0cdd84-3f9fad20e72d8118.elb.us-east-1.amazonaws.com
Admin:~/environment/starrocks-on-eks-workshop (main) $ export STARROCKS_LOAD_HOST=k8s-starrock-astarroc-9c493cedcb-3e77538ba6ecf2ce.elb.us-east-1.amazonaws.com
```

* 登录Starrocks
```
Admin:~/environment (main) $ mysql -h $STARROCKS_JDBC_HOST -P 9030 -u root
```
* 基于S3，创建默认存储卷
```
CREATE STORAGE VOLUME def_volume
TYPE = S3
LOCATIONS = ("s3://<您的Bucket Name>")
PROPERTIES
(
    "enabled" = "true",
    "aws.s3.region" = "us-east-1",
    "aws.s3.endpoint" = "https://s3.us-east-1.amazonaws.com",
    "aws.s3.use_aws_sdk_default_behavior" = "false",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.access_key" = "<您的AK>",
    "aws.s3.secret_key" = "<您的SK>",
    "aws.s3.enable_partitioned_prefix" = "true"
);


SET def_volume AS DEFAULT STORAGE VOLUME;

```

* 确认已配置成功
```
MySQL [(none)]> DESC STORAGE VOLUME def_volume\G
*************************** 1. row ***************************
     Name: def_volume
     Type: S3
IsDefault: true
 Location: s3://starrocks-on-eks-workshop-436103886277-us-east-1
   Params: {"aws.s3.access_key":"******","aws.s3.secret_key":"******","aws.s3.num_partitioned_prefix":"256","aws.s3.endpoint":"https://s3.us-east-1.amazonaws.com","aws.s3.region":"us-east-1","aws.s3.use_instance_profile":"false","aws.s3.enable_partitioned_prefix":"true","aws.s3.use_aws_sdk_default_behavior":"false"}
  Enabled: true
  Comment: 
1 row in set (0.042 sec)

```


* 创建数据库和云原生表
```
MySQL [(none)]> CREATE DATABASE workshop_db_s3_shared_data;
Query OK, 0 rows affected (0.016 sec)

MySQL [(none)]> use workshop_db_s3_shared_data;
Database changed


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
    "storage_volume" = "def_volume",
    "datacache.enable" = "true"
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
    "storage_volume" = "def_volume",
    "datacache.enable" = "true"
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
    "storage_volume" = "def_volume",
    "datacache.enable" = "true"
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
    "storage_volume" = "def_volume",
    "datacache.enable" = "true"
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
    "storage_volume" = "def_volume",
    "datacache.enable" = "true"
);
```



## 数据同步
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

### Mysql实时同步数据到Starrocks（Optional）
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
Admin:~/environment/flink-cdc/docker $ docker build -t $ECR_ID/flink-cdc-pipeline:latest .
```

* 上传Docker镜像
```
Admin:~/environment/flink-cdc/docker $ docker push $ECR_ID/flink-cdc-pipeline:latest
```
* 创建Flink-CDC ConfigMap
```
Admin:~/environment/flink-cdc $ envsubst < flinkcdc-configmap.yaml | kubectl apply -f -

```


* 提交Flink-CDC Job
```
Admin:~/environment/flink-cdc $ envsubst < flink-cdc-pipeline-job.yaml | kubectl apply -f -
```

* 您可以通过如下方式访问Flink UI，以查看导入任务完成情况
```
Admin:~/environment/starrocks-on-eks-workshop/flink-cdc (main) $ kubectl port-forward svc/flink-cdc-pipeline-job-rest 8081:8081 -n flinkcdc

点击cloud9 IDE页面的Preview - Preview Running Application选项，访问当前url的8081端口

```




## 游戏数据分析
### 利用Bitmap实现游戏用户圈选
* 创建用户标签表
首先需要创建一个用户标签表，将各种用户特征转换为bitmap标记：
```
CREATE TABLE user_tags (
    tag_date DATE,
    tag_name VARCHAR(64),
    user_bitmap BITMAP BITMAP_UNION
) ENGINE = OLAP
AGGREGATE KEY(tag_date, tag_name)
DISTRIBUTED BY HASH(tag_name) BUCKETS 10;
```

* 生成用户标签Bitmap
```
-- 插入性别标签
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT CURRENT_DATE() AS tag_date, 'gender_male' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_profile
WHERE gender = '男'
UNION ALL
SELECT CURRENT_DATE() AS tag_date, 'gender_female' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_profile
WHERE gender = '女';

-- 插入年龄段标签
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT CURRENT_DATE() AS tag_date, 'age_18_to_24' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_profile
WHERE age BETWEEN 18 AND 24
UNION ALL
SELECT CURRENT_DATE() AS tag_date, 'age_25_to_34' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_profile
WHERE age BETWEEN 25 AND 34
UNION ALL
SELECT CURRENT_DATE() AS tag_date, 'age_35_plus' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_profile
WHERE age >= 35;

-- 插入VIP等级标签
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT 
    CURRENT_DATE() AS tag_date, 
    CONCAT('vip_level_', vip_level) AS tag_name, 
    BITMAP_UNION(TO_BITMAP(user_id)) AS user_bitmap
FROM user_profile
GROUP BY vip_level;


-- 插入活跃用户标签（最近7天有登录）
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT CURRENT_DATE() AS tag_date, 'active_last_7days' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM user_login
WHERE login_time >= DATE_SUB('2025-04-23', INTERVAL 7 DAY);


-- 插入付费用户标签（有过任何交易记录）
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT CURRENT_DATE() AS tag_date, 'has_payment' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM payment_transactions
GROUP BY user_id;

-- 插入高级玩家标签（游戏等级30以上）
INSERT INTO user_tags (tag_date, tag_name, user_bitmap)
SELECT CURRENT_DATE() AS tag_date, 'high_level_player' AS tag_name, TO_BITMAP(user_id) AS user_bitmap
FROM game_progress
WHERE level >= 30;
```


* 简单圈选示例
```
-- 查询"男性且VIP等级大于等于1"的用户数量
SELECT 
    BITMAP_COUNT(BITMAP_AND(a.user_bitmap, b.user_bitmap)) AS user_count
FROM 
    user_tags a JOIN user_tags b
    ON a.tag_date = b.tag_date
WHERE 
    a.tag_date = CURRENT_DATE()
    AND a.tag_name = 'gender_male' 
    AND b.tag_name IN ('vip_level_1', 'vip_level_2')
    AND b.tag_date = CURRENT_DATE();
```
* 复杂圈选示例
```
-- 查询"35岁以上女性且是高级玩家且最近7天活跃"的用户ID列表
WITH latest_date AS (
    SELECT MAX(tag_date) AS max_date
    FROM user_tags
    WHERE tag_name IN ('gender_female', 'age_35_plus', 'high_level_player', 'active_last_7days')
),
target_users AS (
    SELECT 
        BITMAP_AND(
            BITMAP_AND(a.user_bitmap, b.user_bitmap),
            BITMAP_AND(c.user_bitmap, d.user_bitmap)
        ) AS result_bitmap
    FROM 
        user_tags a, 
        user_tags b,
        user_tags c,
        user_tags d,
        latest_date ld
    WHERE 
        a.tag_date = ld.max_date
        AND b.tag_date = ld.max_date
        AND c.tag_date = ld.max_date
        AND d.tag_date = ld.max_date
        AND a.tag_name = 'gender_female'
        AND b.tag_name = 'age_35_plus'
        AND c.tag_name = 'high_level_player'
        AND d.tag_name = 'active_last_7days'
)
SELECT 
    BITMAP_TO_STRING(result_bitmap) AS user_ids,
    BITMAP_COUNT(result_bitmap) AS user_count
FROM 
    target_users;
```







