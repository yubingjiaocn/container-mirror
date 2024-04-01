import logging
import subprocess
from subprocess import CalledProcessError

from config import IMAGES_DAILY_LIST
from ecr import create_ecr_repo, login_ecr, login_ecr_cn
from utils import is_ecr, replace_domain_name

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def image_daily_handler():
    """Main function to mirror container repos"""
    try:
        ecr_cred_cn = login_ecr_cn()
        repos = []
        proceed_repos = []
        failed_repos = []
        # Read repos list
        with open(IMAGES_DAILY_LIST, 'r') as f:
            repos = [line.strip().split(':')[0] for line in f if (not line.startswith('#')) & (len(line.strip()) != 0)]

        # Start process new image
        for repo in repos:
            logging.info(f"Processing {repo}")

            repo_cn = replace_domain_name(repo)
            uri_cn = create_ecr_repo(repo_cn)
            # Skopeo sync requires parent directory
            dest_uri = "/".join(uri_cn.split("/")[:-1])

            if uri_cn != None:
                if (sync(repo, dest_uri, ecr_cred_cn)):
                    proceed_repos.append(repo)
                    logging.info(f"Complete mirroring of image: {repo}")
                else:
                    failed_repos.append(repo)
                    logging.info(f"Failed mirroring of image: {repo}")

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")


def sync(src_repo: str, dest_repo: str, dest_cred: str) -> bool:
    """Sync a public repository to ECR in CN region."""
    try:
        if is_ecr(src_repo):
            logging.info(f"Repository {src_repo} is from ECR, logging in...")
            src_cred = login_ecr(src_repo)
            src_param = f"--src-creds={src_cred}"
        else:
            src_param = "--src-no-creds"
    except Exception as e:
        logging.error(f"Error login to {src_repo}: {e}")
        return False

    dest_param = f"--dest-creds={dest_cred}"

    logging.info(f"Repo {dest_repo} will be synced with content from {src_repo}")

    try:
        copy_cmd = ["skopeo", "sync", "--src", "docker", "--dest", "docker", "--all", "--keep-going", src_param, dest_param, f"{src_repo}", f"{dest_repo}"]
        process = subprocess.Popen(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            logging.debug(line, end='')

        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, copy_cmd)

    except CalledProcessError as e:
        logging.error(f"Error syncing repo {src_repo}: {e}")
        return False

    return True

if __name__ == "__main__":
    image_daily_handler()