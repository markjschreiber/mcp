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
import json
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import (
    create_zip_file,
    encode_to_base64,
    get_ssm_client,
)
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Any, Dict, List, Optional


async def package_workflow(
    ctx: Context,
    main_file_content: str = Field(
        ...,
        description='Content of the main workflow file',
    ),
    main_file_name: str = Field(
        'main.wdl',
        description='Name of the main workflow file',
    ),
    additional_files: Optional[Dict[str, str]] = Field(
        None,
        description='Dictionary of additional files (filename: content)',
    ),
) -> str:
    """Package workflow definition files into a base64-encoded ZIP.

    Args:
        ctx: MCP context for error reporting
        main_file_content: Content of the main workflow file
        main_file_name: Name of the main workflow file (default: main.wdl)
        additional_files: Dictionary of additional files (filename: content)

    Returns:
        Base64-encoded ZIP file containing the workflow definition
    """
    try:
        # Create a dictionary of files
        files = {main_file_name: main_file_content}

        if additional_files:
            files.update(additional_files)

        # Create ZIP file
        zip_data = create_zip_file(files)

        # Encode to base64
        base64_data = encode_to_base64(zip_data)

        return base64_data
    except Exception as e:
        error_message = f'Error packaging workflow: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise


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
        # Get centralized SSM client
        ssm_client = get_ssm_client()

        # Get the parameters from the SSM parameter store
        response = ssm_client.get_parameters_by_path(
            Path='/aws/service/global-infrastructure/services/omics/regions'
        )

        # Extract the region values
        regions = [param['Value'] for param in response['Parameters']]

        # If no regions found, use the hardcoded list as fallback
        if not regions:
            from awslabs.aws_healthomics_mcp_server.consts import HEALTHOMICS_SUPPORTED_REGIONS

            regions = HEALTHOMICS_SUPPORTED_REGIONS
            logger.warning('No regions found in SSM parameter store. Using hardcoded region list.')

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


async def generate_ecr_repository_policy_for_omics(
    ctx: Context,
    additional_principals: Optional[List[str]] = Field(
        None,
        description='Additional AWS principals to grant access (e.g., account IDs, IAM roles)',
    ),
    include_cross_account_access: bool = Field(
        False,
        description='Whether to include cross-account access for all AWS accounts',
    ),
) -> Dict[str, Any]:
    """Generate an ECR repository policy that allows AWS HealthOmics access.

    This function generates a JSON policy document that can be applied to an ECR repository
    to allow AWS HealthOmics (omics.amazonaws.com) to pull container images. The policy
    includes the minimum required permissions for HealthOmics workflows.

    Args:
        ctx: MCP context for error reporting
        additional_principals: Additional AWS principals to grant access (account IDs, roles, etc.)
        include_cross_account_access: Whether to include cross-account access for all AWS accounts

    Returns:
        Dictionary containing the ECR policy document and usage instructions
    """
    try:
        # Required actions for HealthOmics
        required_actions = [
            'ecr:GetDownloadUrlForLayer',
            'ecr:BatchGetImage',
            'ecr:BatchCheckLayerAvailability',
        ]

        # Base principals - always include HealthOmics service
        principals = ['omics.amazonaws.com']

        # Add additional principals if provided
        if additional_principals:
            principals.extend(additional_principals)

        # Create the policy document
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Sid': 'AllowHealthOmicsAccess',
                    'Effect': 'Allow',
                    'Principal': {'Service': 'omics.amazonaws.com'},
                    'Action': required_actions,
                }
            ],
        }

        # Add additional principals statement if provided
        if additional_principals:
            additional_statement = {
                'Sid': 'AllowAdditionalPrincipals',
                'Effect': 'Allow',
                'Principal': {},
                'Action': required_actions,
            }

            # Categorize principals
            aws_principals = []
            service_principals = []

            for principal in additional_principals:
                if principal.startswith('arn:aws:iam::') or principal.isdigit():
                    # IAM role/user ARN or account ID
                    if principal.isdigit():
                        aws_principals.append(f'arn:aws:iam::{principal}:root')
                    else:
                        aws_principals.append(principal)
                elif '.' in principal:
                    # Likely a service principal
                    service_principals.append(principal)
                else:
                    # Assume it's an account ID if it's numeric
                    if principal.replace('-', '').isdigit():
                        aws_principals.append(f'arn:aws:iam::{principal}:root')
                    else:
                        service_principals.append(principal)

            if aws_principals:
                additional_statement['Principal']['AWS'] = aws_principals
            if service_principals:
                additional_statement['Principal']['Service'] = service_principals

            if additional_statement['Principal']:
                policy_document['Statement'].append(additional_statement)

        # Add cross-account access if requested
        if include_cross_account_access:
            cross_account_statement = {
                'Sid': 'AllowCrossAccountAccess',
                'Effect': 'Allow',
                'Principal': '*',
                'Action': required_actions,
                'Condition': {'StringEquals': {'aws:PrincipalServiceName': 'omics.amazonaws.com'}},
            }
            policy_document['Statement'].append(cross_account_statement)

        # Format the policy as a JSON string
        policy_json = json.dumps(policy_document, indent=2)

        # Generate usage instructions
        usage_instructions = [
            'To apply this policy to your ECR repository, use one of the following methods:',
            '',
            '1. AWS CLI:',
            "   aws ecr set-repository-policy --repository-name YOUR_REPO_NAME --policy-text '{}'".format(
                policy_json.replace("'", "\\'")
            ),
            '',
            '2. AWS Console:',
            '   - Navigate to Amazon ECR in the AWS Console',
            '   - Select your repository',
            '   - Go to the "Permissions" tab',
            '   - Click "Edit policy JSON"',
            '   - Paste the policy document',
            '',
            '3. CloudFormation/CDK:',
            '   Use the policy document in your infrastructure as code templates',
            '',
            'Required permissions for HealthOmics:',
        ]
        usage_instructions.extend([f'  - {action}' for action in required_actions])

        return {
            'policy_document': policy_document,
            'policy_json': policy_json,
            'usage_instructions': usage_instructions,
            'required_actions': required_actions,
            'principals_included': principals,
        }

    except Exception as e:
        error_message = f'Error generating ECR policy: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
