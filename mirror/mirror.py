import os
import re
import boto3
from botocore.exceptions import ClientError
import docker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# AWS ECR region and domain name
ECR_REGION = 'ap-southeast-1'
ECR_ACCOUNT = "600413481647"
ECR_DOMAIN = f"{ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com"

ECR_REGION_CN = 'cn-northwest-1'
ECR_ACCOUNT_CN = "834204282212"

# Domain name mapping
DOMAIN_MAP = {
    "quayio": "quay",
    "quay.io": "quay",
    "gcr.io": "gcr",
    "asia.gcr.io": "gcr",
    "us.gcr.io": "gcr",
    "k8s.gcr.io": "gcr/google_containers",
    "amazonaws.com": "amazonecr",
    "public.ecr.aws": "amazonecr",
    "docker.io": "dockerhub"
}

# File paths
IMAGES_DENIED_LIST = 'denied-images.txt'  # Replaced 'blacklist' with 'denied_list'
IMAGES_IGNORE_LIST = 'ignore-images.txt'
IMAGES_FILE_LIST = 'required-images.txt'
IMAGES_MIRRORED_LIST = 'mirrored-images.txt'
POLICY_FILE = 'policy.json'

# AK/SK for AWS-CN region
AWS_CN_AK = os.environ.get("ecr_ak", "")
AWS_CN_SK = os.environ.get("ecr_sk", "")

# AWS ECR client
ecr_client = boto3.client('ecr', region_name=ECR_REGION)
ecr_client_cn = boto3.client('ecr', region_name=ECR_REGION_CN,
                                 aws_access_key_id=AWS_CN_AK,
                                aws_secret_access_key=AWS_CN_SK)

# Docker client
docker_client = docker.from_env()

## Helper Functions

def replace_domain_name(uri: str) -> str:
    """
    Replace the domain name in the URI with the corresponding value from the DOMAIN_MAP.
    If the domain is not found in the map, prepend 'dockerhub/' to the URI.
    """
    for domain, prefix in DOMAIN_MAP.items():
        if uri.startswith(domain):
            return uri.replace(domain, prefix, 1)
    return f"dockerhub/{uri}"

def in_array(elem, arr) -> bool:
    """Helper: Check if an element is present in an array."""
    return elem in arr

def is_ecr(img: str) -> bool:
    """Define the pattern to match ECR image reference"""
    pattern = r'^(\d+)\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com/(.+)$'
    match = re.match(pattern, img)
    if match:
        return True
    else:
        return False

def login_ecr(img: str) -> bool:
    """Authenticate with AWS ECR."""
    try:
        registry = img.split('/')[0]
        logging.info(f"Logging in to {registry}...")
        # Login to ECR of Global region
        ecr_auth = ecr_client.get_authorization_token(registryIds=[ECR_ACCOUNT])["authorizationData"][0]['authorizationToken']

        docker_client.login(
            registry=registry,
            username="AWS",
            password=ecr_auth
        )
        logging.info(f"Logged in to {registry}.")
        return True

    except Exception as e:
        logging.error(f"Error logging in to ECR: {e}")

def login_ecr_cn(account: str, region: str):
    """Authenticate with AWS ECR CN for pushing image."""
    try:
        ecr_auth_cn = ecr_client_cn.get_authorization_token(registryIds=[account])["authorizationData"][0]['authorizationToken']
        ecr_domain_cn = f"{account}.dkr.ecr.{region}.amazonaws.com.cn"
        logging.info(f"Logging in to {ecr_domain_cn}...")
        docker_client.login(
            registry=ecr_domain_cn,
            username="AWS",
            password=ecr_auth_cn
        )
        logging.info(f"Logged in to {ecr_domain_cn}.")
        return True
    except Exception as e:
        logging.error(f"Error logging in to ECR: {e}")
        raise RuntimeError

def get_local_image_digest(image_name: str) -> str:
    """Get the digest of a local Docker image."""
    try:
        image = docker_client.images.get(image_name)
        return image.attrs['RepoDigests'][0].split('@')[-1]
    except docker.errors.ImageNotFound:
        logging.warning(f"Image not found: {image_name}")
        return None
    except Exception as e:
        logging.error(f"Error getting digest for {image_name}: {e}")
        return None

def is_remote_image_exists(repo_name: str, tag: str, digest: str) -> bool:
    """Check if a image in CN ECR exists with the given tag and digest."""
    try:
        response = ecr_client_cn.describe_images(repositoryName=repo_name, imageIds=[{'imageDigest': digest}])
        image_details = response.get('imageDetails', [])
        for image in image_details:
            if tag in image.get('imageTags', []):
                return True
        return False
    except ClientError as e:
        logging.error(f"Error checking remote image existence: {e}")
        return False

