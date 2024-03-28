import logging
import shutil

import docker

from config import (IMAGES_DENIED_LIST, IMAGES_FAILED_LIST, IMAGES_IGNORE_LIST,
                    IMAGES_LIST, IMAGES_LIST_TEMPLATE, IMAGES_MIRRORED_LIST)
from ecr import create_ecr_repo, delete_ecr_repo, login_ecr
from utils import in_array, is_ecr, replace_domain_name

docker_client = docker.from_env()

def image_handler():
    """Main function to mirror container images"""
    try:
        images = []
        proceed_images = []
        failed_images = []
        # Read images list
        with open(IMAGES_DENIED_LIST, 'r') as f:  # Replaced 'blacklist' with 'denied_list'
            denied_list = [line.strip().split(':')[0] for line in f if not line.startswith('#')]
        with open(IMAGES_IGNORE_LIST, 'r') as f:
            ignore_images = [line.strip() for line in f if not line.startswith('#')]
        with open(IMAGES_LIST, 'r') as f:
            images = [line.strip() for line in f if (not line.startswith('#')) & (len(line.strip()) != 0)]

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

        shutil.copyfile(IMAGES_LIST_TEMPLATE, IMAGES_LIST)

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")

def pull_and_push(orig_img: str, target_repo: str) -> bool:
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