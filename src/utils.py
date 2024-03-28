import re

from config import DOMAIN_MAP


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