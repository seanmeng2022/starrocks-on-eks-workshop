#!/bin/bash

# Exit on error
set -e

echo "Starting Cloud9 environment setup..."

# Update system packages
sudo yum update -y


#update node.js version
sudo yum remove -y nodejs npm
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo yum install -y nodejs

sudo npm install -g aws-cdk --force

# Install kubectl
echo "Installing kubectl..."
curl -o kubectl https://s3.us-west-2.amazonaws.com/amazon-eks/1.27.1/2023-04-19/bin/linux/amd64/kubectl
chmod +x ./kubectl
mkdir -p $HOME/bin && cp ./kubectl $HOME/bin/kubectl && export PATH=$HOME/bin:$PATH
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc

# Install eksctl
echo "Installing eksctl..."
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin
eksctl version

# Install Helm
echo "Installing Helm..."
curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
helm version
helm repo add eks https://aws.github.io/eks-charts
helm repo update eks
helm repo add flink-operator-repo https://archive.apache.org/dist/flink/flink-kubernetes-operator-1.9.0/


# Resize EBS volume (default 100GB if not specified)
echo "Resizing EBS volume..."
SIZE=${1:-100}

# Get the ID of the environment host Amazon EC2 instance
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
INSTANCEID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" -v http://169.254.169.254/latest/meta-data/instance-id 2> /dev/null)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" -v http://169.254.169.254/latest/meta-data/placement/region 2> /dev/null)

# Get the ID of the Amazon EBS volume associated with the instance
VOLUMEID=$(aws ec2 describe-instances \
  --instance-id $INSTANCEID \
  --query "Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId" \
  --output text \
  --region $REGION)

echo "Modifying EBS volume $VOLUMEID to $SIZE GB..."
# Resize the EBS volume
aws ec2 modify-volume --volume-id $VOLUMEID --size $SIZE

# Wait for the resize to finish
echo "Waiting for volume modification to complete..."
while [ \
  "$(aws ec2 describe-volumes-modifications \
    --volume-id $VOLUMEID \
    --filters Name=modification-state,Values="optimizing","completed" \
    --query "length(VolumesModifications)"\
    --output text)" != "1" ]; do
sleep 1
done

echo "Volume modification completed. Extending file system..."

# Check if we're on an NVMe filesystem
if [[ -e "/dev/xvda" && $(readlink -f /dev/xvda) = "/dev/xvda" ]]
then
  echo "Detected standard EBS volume, extending partition..."
  # Rewrite the partition table so that the partition takes up all the space that it can
  sudo growpart /dev/xvda 1

  # Expand the size of the file system
  # Check if we're on AL2 or AL2023
  STR=$(cat /etc/os-release)
  SUBAL2="VERSION_ID=\"2\""
  SUBAL2023="VERSION_ID=\"2023\""
  if [[ "$STR" == *"$SUBAL2"* || "$STR" == *"$SUBAL2023"* ]]
  then
    echo "Detected Amazon Linux 2/2023, using xfs_growfs..."
    sudo xfs_growfs -d /
  else
    echo "Using resize2fs for ext4 filesystem..."
    sudo resize2fs /dev/xvda1
  fi
else
  echo "Detected NVMe filesystem, extending partition..."
  # Rewrite the partition table so that the partition takes up all the space that it can
  sudo growpart /dev/nvme0n1 1

  # Expand the size of the file system
  # Check if we're on AL2 or AL2023
  STR=$(cat /etc/os-release)
  SUBAL2="VERSION_ID=\"2\""
  SUBAL2023="VERSION_ID=\"2023\""
  if [[ "$STR" == *"$SUBAL2"* || "$STR" == *"$SUBAL2023"* ]]
  then
    echo "Detected Amazon Linux 2/2023, using xfs_growfs..."
    sudo xfs_growfs -d /
  else
    echo "Using resize2fs for ext4 filesystem..."
    sudo resize2fs /dev/nvme0n1p1
  fi
fi

# Add Helm repositories (optional - uncomment and modify as needed)
# echo "Adding Helm repositories..."
# helm repo add stable https://charts.helm.sh/stable
# helm repo add bitnami https://charts.bitnami.com/bitnami
# helm repo update

echo "Setup completed successfully!"
echo "Installed versions:"
echo "kubectl version: $(kubectl version --client)"
echo "eksctl version: $(eksctl version)"
echo "helm version: $(helm version)"
echo ""
echo "Disk space:"
df -h