## Main Functions

def create_ecr_repo(repo_name: str, denied_list: list) -> str:
    """Create an ECR repository in CN region if it doesn't exist and attach a public-read policy."""
    if in_array(repo_name, denied_list):
        logging.info(f"Repository: {repo_name} is on the denied list")
        return None

    try:
        existing_repos = ecr_client_cn.describe_repositories()['repositories']
        existing_repo_names = [repo['repositoryName'] for repo in existing_repos]
        if repo_name in existing_repo_names:
            logging.info(f"Repository: {repo_name} already exists")
        else:
            logging.info(f"Creating repository: {repo_name}")
            ecr_client_cn.create_repository(repositoryName=repo_name)
            attach_policy(repo_name)
        return repo_name
    except ClientError as e:
        logging.error(f"Error creating ECR repository {repo_name}: {e}")

def attach_policy(repo_name: str):
    """Attach a public-read policy to an ECR repository in CN region."""
    try:
        with open(POLICY_FILE, 'r') as f:
            policy_text = f.read()
        ecr_client_cn.set_repository_policy(repositoryName=repo_name, policyText=policy_text)
        logging.info(f"Attached public-read policy to ECR repository: {repo_name}")
    except (ClientError, FileNotFoundError) as e:
        logging.error(f"Error attaching policy to ECR repository {repo_name}: {e}")

def delete_ecr_repo(repo_name: str, denied_list):  # Replaced 'blacklist' with 'denied_list'
    """Delete an ECR repository in CN region if it's on the denied list."""
    if in_array(repo_name, denied_list):
        try:
            existing_repos = ecr_client.describe_repositories()['repositories']
            existing_repo_names = [repo['repositoryName'] for repo in existing_repos]
            if repo_name in existing_repo_names:
                logging.info(f"Deleting repository: {repo_name}")
                ecr_client_cn.delete_repository(repositoryName=repo_name, force=True)
                return True
        except ClientError as e:
            logging.error(f"Error deleting ECR repository {repo_name}: {e}")
            return False

def pull_and_push(orig_img: str, target_registry: str) -> bool:  # Replaced 'blacklist' with 'denied_list'
    """Pull an image from a public repository and push it to ECR in CN region."""
    try:
        if is_ecr(orig_img):
            logging.info(f"Image {orig_img} is from ECR, logging in...")
            login_ecr(orig_img)

        logging.info(f"Pulling image: {orig_img}")
        docker_client.images.pull(orig_img)

        target_img = f"{target_registry}/{replace_domain_name(orig_img)}"
        logging.info(f"Tagging {orig_img} as {target_img}")
        docker_client.images.get(orig_img).tag(target_img)

        digest = get_local_image_digest(target_img)
        if digest and is_remote_image_exists(target_img.split('/')[1], target_img.split(':')[-1], digest):
            logging.warning(f"Image {target_img} already exists, skipping push")
        else:
            logging.info(f"Pushing image: {target_img}")
            docker_client.images.push(target_img)
        return True
    except docker.errors.APIError as e:
        logging.error(f"Error pulling or pushing image {orig_img}: {e}")
        return False

def main():
    """Main function to orchestrate the script."""
    try:
        images = []
        proceed_images = []
        failed_images = []
        # Read images list
        with open(IMAGES_DENIED_LIST, 'r') as f:  # Replaced 'blacklist' with 'denied_list'
            denied_list = [line.strip().split(':')[0] for line in f if not line.startswith('#')]
        with open(IMAGES_IGNORE_LIST, 'r') as f:
            ignore_images = [line.strip() for line in f if not line.startswith('#')]
        with open(IMAGES_FILE_LIST, 'r') as f:
            images = [line.strip() for line in f if not line.startswith('#')]

        # Login to ECR
        login_ecr()

        # Delete denied repositories
        for repo in denied_list:
            delete_ecr_repo(replace_domain_name(repo), denied_list)

        # Start process new image
        for img in images:
            logging.info(f"Processing {img}")
            registry = img.split('/')[0]
            if in_array(registry, denied_list):
                logging.info(f"Repository: {registry} is on the denied list, skipping")
                continue

            if in_array(img, ignore_images):
                logging.info(f"Ignoring image: {img}")
                continue

            img_cn = replace_domain_name(img)
            if create_ecr_repo(img_cn) != None:
                if (pull_and_push(img_cn, denied_list, ignore_images)):
                    proceed_images.append(img)
                else:
                    failed_images.append(img)

        # Handle file actions


    except FileNotFoundError as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()