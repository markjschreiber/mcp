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

import os
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from loguru import logger
from typing import Any, Dict


def get_omics_client():
    """Get an AWS HealthOmics client.

    Returns:
        boto3.client: Configured HealthOmics client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    return session.client('omics')


def get_logs_client():
    """Get an AWS CloudWatch Logs client.

    Returns:
        boto3.client: Configured CloudWatch Logs client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    return session.client('logs')


async def diagnose_run_failure(
    run_id: str,
) -> Dict[str, Any]:
    """Diagnose a failed workflow run.

    Args:
        run_id: ID of the failed run

    Returns:
        Dictionary containing diagnostic information
    """
    omics_client = get_omics_client()
    logs_client = get_logs_client()

    try:
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

        # Get engine logs
        log_group_name = '/aws/omics/WorkflowLog'
        engine_log_stream = f'run/{run_id}/engine'

        try:
            engine_logs_response = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=engine_log_stream,
                limit=100,
                startFromHead=False,  # Get the most recent logs
            )

            engine_logs = [
                event.get('message', '') for event in engine_logs_response.get('events', [])
            ]
        except Exception as e:
            logger.error(f'Error retrieving engine logs: {str(e)}')
            engine_logs = [f'Error retrieving engine logs: {str(e)}']

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

            # Get task logs
            try:
                task_log_stream = f'run/{run_id}/task/{task_id}'
                task_logs_response = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=task_log_stream,
                    limit=50,
                    startFromHead=False,  # Get the most recent logs
                )

                task_logs = [
                    event.get('message', '') for event in task_logs_response.get('events', [])
                ]
            except Exception as e:
                logger.error(f'Error retrieving task logs: {str(e)}')
                task_logs = [f'Error retrieving task logs: {str(e)}']

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
    except Exception as e:
        logger.error(f'Error diagnosing run failure: {str(e)}')
        return {'error': str(e)}
