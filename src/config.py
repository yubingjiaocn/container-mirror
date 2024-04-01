import os
from pathlib import Path

ECR_REGION = 'ap-southeast-1'
ECR_ACCOUNT = "600413481647"

ECR_REGION_CN = 'cn-northwest-1'
ECR_ACCOUNT_CN = "834204282212"
ECR_DOMAIN_CN = f"{ECR_ACCOUNT_CN}.dkr.ecr.{ECR_REGION_CN}.amazonaws.com.cn"

# Domain name mapping
DOMAIN_MAP = {
    "quayio": "quay",
    "quay.io": "quay",
    "gcr.io": "gcr",
    "asia.gcr.io": "gcr",
    "us.gcr.io": "gcr",
    "k8s.gcr.io": "gcr/google_containers",
    "public.ecr.aws": "amazonecr",
    "docker.io": "dockerhub",
    "nvcr.io": "nvcr",
    "registry.k8s.io": "k8s",
    "ghcr.io": "ghcr"
}

PWD = Path(os.path.dirname(os.path.realpath(__file__))).parent.absolute()

# File paths
IMAGES_DENIED_LIST = f'{PWD}/mirror/denied-images.txt'
IMAGES_IGNORE_LIST = f'{PWD}/mirror/ignore-images.txt'
IMAGES_LIST = f'{PWD}/mirror/required-images.txt'
IMAGES_LIST_TEMPLATE= f'{PWD}/src/resources/required-images.txt.template'
IMAGES_MIRRORED_LIST = f'{PWD}/mirror/mirrored-images.txt'
IMAGES_FAILED_LIST = f'{PWD}/mirror/failed-images.txt'
POLICY_FILE = f'{PWD}/src/resources/policy.json'

IMAGES_DAILY_LIST = f'{PWD}/mirror/required-images-daily.txt'

CHARTS_LIST = f'{PWD}/mirror/required-charts.txt'
CHARTS_LIST_TEMPLATE= f'{PWD}/src/resources/required-charts.txt.template'
CHARTS_MIRRORED_LIST = f'{PWD}/mirror/mirrored-charts.txt'
CHARTS_FAILED_LIST = f'{PWD}/mirror/failed-charts.txt'




# AK/SK for AWS-CN region
AWS_CN_AK = os.environ.get("ecr_ak", "")
AWS_CN_SK = os.environ.get("ecr_sk", "")
