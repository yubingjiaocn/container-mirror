import base64
import logging
import os
import re
import shutil
from pathlib import Path

import boto3
import docker
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# AWS ECR region and domain name
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
    "docker.io": "dockerhub"
}

PWD = Path(os.path.dirname(os.path.realpath(__file__))).parent.absolute()

# File paths
IMAGES_DENIED_LIST = f'{PWD}/mirror/denied-images.txt'  # Replaced 'blacklist' with 'denied_list'
IMAGES_IGNORE_LIST = f'{PWD}/mirror/ignore-images.txt'
IMAGES_FILE_LIST = f'{PWD}/mirror/required-images.txt'
IMAGES_FILE_LIST_TEMPLATE= f'{PWD}/bin/required-images.txt.template'
IMAGES_MIRRORED_LIST = f'{PWD}/mirror/mirrored-images.txt'
IMAGES_FAILED_LIST = f'{PWD}/mirror/failed-images.txt'
POLICY_FILE = f'{PWD}/mirror/policy.json'

# AK/SK for AWS-CN region
AWS_CN_AK = os.environ.get("ecr_ak", "")
AWS_CN_SK = os.environ.get("ecr_sk", "")

# AWS ECR client
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

    # special handling for ECR... I don't want to do this...
    if is_ecr(uri):
        repo = uri.split('/', 1)[1]
        return repo

    return f"dockerhub/{uri}"

def in_array(elem, arr) -> bool:
    """Helper: Check if an element is present in an array."""
    return elem in arr

def is_ecr(img: str) -> bool:
    """Helper: Check if the image match ECR image reference"""
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
        # Get region from registry and create client
        img_region = registry.split('.')[3]
        ecr_client = boto3.client('ecr', region_name=img_region)

        ecr_auth = ecr_client.get_authorization_token()
        username, password = base64.b64decode(ecr_auth["authorizationData"][0]['authorizationToken']).decode().split(':')

        docker_client.login(
            registry=registry,
            username=username,
            password=password,
            reauth=True
        )

        logging.info(f"Logged in to {registry}.")
        return True

    except Exception as e:
        logging.error(f"Error logging in to ECR: {e}")

def login_ecr_cn():
    """Authenticate with AWS ECR CN for pushing image."""
    try:
        ecr_auth_cn = ecr_client_cn.get_authorization_token()["authorizationData"][0]['authorizationToken']
        username, password = base64.b64decode(ecr_auth_cn).decode().split(':')

        logging.info(f"Logging in to {ECR_DOMAIN_CN}...")
        docker_client.login(
            registry=ECR_DOMAIN_CN,
            username=username,
            password=password
        )
        logging.info(f"Logged in to {ECR_DOMAIN_CN}.")
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

def create_ecr_repo(repo_name: str) -> str:
    """Create an ECR repository in CN region if it doesn't exist and attach a public-read policy."""
    try:
        existing_repos = ecr_client_cn.describe_repositories()['repositories']
        existing_repo_names = [repo['repositoryName'] for repo in existing_repos]
        if repo_name in existing_repo_names:
            logging.info(f"Repository: {repo_name} already exists")
            return f"{ECR_DOMAIN_CN}/{repo_name}"  # Return the URI of the existing repository
        else:
            logging.info(f"Creating repository: {repo_name}")
            uri = ecr_client_cn.create_repository(repositoryName=repo_name)['repository']['repositoryUri']
            attach_policy(repo_name)
            logging.info(f"Created repository with URI: {uri}")
            return uri
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

def delete_ecr_repo(repo_name: str):
    """Delete an ECR repository in CN region"""
    try:
        existing_repos = ecr_client_cn.describe_repositories()['repositories']
        existing_repo_names = [repo['repositoryName'] for repo in existing_repos]
        if repo_name in existing_repo_names:
            logging.info(f"Deleting repository: {repo_name}")
            ecr_client_cn.delete_repository(repositoryName=repo_name, force=True)
            return True
        else:
            logging.info(f"Repository: {repo_name} does not exist")
            return False
    except ClientError as e:
        logging.error(f"Error deleting ECR repository {repo_name}: {e}")
        return False

def pull_and_push(orig_img: str, target_repo: str) -> bool:  # Replaced 'blacklist' with 'denied_list'
    """Pull an image from a public repository and push it to ECR in CN region."""
    try:
        if is_ecr(orig_img):
            logging.info(f"Image {orig_img} is from ECR, logging in...")
            login_ecr(orig_img)

        logging.info(f"Pulling image: {orig_img}")
        docker_client.images.pull(orig_img)

        tag = orig_img.split(':')[-1]

        target_img = f"{target_repo}:{tag}"
        logging.info(f"Tagging {orig_img} as {target_img}")
        docker_client.images.get(orig_img).tag(target_img)

        logging.info(f"Pushing image: {target_img}")
        docker_client.images.push(target_img)
        logging.info(f"Pushed image: {target_img}")

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
            images = [line.strip() for line in f if (not line.startswith('#')) & (len(line.strip()) != 0)]

        # Login to ECR
        login_ecr_cn()

        # Delete denied repositories
        for repo in denied_list:
            delete_ecr_repo(replace_domain_name(repo))

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

            # if the image has no tag, add latest tag to further process
            if not ':' in img:
                img = f"{img}:latest"

            repo_cn = replace_domain_name(img.split(':')[0])
            uri_cn = create_ecr_repo(repo_cn)

            if uri_cn != None:
                if (pull_and_push(img, uri_cn)):
                    proceed_images.append(img)
                    logging.info(f"Complete mirroring of image: {img}")
                else:
                    failed_images.append(img)
                    logging.info(f"Failed mirroring of image: {img}")

        # Handle file actions
        with open(IMAGES_MIRRORED_LIST, 'a+') as f:
            for img in proceed_images:
                f.write(f"{img}\n")

        with open(IMAGES_FAILED_LIST, 'a+') as f:
            for img in failed_images:
                f.write(f"{img}\n")

        shutil.copyfile(IMAGES_FILE_LIST_TEMPLATE, IMAGES_FILE_LIST)

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()