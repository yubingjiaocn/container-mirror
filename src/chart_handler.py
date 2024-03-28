def list_charts(repo_url):
    try:
        repo_index = urlopen(repo_url + "/index.yaml")
    except Exception as e:
        logging.error(f"Failed to fetch repository index: {e}")
        return {}

    try:
        repo_data = ElementTree.parse(repo_index)
    except Exception as e:
        logging.error(f"Failed to parse repository index: {e}")
        return {}

    charts = {}
    for entry in repo_data.findall("{http://kubernetes.io/helm/}entry"):
        chart_name = entry.find("{http://kubernetes.io/helm/}name").text
        versions = [version.text for version in entry.findall("{http://kubernetes.io/helm/}version")]
        charts[chart_name] = versions

    logging.info("Charts in the repository:")
    for chart, versions in charts.items():
        logging.info(f"- {chart}: {', '.join(versions)}")

    return charts

def package_and_push_charts(charts, oci_registry):
    for chart, versions in charts.items():
        for version in versions:
            logging.info(f"Packaging {chart} {version} as OCI artifact...")

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    chart_file = os.path.join(tmpdir, f"{chart}-{version}.tgz")
                    subprocess.run(["helm", "package", f"{chart}--version={version}", "--destination", tmpdir], check=True)

                    logging.info(f"Pushing {chart} {version} to {oci_registry}/{chart}:{version}")

                    subprocess.run(["helm", "push", chart_file, "oci://" + oci_registry + "/" + chart + ":" + version], check=True)

            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to package or push {chart} {version}: {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")

def chart_handler():
    """Main function to mirror helm charts"""
    try:
        charts = []
        proceed_charts = []
        failed_charts = []
        # Read charts list
        with open(CHARTS_LIST, 'r') as f:
            repo_url = [line.strip() for line in f if (not line.startswith('#')) & (len(line.strip()) != 0)]

        # Start process new image
        for repo in repo_url:
            logging.info(f"Processing {repo}")
            charts = list_charts(repo)
            for version in charts.items():
                package_and_push_charts(version, ECR_DOMAIN_CN)

        # Handle file actions
        with open(IMAGES_MIRRORED_LIST, 'a+') as f:
            for chart in proceed_charts:
                f.write(f"{chart}\n")

        with open(IMAGES_FAILED_LIST, 'a+') as f:
            for chart in failed_charts:
                f.write(f"{chart}\n")

        shutil.copyfile(CHARTS_LIST_TEMPLATE, CHARTS_LIST)

    except FileNotFoundError as e:
        logging.error(f"Error: {e}")
