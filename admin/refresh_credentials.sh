# Load environment variables from .env file
set -o allexport
source .env
set +o allexport

aws configure set sso_start_url $AWS_SSO_START_URL
aws configure set sso_region $AWS_SSO_REGION
aws sso login --profile $AWS_PROFILE