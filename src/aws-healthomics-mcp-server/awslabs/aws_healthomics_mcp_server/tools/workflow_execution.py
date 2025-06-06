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

"""Workflow execution tools for the AWS HealthOmics MCP server."""

import os
from awslabs.aws_healthomics_mcp_server.consts import (
    CACHE_BEHAVIORS,
    DEFAULT_MAX_RESULTS,
    DEFAULT_REGION,
    ERROR_INVALID_CACHE_BEHAVIOR,
    ERROR_INVALID_RUN_STATUS,
    ERROR_INVALID_STORAGE_TYPE,
    ERROR_STATIC_STORAGE_REQUIRES_CAPACITY,
    RUN_STATUSES,
    STORAGE_TYPE_STATIC,
    STORAGE_TYPES,
)
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from awslabs.aws_healthomics_mcp_server.utils.s3_utils import ensure_s3_uri_ends_with_slash
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


async def start_run(
    workflow_id: str,
    role_arn: str,
    name: str,
    output_uri: str,
    parameters: Dict[str, Any],
    workflow_version_name: Optional[str] = None,
    storage_type: Optional[str] = 'DYNAMIC',
    storage_capacity: Optional[int] = None,
    cache_id: Optional[str] = None,
    cache_behavior: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a workflow run.

    Args:
        workflow_id: ID of the workflow to run
        role_arn: ARN of the IAM role to use for the run
        name: Name for the run
        output_uri: S3 URI for the run outputs
        parameters: Parameters for the workflow
        workflow_version_name: Optional version name to run
        storage_type: Storage type (STATIC or DYNAMIC)
        storage_capacity: Storage capacity in GB (required for STATIC)
        cache_id: Optional ID of a run cache to use
        cache_behavior: Optional cache behavior (CACHE_ALWAYS or CACHE_ON_FAILURE)

    Returns:
        Dictionary containing the run information
    """
    client = get_omics_client()

    # Validate storage type
    if storage_type not in STORAGE_TYPES:
        return {'error': ERROR_INVALID_STORAGE_TYPE.format(STORAGE_TYPES)}

    # Validate storage capacity for STATIC storage
    if storage_type == STORAGE_TYPE_STATIC and storage_capacity is None:
        return {'error': ERROR_STATIC_STORAGE_REQUIRES_CAPACITY}

    # Validate cache behavior
    if cache_behavior and cache_behavior not in CACHE_BEHAVIORS:
        return {'error': ERROR_INVALID_CACHE_BEHAVIOR.format(CACHE_BEHAVIORS)}

    # Ensure output URI ends with a slash
    output_uri = ensure_s3_uri_ends_with_slash(output_uri)

    params = {
        'workflowId': workflow_id,
        'roleArn': role_arn,
        'name': name,
        'outputUri': output_uri,
        'parameters': parameters,
        'storageType': storage_type,
    }

    if workflow_version_name:
        params['workflowVersionName'] = workflow_version_name

    if storage_type == STORAGE_TYPE_STATIC and storage_capacity:
        params['storageCapacity'] = storage_capacity

    if cache_id:
        params['cacheId'] = cache_id

        if cache_behavior:
            params['cacheBehavior'] = cache_behavior

    try:
        response = client.start_run(**params)

        return {
            'id': response.get('id'),
            'arn': response.get('arn'),
            'status': response.get('status'),
            'name': name,
            'workflowId': workflow_id,
            'workflowVersionName': workflow_version_name,
            'outputUri': output_uri,
        }
    except Exception as e:
        logger.error(f'Error starting run: {str(e)}')
        return {'error': str(e)}


async def list_runs(
    max_results: Optional[int] = DEFAULT_MAX_RESULTS,
    next_token: Optional[str] = None,
    status: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """List workflow runs.

    Args:
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination
        status: Filter by run status
        created_after: Filter for runs created after this timestamp (ISO format)
        created_before: Filter for runs created before this timestamp (ISO format)

    Returns:
        Dictionary containing run information and next token if available
    """
    client = get_omics_client()

    # Validate status
    if status and status not in RUN_STATUSES:
        return {'error': ERROR_INVALID_RUN_STATUS.format(RUN_STATUSES)}

    params: dict[str, Any] = {'maxResults': max_results}

    if next_token:
        params['startingToken'] = next_token

    if status:
        params['status'] = status

    if created_after:
        params['createdAfter'] = created_after

    if created_before:
        params['createdBefore'] = created_before

    try:
        response = client.list_runs(**params)

        # Transform the response to a more user-friendly format
        runs = []
        for run in response.get('items', []):
            run_info = {
                'id': run.get('id'),
                'arn': run.get('arn'),
                'name': run.get('name'),
                'status': run.get('status'),
                'workflowId': run.get('workflowId'),
                'workflowType': run.get('workflowType'),
                'creationTime': run.get('creationTime').isoformat()
                if run.get('creationTime')
                else None,
            }

            if 'startTime' in run:
                run_info['startTime'] = run['startTime'].isoformat()

            if 'stopTime' in run:
                run_info['stopTime'] = run['stopTime'].isoformat()

            runs.append(run_info)

        result = {'runs': runs}
        if 'nextToken' in response:
            result['nextToken'] = response['nextToken']

        return result
    except Exception as e:
        logger.error(f'Error listing runs: {str(e)}')
        return {'error': str(e)}


async def get_run(
    run_id: str,
) -> Dict[str, Any]:
    """Get details about a specific run.

    Args:
        run_id: ID of the run to retrieve

    Returns:
        Dictionary containing run details
    """
    client = get_omics_client()

    try:
        response = client.get_run(id=run_id)

        result = {
            'id': response.get('id'),
            'arn': response.get('arn'),
            'name': response.get('name'),
            'status': response.get('status'),
            'workflowId': response.get('workflowId'),
            'workflowType': response.get('workflowType'),
            'creationTime': response.get('creationTime').isoformat()
            if response.get('creationTime')
            else None,
            'outputUri': response.get('outputUri'),
        }

        if 'startTime' in response:
            result['startTime'] = response['startTime'].isoformat()

        if 'stopTime' in response:
            result['stopTime'] = response['stopTime'].isoformat()

        if 'statusMessage' in response:
            result['statusMessage'] = response['statusMessage']

        if 'failureReason' in response:
            result['failureReason'] = response['failureReason']

        if 'workflowVersionName' in response:
            result['workflowVersionName'] = response['workflowVersionName']

        return result
    except Exception as e:
        logger.error(f'Error getting run: {str(e)}')
        return {'error': str(e)}


async def list_run_tasks(
    run_id: str,
    max_results: Optional[int] = DEFAULT_MAX_RESULTS,
    next_token: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List tasks for a specific run.

    Args:
        run_id: ID of the run
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination
        status: Filter by task status

    Returns:
        Dictionary containing task information and next token if available
    """
    client = get_omics_client()

    params = {
        'id': run_id,
        'maxResults': max_results,
    }

    if next_token:
        params['startingToken'] = next_token

    if status:
        params['status'] = status

    try:
        response = client.list_run_tasks(**params)

        # Transform the response to a more user-friendly format
        tasks = []
        for task in response.get('items', []):
            task_info = {
                'taskId': task.get('taskId'),
                'status': task.get('status'),
                'name': task.get('name'),
                'cpus': task.get('cpus'),
                'memory': task.get('memory'),
            }

            if 'startTime' in task:
                task_info['startTime'] = task['startTime'].isoformat()

            if 'stopTime' in task:
                task_info['stopTime'] = task['stopTime'].isoformat()

            tasks.append(task_info)

        result = {'tasks': tasks}
        if 'nextToken' in response:
            result['nextToken'] = response['nextToken']

        return result
    except Exception as e:
        logger.error(f'Error listing run tasks: {str(e)}')
        return {'error': str(e)}


async def get_run_task(
    run_id: str,
    task_id: str,
) -> Dict[str, Any]:
    """Get details about a specific task.

    Args:
        run_id: ID of the run
        task_id: ID of the task

    Returns:
        Dictionary containing task details
    """
    client = get_omics_client()

    try:
        response = client.get_run_task(id=run_id, taskId=task_id)

        result = {
            'taskId': response.get('taskId'),
            'status': response.get('status'),
            'name': response.get('name'),
            'cpus': response.get('cpus'),
            'memory': response.get('memory'),
        }

        if 'startTime' in response:
            result['startTime'] = response['startTime'].isoformat()

        if 'stopTime' in response:
            result['stopTime'] = response['stopTime'].isoformat()

        if 'statusMessage' in response:
            result['statusMessage'] = response['statusMessage']

        if 'logStream' in response:
            result['logStream'] = response['logStream']

        return result
    except Exception as e:
        logger.error(f'Error getting run task: {str(e)}')
        return {'error': str(e)}
