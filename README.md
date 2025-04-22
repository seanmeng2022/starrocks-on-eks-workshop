# 环境准备

## 搭建基础环境（Cloud9/VPC/EKS/Aurora等）
* 通过Cloudformation部署cloud9以及VPC环境
* 进入AWS Cloud9控制台，登录Cloud9实例
<img width="1327" alt="image" src="https://github.com/user-attachments/assets/d993a3c1-5d94-4b11-ba00-1f2180825012" />

* Git clone下载本次Workshop所需要的代码文件
* 关闭Cloud9 AWS Managed temporary credential功能开关
<img width="1329" alt="image" src="https://github.com/user-attachments/assets/7795bd37-2040-4ca5-898d-683b0f61b906" />

<img width="1330" alt="image" src="https://github.com/user-attachments/assets/7bc4e69f-1ad0-4c27-a327-6a812b3dd55e" />


* 配置aws账号的ak，sk

```
AWS Access Key ID [None]: <您的AK>
AWS Secret Access Key [None]: <您的SK>
Default region name [None]: us-east-1
Default output format [None]:
```

* 运行cloud9环境初始化脚本，该脚本会安装后续workshop需要的相关环境，如helm，kubetcl，扩展EBS磁盘等

```
sh cloud9/cloud9.sh
```

