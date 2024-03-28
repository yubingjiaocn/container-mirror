import shutil
import subprocess
import tempfile
import requests
import yaml
import logging
from config import (CHARTS_LIST, CHARTS_LIST_TEMPLATE, CHARTS_FAILED_LIST, CHARTS_MIRRORED_LIST, ECR_DOMAIN_CN)
from ecr import login_ecr_cn, create_ecr_repo

def list_charts(repo_url: str) -> list:
    """List all charts and version from a HTTP-based helm repository."""
    try:
        # Fetch the index.yaml file
        logging.info(f"Fetching index.yaml from {repo_url}")
        response = requests.get(repo_url + "index.yaml")
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        index_yaml = response.text

        # Parse the YAML data
        logging.info("Parsing index.yaml")
        index_data = yaml.safe_load(index_yaml)
        charts = []

        # Iterate over entries in the index
        for chart_name, chart_versions in index_data["entries"].items():
            logging.info(f"Processing Chart: {chart_name}")
            versions = []
            for version in chart_versions:
                logging.info(f"Fetched version: {version['version']}")
                versions.append({
                    "version_str": version["version"],
                    "download_url": version["urls"][0]
                })
            charts.append({chart_name: versions})
        return charts

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching index.yaml: {e}")
    except yaml.YAMLError as e:
        logging.error(f"Error parsing index.yaml: {e}")
    except KeyError as e:
        logging.error(f"Error accessing index.yaml data: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def push_charts(url: str, dest_repo: str) -> str:
    """Fetch single helm chart from URL and upload to OCI registry"""
    filename = url.rsplit('/', 1)[1]

    # Download helm charts and write to a temp file, filename should be kept
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            logging.info(f"Downloading {url}")
            response = requests.get(url, allow_redirects=True)
            response.raise_for_status()  # Raise an exception for non-2xx status codes
            chart_file = f"{tmpdir}/{filename}"
            with open(chart_file, 'wb') as f:
                f.write(response.content)
                f.close()
            logging.info(f"{url} downloaded to {chart_file}")
        except Exception as e:
            logging.error(f"Failed to download {url}: {e}")

        # Use Helm CLI to push charts
        try:
            logging.info(f"{url} will be pushed to oci://{dest_repo}")
            push_cmd = ["helm", "push", chart_file, f"oci://{dest_repo}"]
            result = subprocess.run(push_cmd, capture_output=True, text=True, check=True)
            output = result.stderr.splitlines()
            # Filter output and only return OCI reference
            for line in output:
                if line.startswith("Pushed"):
                    return line.replace("Pushed: ", "")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to push {url}: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return None

def helm_login_cn():
    ecr_pass_cn =  login_ecr_cn()[4:]
    login_cmd = ["helm", "registry", "login", "-u", "AWS", "-p", ecr_pass_cn, ECR_DOMAIN_CN]
    try:
        result = subprocess.run(login_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error login to ECR_DOMAIN_CN: {e}")
        logging.error(f"{e.stdout}")
        logging.error(f"{e.stderr}")
        return False

    return result.returncode

def chart_handler():
    """Main function to mirror helm charts"""
    try:
        helm_login_cn()
        charts = []
        proceed_charts = []
        failed_charts = []
        # Read charts list
        with open(CHARTS_LIST, 'r') as f:
            repo_url = [line.strip() for line in f if (not line.startswith('#')) & (len(line.strip()) != 0)]

        # Start process new image
        for repo in repo_url:
            logging.info(f"Processing: {repo}")
            charts = list_charts(repo)
            for chart in charts:
                chart_name = list(chart.keys())[0]
                logging.info(f"Processing Chart: {chart_name}")

                versions = list(chart.values())[0]
                for version in versions:
                    url = version["download_url"]
                    logging.info(f"Processing {url}")
                    # remove http and https prefix of url, and extract only path
                    # example: "https://aws.github.io/eks-charts/abc/appmesh-controller-1.12.5.tgz" to "eks-charts/abc"
                    chart_path = "/".join(url.split("://")[-1].split("/")[1:-1])
                    dest_repo = f"charts/{chart_path}"
                    repo_uri = create_ecr_repo(f"{dest_repo}/{chart_name}")

                    if repo_uri != None:
                        # Helm push should push to parent url
                        # example: "eks-charts/abc/appmesh-controller" to "eks-charts/abc"
                        dest_uri = "/".join(repo_uri.split("/")[:-1])
                        response = push_charts(version["download_url"], dest_uri)

                        if (response != None):
                            proceed_charts.append(response)
                        else:
                            failed_charts.append(url)

        # Handle file actions
        with open(CHARTS_MIRRORED_LIST, 'a+') as f:
            for chart in proceed_charts:
                f.write(f"{chart}\n")

        with open(CHARTS_FAILED_LIST, 'a+') as f:
            for chart in failed_charts:
                f.write(f"{chart}\n")

        shutil.copyfile(CHARTS_LIST_TEMPLATE, CHARTS_LIST)

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")
