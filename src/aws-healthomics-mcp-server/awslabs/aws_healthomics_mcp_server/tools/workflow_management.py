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

"""Workflow management tools for the AWS HealthOmics MCP server."""

import os
from awslabs.aws_healthomics_mcp_server.consts import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_REGION,
    ERROR_INVALID_EXPORT_TYPE,
    EXPORT_TYPES,
)
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import (
    decode_from_base64,
    get_aws_session,
)
from loguru import logger
from typing import Any, Dict, Optional


def get_omics_client():
    """Get an AWS HealthOmics client.

    Returns:
        boto3.client: Configured HealthOmics client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    return session.client('omics')


async def list_workflows(
    max_results: Optional[int] = DEFAULT_MAX_RESULTS,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List available HealthOmics workflows.

    Args:
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination

    Returns:
        Dictionary containing workflow information and next token if available
    """
    client = get_omics_client()

    params = {'maxResults': max_results}
    if next_token:
        params['startingToken'] = next_token

    try:
        response = client.list_workflows(**params)

        # Transform the response to a more user-friendly format
        workflows = []
        for workflow in response.get('items', []):
            workflows.append(
                {
                    'id': workflow.get('id'),
                    'arn': workflow.get('arn'),
                    'name': workflow.get('name'),
                    'status': workflow.get('status'),
                    'type': workflow.get('type'),
                    'creationTime': workflow.get('creationTime').isoformat()
                    if workflow.get('creationTime')
                    else None,
                }
            )

        result = {'workflows': workflows}
        if 'nextToken' in response:
            result['nextToken'] = response['nextToken']

        return result
    except Exception as e:
        logger.error(f'Error listing workflows: {str(e)}')
        return {'error': str(e)}


async def create_workflow(
    name: str,
    definition_zip_base64: str,
    description: Optional[str] = None,
    parameter_template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new HealthOmics workflow.

    Args:
        name: Name of the workflow
        definition_zip_base64: Base64-encoded workflow definition ZIP file
        description: Optional description of the workflow
        parameter_template: Optional parameter template for the workflow

    Returns:
        Dictionary containing the created workflow information
    """
    client = get_omics_client()

    params = {
        'name': name,
        'definitionZip': decode_from_base64(definition_zip_base64),
    }

    if description:
        params['description'] = description

    if parameter_template:
        params['parameterTemplate'] = parameter_template

    try:
        response = client.create_workflow(**params)

        return {
            'id': response.get('id'),
            'arn': response.get('arn'),
            'status': response.get('status'),
            'name': name,
            'description': description,
        }
    except Exception as e:
        logger.error(f'Error creating workflow: {str(e)}')
        return {'error': str(e)}


async def get_workflow(
    workflow_id: str,
    export_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Get details about a specific workflow.

    Args:
        workflow_id: ID of the workflow to retrieve
        export_type: Optional export type (DEFINITION, PARAMETER_TEMPLATE)

    Returns:
        Dictionary containing workflow details
    """
    client = get_omics_client()

    params = {'id': workflow_id}

    if export_type:
        if export_type not in EXPORT_TYPES:
            return {'error': ERROR_INVALID_EXPORT_TYPE.format(EXPORT_TYPES)}
        params['export'] = export_type

    try:
        response = client.get_workflow(**params)

        result = {
            'id': response.get('id'),
            'arn': response.get('arn'),
            'name': response.get('name'),
            'status': response.get('status'),
            'type': response.get('type'),
            'creationTime': response.get('creationTime').isoformat()
            if response.get('creationTime')
            else None,
        }

        if 'description' in response:
            result['description'] = response['description']

        if 'parameterTemplate' in response:
            result['parameterTemplate'] = response['parameterTemplate']

        if 'definition' in response:
            result['definition'] = response['definition']

        return result
    except Exception as e:
        logger.error(f'Error getting workflow: {str(e)}')
        return {'error': str(e)}


async def create_workflow_version(
    workflow_id: str,
    version_name: str,
    definition_zip_base64: str,
    description: Optional[str] = None,
    parameter_template: Optional[Dict[str, Any]] = None,
    storage_type: Optional[str] = 'DYNAMIC',
    storage_capacity: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a new version of an existing workflow.

    Args:
        workflow_id: ID of the workflow
        version_name: Name for the new version
        definition_zip_base64: Base64-encoded workflow definition ZIP file
        description: Optional description of the workflow version
        parameter_template: Optional parameter template for the workflow
        storage_type: Storage type (STATIC or DYNAMIC)
        storage_capacity: Storage capacity in GB (required for STATIC)

    Returns:
        Dictionary containing the created workflow version information
    """
    client = get_omics_client()

    params = {
        'workflowId': workflow_id,
        'versionName': version_name,
        'definitionZip': decode_from_base64(definition_zip_base64),
        'storageType': storage_type,
    }

    if description:
        params['description'] = description

    if parameter_template:
        params['parameterTemplate'] = parameter_template

    if storage_type == 'STATIC' and storage_capacity:
        params['storageCapacity'] = storage_capacity

    try:
        response = client.create_workflow_version(**params)

        return {
            'id': response.get('id'),
            'arn': response.get('arn'),
            'status': response.get('status'),
            'name': response.get('name'),
            'versionName': version_name,
            'description': description,
        }
    except Exception as e:
        logger.error(f'Error creating workflow version: {str(e)}')
        return {'error': str(e)}


async def list_workflow_versions(
    workflow_id: str,
    max_results: Optional[int] = DEFAULT_MAX_RESULTS,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List versions of a workflow.

    Args:
        workflow_id: ID of the workflow
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination

    Returns:
        Dictionary containing workflow version information and next token if available
    """
    client = get_omics_client()

    params = {
        'workflowId': workflow_id,
        'maxResults': max_results,
    }

    if next_token:
        params['startingToken'] = next_token

    try:
        response = client.list_workflow_versions(**params)

        # Transform the response to a more user-friendly format
        versions = []
        for version in response.get('items', []):
            versions.append(
                {
                    'id': version.get('id'),
                    'arn': version.get('arn'),
                    'name': version.get('name'),
                    'versionName': version.get('versionName'),
                    'status': version.get('status'),
                    'type': version.get('type'),
                    'creationTime': version.get('creationTime').isoformat()
                    if version.get('creationTime')
                    else None,
                }
            )

        result = {'versions': versions}
        if 'nextToken' in response:
            result['nextToken'] = response['nextToken']

        return result
    except Exception as e:
        logger.error(f'Error listing workflow versions: {str(e)}')
        return {'error': str(e)}
