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
    get_run_manifest_logs,
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
    """Provides comprehensive diagnostic information for a failed workflow run.

    This function collects multiple sources of diagnostic information including:
    - Run details and failure reason
    - Engine logs from CloudWatch
    - Run manifest logs containing workflow summary and resource metrics
    - Task logs from all failed tasks
    - Actionable recommendations for troubleshooting

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the failed run

    Returns:
        Dictionary containing comprehensive diagnostic information including:
        - runId: The run identifier
        - status: Current run status
        - failureReason: AWS-provided failure reason
        - runUuid: Run UUID for log stream identification
        - engineLogs: Engine execution logs
        - manifestLogs: Run manifest logs with workflow summary
        - failedTasks: List of failed tasks with their logs
        - recommendations: Troubleshooting recommendations
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

        # Extract run details
        failure_reason = run_response.get('failureReason', 'No failure reason provided')
        run_uuid = run_response.get('uuid')

        logger.info(f'Diagnosing failed run {run_id} with UUID {run_uuid}')

        # Get engine logs using the workflow_analysis function
        engine_logs = []
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
            logger.info(f'Retrieved {len(engine_logs)} engine log entries')
        except Exception as e:
            error_message = f'Error retrieving engine logs: {str(e)}'
            logger.error(error_message)
            engine_logs = [error_message]

        # Get run manifest logs if UUID is available
        manifest_logs = []
        if run_uuid:
            try:
                manifest_logs_response = await get_run_manifest_logs(
                    ctx=ctx,
                    run_id=run_id,
                    run_uuid=run_uuid,
                    limit=100,
                    start_from_head=False,  # Get the most recent logs
                )

                # Extract just the messages for backward compatibility
                manifest_logs = [
                    event.get('message', '') for event in manifest_logs_response.get('events', [])
                ]
                logger.info(f'Retrieved {len(manifest_logs)} manifest log entries')
            except Exception as e:
                error_message = f'Error retrieving manifest logs: {str(e)}'
                logger.error(error_message)
                manifest_logs = [error_message]
        else:
            logger.warning(f'No UUID available for run {run_id}, skipping manifest logs')
            manifest_logs = ['No run UUID available - manifest logs cannot be retrieved']

        # Get all failed tasks (not just the first 10)
        failed_tasks = []
        next_token = None

        while True:
            list_tasks_params = {
                'id': run_id,
                'status': 'FAILED',
                'maxResults': 100,  # Get more tasks per request
            }
            if next_token:
                list_tasks_params['startingToken'] = next_token

            tasks_response = omics_client.list_run_tasks(**list_tasks_params)

            for task in tasks_response.get('items', []):
                task_id = task.get('taskId')
                task_name = task.get('name')
                task_status_message = task.get('statusMessage', 'No status message')

                logger.info(f'Processing failed task {task_id} ({task_name})')

                # Get task logs using the workflow_analysis function
                task_logs = []
                try:
                    task_logs_response = await get_task_logs(
                        ctx=ctx,
                        run_id=run_id,
                        task_id=task_id,
                        limit=100,  # Get more logs per task
                        start_from_head=False,  # Get the most recent logs
                    )

                    # Extract just the messages for backward compatibility
                    task_logs = [
                        event.get('message', '') for event in task_logs_response.get('events', [])
                    ]
                    logger.info(f'Retrieved {len(task_logs)} log entries for task {task_id}')
                except Exception as e:
                    error_message = f'Error retrieving task logs for {task_id}: {str(e)}'
                    logger.error(error_message)
                    task_logs = [error_message]

                failed_tasks.append(
                    {
                        'taskId': task_id,
                        'name': task_name,
                        'statusMessage': task_status_message,
                        'logs': task_logs,
                        'logCount': len(task_logs),
                    }
                )

            # Check if there are more tasks to retrieve
            next_token = tasks_response.get('nextToken')
            if not next_token:
                break

        logger.info(f'Found {len(failed_tasks)} failed tasks for run {run_id}')

        # Enhanced recommendations based on common failure patterns
        recommendations = [
            'Check IAM role permissions for S3 access and CloudWatch Logs',
            'Verify container images are accessible from the HealthOmics service',
            "Ensure input files exist and are accessible by the run's IAM role",
            'Check for syntax errors in workflow definition',
            'Verify parameter values match the expected types and formats',
            'Review manifest logs for resource allocation and utilization issues',
            'Check task logs for application-specific error messages',
            "Verify that output S3 locations are writable by the run's IAM role",
            'Consider increasing resource allocations if tasks failed due to memory/CPU limits',
            'Check for network connectivity issues if tasks failed during data transfer',
        ]

        # Compile comprehensive diagnostic information
        diagnosis = {
            'runId': run_id,
            'runUuid': run_uuid,
            'status': run_response.get('status'),
            'failureReason': failure_reason,
            'creationTime': run_response.get('creationTime').isoformat()
            if hasattr(run_response.get('creationTime'), 'isoformat')
            else run_response.get('creationTime'),
            'startTime': run_response.get('startTime').isoformat()
            if hasattr(run_response.get('startTime'), 'isoformat')
            else run_response.get('startTime'),
            'stopTime': run_response.get('stopTime').isoformat()
            if hasattr(run_response.get('stopTime'), 'isoformat')
            else run_response.get('stopTime'),
            'workflowId': run_response.get('workflowId'),
            'workflowType': run_response.get('workflowType'),
            'engineLogs': engine_logs,
            'engineLogCount': len(engine_logs),
            'manifestLogs': manifest_logs,
            'manifestLogCount': len(manifest_logs),
            'failedTasks': failed_tasks,
            'failedTaskCount': len(failed_tasks),
            'recommendations': recommendations,
            'summary': {
                'totalFailedTasks': len(failed_tasks),
                'hasManifestLogs': bool(
                    run_uuid
                    and len(manifest_logs) > 0
                    and 'Error retrieving manifest logs' not in str(manifest_logs)
                ),
                'hasEngineLogs': len(engine_logs) > 0
                and 'Error retrieving engine logs' not in str(engine_logs),
                'diagnosisTimestamp': ctx.session.request_id
                if hasattr(ctx, 'session')
                else 'unknown',
            },
        }

        logger.info(
            f'Diagnosis complete for run {run_id}: {len(failed_tasks)} failed tasks, {len(engine_logs)} engine logs, {len(manifest_logs)} manifest logs'
        )
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
