import logging
from image_handler import image_handler
from chart_handler import chart_handler
from ecr import login_ecr_cn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def main():
    # Login to ECR
    login_ecr_cn()

    image_handler()
    # chart_handler()

if __name__ == "__main__":
    main()