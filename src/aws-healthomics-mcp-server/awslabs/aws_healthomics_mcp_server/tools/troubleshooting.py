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

"""Troubleshooting tools for the AWS HealthOmics MCP server."""

import botocore
import botocore.exceptions
import os
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.tools.workflow_analysis import (
    get_run_engine_logs,
    get_task_logs,
)
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Any, Dict


def get_omics_client():
    """Get an AWS HealthOmics client.

    Returns:
        boto3.client: Configured HealthOmics client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    try:
        return session.client('omics')
    except Exception as e:
        logger.error(f'Failed to create HealthOmics client: {str(e)}')
        raise


async def diagnose_run_failure(
    ctx: Context,
    run_id: str = Field(
        ...,
        description='ID of the failed run',
    ),
) -> Dict[str, Any]:
    """Diagnose a failed workflow run.

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the failed run

    Returns:
        Dictionary containing diagnostic information
    """
    try:
        omics_client = get_omics_client()

        # Get run details
        run_response = omics_client.get_run(id=run_id)

        # Check if the run actually failed
        if run_response.get('status') != 'FAILED':
            return {
                'status': run_response.get('status'),
                'message': f'Run is not in FAILED state. Current status: {run_response.get("status")}',
            }

        # Get failure reason
        failure_reason = run_response.get('failureReason', 'No failure reason provided')

        # Get engine logs using the workflow_analysis function
        try:
            engine_logs_response = await get_run_engine_logs(
                ctx=ctx,
                run_id=run_id,
                limit=100,
                start_from_head=False,  # Get the most recent logs
            )

            # Extract just the messages for backward compatibility
            engine_logs = [
                event.get('message', '') for event in engine_logs_response.get('events', [])
            ]
        except Exception as e:
            error_message = f'Error retrieving engine logs: {str(e)}'
            logger.error(error_message)
            engine_logs = [error_message]

        # Get failed tasks
        tasks_response = omics_client.list_run_tasks(
            id=run_id,
            status='FAILED',
            maxResults=10,
        )

        failed_tasks = []
        for task in tasks_response.get('items', []):
            task_id = task.get('taskId')
            task_name = task.get('name')

            # Get task logs using the workflow_analysis function
            try:
                task_logs_response = await get_task_logs(
                    ctx=ctx,
                    run_id=run_id,
                    task_id=task_id,
                    limit=50,
                    start_from_head=False,  # Get the most recent logs
                )

                # Extract just the messages for backward compatibility
                task_logs = [
                    event.get('message', '') for event in task_logs_response.get('events', [])
                ]
            except Exception as e:
                error_message = f'Error retrieving task logs: {str(e)}'
                logger.error(error_message)
                task_logs = [error_message]

            failed_tasks.append(
                {
                    'taskId': task_id,
                    'name': task_name,
                    'statusMessage': task.get('statusMessage', 'No status message'),
                    'logs': task_logs,
                }
            )

        # Compile diagnostic information
        diagnosis = {
            'runId': run_id,
            'status': run_response.get('status'),
            'failureReason': failure_reason,
            'engineLogs': engine_logs,
            'failedTasks': failed_tasks,
            'recommendations': [
                'Check IAM role permissions for S3 access and CloudWatch Logs',
                'Verify container images are accessible from the HealthOmics service',
                'Ensure input files exist and are accessible',
                'Check for syntax errors in workflow definition',
                'Verify parameter values match the expected types',
            ],
        }

        return diagnosis
    except botocore.exceptions.ClientError as e:
        error_message = f'AWS error diagnosing run failure for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except botocore.exceptions.BotoCoreError as e:
        error_message = f'AWS error diagnosing run failure for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = f'Unexpected error diagnosing run failure for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
