# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""S3 utility functions for the HealthOmics MCP server."""

from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from typing import Optional, Tuple
from urllib.parse import urlparse


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    """Parse an S3 URI into bucket and key.

    Args:
        uri: S3 URI (s3://bucket/key)

    Returns:
        Tuple[str, str]: Bucket name and object key
    """
    parsed = urlparse(uri)
    if parsed.scheme != 's3':
        raise ValueError(f'Invalid S3 URI: {uri}')

    bucket = parsed.netloc
    key = parsed.path.lstrip('/')

    return bucket, key


def upload_to_s3(data: bytes, uri: str, region: Optional[str] = None) -> str:
    """Upload data to S3.

    Args:
        data: Data to upload
        uri: S3 URI (s3://bucket/key)
        region: AWS region name (optional)

    Returns:
        str: S3 URI of the uploaded object
    """
    bucket, key = parse_s3_uri(uri)

    session = get_aws_session(region)
    s3_client = session.client('s3')

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
    )

    return uri


def download_from_s3(uri: str, region: Optional[str] = None) -> bytes:
    """Download data from S3.

    Args:
        uri: S3 URI (s3://bucket/key)
        region: AWS region name (optional)

    Returns:
        bytes: Downloaded data
    """
    bucket, key = parse_s3_uri(uri)

    session = get_aws_session(region)
    s3_client = session.client('s3')

    response = s3_client.get_object(
        Bucket=bucket,
        Key=key,
    )

    return response['Body'].read()


def ensure_s3_uri_ends_with_slash(uri: str) -> str:
    """Ensure an S3 URI ends with a slash.

    Args:
        uri: S3 URI

    Returns:
        str: S3 URI with trailing slash
    """
    if not uri.endswith('/'):
        uri += '/'

    return uri
