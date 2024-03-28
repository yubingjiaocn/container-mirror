import logging
import shutil
import subprocess

from config import (IMAGES_DENIED_LIST, IMAGES_FAILED_LIST, IMAGES_IGNORE_LIST,
                    IMAGES_LIST, IMAGES_LIST_TEMPLATE, IMAGES_MIRRORED_LIST)
from ecr import create_ecr_repo, delete_ecr_repo, login_ecr, login_ecr_cn
from utils import in_array, is_ecr, replace_domain_name

def image_handler():
    """Main function to mirror container images"""
    try:
        ecr_cred_cn = login_ecr_cn()
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
                if (copy(img, uri_cn, ecr_cred_cn)):
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

def copy(src_img: str, dest_repo: str, dest_cred: str) -> bool:
    """Pull an image from a public repository and push it to ECR in CN region."""
    try:
        if is_ecr(src_img):
            logging.info(f"Image {src_img} is from ECR, logging in...")
            src_cred = login_ecr(src_img)
            src_param = f"--src-creds={src_cred}"
        else:
            src_param = "--src-no-creds"

        tag = src_img.split(':')[-1]
        dest_img = f"{dest_repo}:{tag}"

        dest_param = f"--dest-creds={dest_cred}"

        copy_cmd = ["skopeo", "copy", src_param, dest_param, f"docker://{src_img}", f"docker://{dest_img}"]

        logging.info(f"Image {src_img} will be copied to {dest_img}")

        result = subprocess.run(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        return result

    except Exception as e:
        logging.error(f"Error copying image {src_img}: {e}")
        return False