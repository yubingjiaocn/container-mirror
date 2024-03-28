import base64
import logging

import boto3
from botocore.exceptions import ClientError

from config import (AWS_CN_AK, AWS_CN_SK, ECR_DOMAIN_CN, ECR_REGION_CN,
                    POLICY_FILE)

ecr_client_cn = boto3.client('ecr', region_name=ECR_REGION_CN,
                                 aws_access_key_id=AWS_CN_AK,
                                aws_secret_access_key=AWS_CN_SK)

def login_ecr(img: str) -> str:
    """Authenticate with AWS ECR."""
    try:
        registry = img.split('/')[0]
        logging.info(f"Logging in to {registry}...")
        # Get region from registry and create client
        img_region = registry.split('.')[3]
        ecr_client = boto3.client('ecr', region_name=img_region)

        ecr_auth = ecr_client.get_authorization_token()
        cred = base64.b64decode(ecr_auth["authorizationData"][0]['authorizationToken']).decode()

        return cred

    except Exception as e:
        logging.error(f"Error logging in to ECR: {e}")

def login_ecr_cn() -> str:
    """Authenticate with AWS ECR CN for pushing image."""
    try:
        ecr_auth_cn = ecr_client_cn.get_authorization_token()["authorizationData"][0]['authorizationToken']
        cred = base64.b64decode(ecr_auth_cn).decode()
        return cred
    except Exception as e:
        logging.error(f"Error logging in to ECR: {e}")
        raise RuntimeError

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