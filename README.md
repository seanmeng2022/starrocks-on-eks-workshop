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
这里有问题要看下：export ECR_ID=<您的ECR地址>
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
