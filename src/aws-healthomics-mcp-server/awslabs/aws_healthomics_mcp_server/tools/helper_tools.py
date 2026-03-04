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

"""Helper tools for the AWS HealthOmics MCP server."""

import botocore
import botocore.exceptions
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import (
    create_zip_file,
    encode_to_base64,
    get_aws_session,
    get_omics_service_name,
)
from awslabs.aws_healthomics_mcp_server.utils.content_resolver import resolve_single_content
from awslabs.aws_healthomics_mcp_server.utils.error_utils import handle_tool_error
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Any, Dict, Optional, Union


async def package_workflow(
    ctx: Context,
    main_file_content: str = Field(
        ...,
        description='Content of the main workflow file. Accepts inline content, a local file path, or an S3 URI (s3://bucket/key).',
    ),
    main_file_name: str = Field(
        'main.wdl',
        description='Name of the main workflow file',
    ),
    additional_files: Optional[Dict[str, str]] = Field(
        None,
        description='Dictionary of additional files (filename: content). Values accept inline content, local file paths, or S3 URIs.',
    ),
) -> Union[str, Dict[str, Any]]:
    """Package workflow definition files into a base64-encoded ZIP.

    Args:
        ctx: MCP context for error reporting
        main_file_content: Content of the main workflow file. Accepts inline content,
            a local file path, or an S3 URI (s3://bucket/key).
        main_file_name: Name of the main workflow file (default: main.wdl)
        additional_files: Dictionary of additional files (filename: content).
            Values accept inline content, local file paths, or S3 URIs.

    Returns:
        Base64-encoded ZIP file containing the workflow definition, or error dict
    """
    try:
        try:
            resolved_main = await resolve_single_content(main_file_content, mode='text')
        except (ValueError, FileNotFoundError, PermissionError) as e:
            return await handle_tool_error(ctx, e, 'Error resolving main file content')

        files: dict[str, str] = {main_file_name: str(resolved_main.content)}

        if additional_files:
            try:
                for fname, fvalue in additional_files.items():
                    resolved = await resolve_single_content(fvalue, mode='text')
                    files[fname] = str(resolved.content)
            except (ValueError, FileNotFoundError, PermissionError) as e:
                return await handle_tool_error(ctx, e, 'Error resolving additional file content')

        # Create ZIP file
        zip_data = create_zip_file(files)

        # Encode to base64
        base64_data = encode_to_base64(zip_data)

        return base64_data
    except Exception as e:
        return await handle_tool_error(ctx, e, 'Error packaging workflow')


async def get_supported_regions(
    ctx: Context,
) -> Dict[str, Any]:
    """Get the list of AWS regions where HealthOmics is available.

    Args:
        ctx: MCP context for error reporting

    Returns:
        Dictionary containing the list of supported region codes and the total count
        of regions where HealthOmics is available
    """
    try:
        # Get centralized AWS session
        session = get_aws_session()

        # Get the service name (defaults to 'omics')
        service_name = get_omics_service_name()

        # Get available regions for the HealthOmics service
        regions = session.get_available_regions(service_name)

        # If no regions found, use the hardcoded list as fallback
        if not regions:
            from awslabs.aws_healthomics_mcp_server.consts import HEALTHOMICS_SUPPORTED_REGIONS

            regions = HEALTHOMICS_SUPPORTED_REGIONS
            logger.warning('No regions found via boto3 session. Using hardcoded region list.')

        return {'regions': sorted(regions), 'count': len(regions)}
    except botocore.exceptions.BotoCoreError as e:
        error_message = f'AWS error retrieving supported regions: {str(e)}'
        logger.error(error_message)
        logger.info('Using hardcoded region list as fallback')

        # Use hardcoded list as fallback
        from awslabs.aws_healthomics_mcp_server.consts import HEALTHOMICS_SUPPORTED_REGIONS

        return {
            'regions': sorted(HEALTHOMICS_SUPPORTED_REGIONS),
            'count': len(HEALTHOMICS_SUPPORTED_REGIONS),
            'note': 'Using hardcoded region list due to error: ' + str(e),
        }
    except Exception as e:
        error_message = f'Unexpected error retrieving supported regions: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)

        # Use hardcoded list as fallback
        from awslabs.aws_healthomics_mcp_server.consts import HEALTHOMICS_SUPPORTED_REGIONS

        return {
            'regions': sorted(HEALTHOMICS_SUPPORTED_REGIONS),
            'count': len(HEALTHOMICS_SUPPORTED_REGIONS),
            'note': 'Using hardcoded region list due to error: ' + str(e),
        }
