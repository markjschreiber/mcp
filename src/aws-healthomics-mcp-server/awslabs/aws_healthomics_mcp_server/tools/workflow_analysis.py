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

"""Workflow analysis tools for the AWS HealthOmics MCP server."""

import botocore
import botocore.exceptions
import csv
import os
import subprocess
import tempfile
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Any, Dict, List, Optional


def get_logs_client():
    """Get an AWS CloudWatch Logs client.

    Returns:
        boto3.client: Configured CloudWatch Logs client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    try:
        return session.client('logs')
    except Exception as e:
        logger.error(f'Failed to create CloudWatch Logs client: {str(e)}')
        raise


async def analyze_run(
    ctx: Context,
    run_ids: List[str] = Field(
        ...,
        description='List of run IDs to analyze',
    ),
    headroom: float = Field(
        0.1,
        description='Resource headroom factor (0.0-1.0)',
        ge=0.0,
        le=1.0,
    ),
) -> Dict[str, Any]:
    """Analyze run performance using the run analyzer.

    Args:
        ctx: MCP context for error reporting
        run_ids: List of run IDs to analyze
        headroom: Resource headroom factor (0.0-1.0, default: 0.1)

    Returns:
        Dictionary containing analysis results
    """
    # Validate headroom
    if not 0.0 <= headroom <= 1.0:
        error_message = 'Headroom must be between 0.0 and 1.0'
        logger.error(error_message)
        await ctx.error(error_message)
        raise ValueError(error_message)

    # Check if run analyzer is available
    try:
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv') as temp_file:
            # Build command
            cmd = ['python', '-m', 'omics.cli.run_analyzer', '-b']
            cmd.extend(run_ids)
            cmd.extend(['--headroom', str(headroom), '--output', temp_file.name])

            # Run the command
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if process.returncode != 0:
                error_message = f'Run analyzer failed: {process.stderr}'
                logger.error(error_message)
                await ctx.error(error_message)
                raise RuntimeError(error_message)

            # Read the CSV output
            temp_file.seek(0)
            reader = csv.DictReader(temp_file)
            results = []

            for row in reader:
                results.append(
                    {
                        'taskName': row.get('name', ''),
                        'count': int(row.get('count', 0)),
                        'meanRunningSeconds': float(row.get('meanRunningSeconds', 0)),
                        'maximumRunningSeconds': float(row.get('maximumRunningSeconds', 0)),
                        'stdDevRunningSeconds': float(row.get('stdDevRunningSeconds', 0)),
                        'maximumCpuUtilizationRatio': float(
                            row.get('maximumCpuUtilizationRatio', 0)
                        ),
                        'meanCpuUtilizationRatio': float(row.get('meanCpuUtilizationRatio', 0)),
                        'maximumMemoryUtilizationRatio': float(
                            row.get('maximumMemoryUtilizationRatio', 0)
                        ),
                        'meanMemoryUtilizationRatio': float(
                            row.get('meanMemoryUtilizationRatio', 0)
                        ),
                        'recommendedCpus': int(row.get('recommendedCpus', 0)),
                        'recommendedMemoryGiB': float(row.get('recommendedMemoryGiB', 0)),
                        'recommendedInstanceType': row.get('recommendOmicsInstanceType', ''),
                        'maximumEstimatedUSD': float(row.get('maximumEstimatedUSD', 0)),
                        'meanEstimatedUSD': float(row.get('meanEstimatedUSD', 0)),
                    }
                )

            return {'results': results}
    except subprocess.SubprocessError as e:
        error_message = f'Error executing run analyzer command: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = f'Unexpected error analyzing run: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise


async def _get_logs_from_stream(
    client,
    log_group_name: str,
    log_stream_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    start_from_head: bool = True,
) -> Dict[str, Any]:
    """Helper function to retrieve logs from a specific CloudWatch log stream.

    Args:
        client: CloudWatch Logs client
        log_group_name: Name of the log group
        log_stream_name: Name of the log stream
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return
        next_token: Token for pagination
        start_from_head: Whether to start from the beginning (True) or end (False) of the log stream

    Returns:
        Dictionary containing log events and next token if available
    """
    from datetime import datetime, timezone

    params = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'limit': limit,
        'startFromHead': start_from_head,
    }

    if next_token:
        params['nextToken'] = next_token

    if start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        params['startTime'] = int(start_dt.timestamp() * 1000)

    if end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        params['endTime'] = int(end_dt.timestamp() * 1000)

    response = client.get_log_events(**params)

    # Transform the response to a more user-friendly format
    events = []
    for event in response.get('events', []):
        # Convert timestamp from milliseconds to UTC ISO format
        timestamp_ms = event.get('timestamp', 0)
        timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        events.append(
            {
                'timestamp': timestamp_dt.isoformat().replace('+00:00', 'Z'),
                'message': event.get('message', ''),
            }
        )

    result = {'events': events}
    if 'nextForwardToken' in response:
        result['nextToken'] = response['nextForwardToken']

    return result


async def get_run_logs(
    ctx: Context,
    run_id: str = Field(
        ...,
        description='ID of the run',
    ),
    start_time: Optional[str] = Field(
        None,
        description='Optional start time for log retrieval (ISO format)',
    ),
    end_time: Optional[str] = Field(
        None,
        description='Optional end time for log retrieval (ISO format)',
    ),
    limit: int = Field(
        100,
        description='Maximum number of log events to return',
        ge=1,
        le=10000,
    ),
    next_token: Optional[str] = Field(
        None,
        description='Token for pagination from a previous response',
    ),
    start_from_head: bool = Field(
        True,
        description='Whether to start from the beginning (True) or end (False) of the log stream',
    ),
) -> Dict[str, Any]:
    """Retrieve high-level run logs that show workflow execution events.

    These logs contain a high-level summary of events during a run including:
    - Run creation and start events
    - File import start and completion
    - Workflow task start and completion
    - Export start and completion
    - Workflow completion

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the run
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination from a previous response
        start_from_head: Whether to start from the beginning (True) or end (False) of the log stream

    Returns:
        Dictionary containing log events and next token if available
    """
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'run/{run_id}'

    try:
        return await _get_logs_from_stream(
            client,
            log_group_name,
            log_stream_name,
            start_time,
            end_time,
            limit,
            next_token,
            start_from_head,
        )
    except ValueError as e:
        error_message = f'Invalid timestamp format: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except botocore.exceptions.BotoCoreError as e:
        error_message = f'AWS error retrieving run logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = f'Unexpected error retrieving run logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise


async def get_run_manifest_logs(
    ctx: Context,
    run_id: str = Field(
        ...,
        description='ID of the run',
    ),
    run_uuid: Optional[str] = Field(
        ...,
        description='Optional UUID of the run',
    ),
    start_time: Optional[str] = Field(
        None,
        description='Optional start time for log retrieval (ISO format)',
    ),
    end_time: Optional[str] = Field(
        None,
        description='Optional end time for log retrieval (ISO format)',
    ),
    limit: int = Field(
        100,
        description='Maximum number of log events to return',
        ge=1,
        le=10000,
    ),
    next_token: Optional[str] = Field(
        None,
        description='Token for pagination from a previous response',
    ),
    start_from_head: bool = Field(
        True,
        description='Whether to start from the beginning (True) or end (False) of the log stream',
    ),
) -> Dict[str, Any]:
    """Retrieve run manifest logs produced when a workflow completes or fails.

    These logs contain a summary of the overall workflow including:
    - Runtime information
    - Inputs and input digests
    - Messages and status information
    - Task summaries with resource allocation and utilization metrics

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the run
        run_uuid: Optional UUID of the run
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination from a previous response
        start_from_head: Whether to start from the beginning (True) or end (False) of the log stream

    Returns:
        Dictionary containing log events and next token if available
    """
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'manifest/run/{run_id}/{run_uuid}' if run_uuid else f'manifest/run/{run_id}'
    try:
        return await _get_logs_from_stream(
            client,
            log_group_name,
            log_stream_name,
            start_time,
            end_time,
            limit,
            next_token,
            start_from_head,
        )
    except ValueError as e:
        error_message = f'Invalid timestamp format: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except botocore.exceptions.BotoCoreError as e:
        error_message = f'AWS error retrieving manifest logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = f'Unexpected error retrieving manifest logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise


async def get_run_engine_logs(
    ctx: Context,
    run_id: str = Field(
        ...,
        description='ID of the run',
    ),
    start_time: Optional[str] = Field(
        None,
        description='Optional start time for log retrieval (ISO format)',
    ),
    end_time: Optional[str] = Field(
        None,
        description='Optional end time for log retrieval (ISO format)',
    ),
    limit: int = Field(
        100,
        description='Maximum number of log events to return',
        ge=1,
        le=10000,
    ),
    next_token: Optional[str] = Field(
        None,
        description='Token for pagination from a previous response',
    ),
    start_from_head: bool = Field(
        True,
        description='Whether to start from the beginning (True) or end (False) of the log stream',
    ),
) -> Dict[str, Any]:
    """Retrieve engine logs containing STDOUT and STDERR from the workflow engine process.

    These logs contain all output from the workflow engine process including:
    - Engine startup and initialization messages
    - Workflow parsing and validation output
    - Task scheduling and execution messages
    - Error messages and debugging information

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the run
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination from a previous response
        start_from_head: Whether to start from the beginning (True) or end (False) of the log stream

    Returns:
        Dictionary containing log events and next token if available
    """
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'run/{run_id}/engine'

    try:
        return await _get_logs_from_stream(
            client,
            log_group_name,
            log_stream_name,
            start_time,
            end_time,
            limit,
            next_token,
            start_from_head,
        )
    except ValueError as e:
        error_message = f'Invalid timestamp format: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except botocore.exceptions.BotoCoreError as e:
        error_message = f'AWS error retrieving engine logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = f'Unexpected error retrieving engine logs for run {run_id}: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise


async def get_task_logs(
    ctx: Context,
    run_id: str = Field(
        ...,
        description='ID of the run',
    ),
    task_id: str = Field(
        ...,
        description='ID of the specific task',
    ),
    start_time: Optional[str] = Field(
        None,
        description='Optional start time for log retrieval (ISO format)',
    ),
    end_time: Optional[str] = Field(
        None,
        description='Optional end time for log retrieval (ISO format)',
    ),
    limit: int = Field(
        100,
        description='Maximum number of log events to return',
        ge=1,
        le=10000,
    ),
    next_token: Optional[str] = Field(
        None,
        description='Token for pagination from a previous response',
    ),
    start_from_head: bool = Field(
        True,
        description='Whether to start from the beginning (True) or end (False) of the log stream',
    ),
) -> Dict[str, Any]:
    """Retrieve logs for a specific workflow task containing STDOUT and STDERR.

    These logs contain the output from a specific task process including:
    - Task container startup messages
    - Application-specific output and error messages
    - Task completion or failure information

    Args:
        ctx: MCP context for error reporting
        run_id: ID of the run
        task_id: ID of the specific task
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination from a previous response
        start_from_head: Whether to start from the beginning (True) or end (False) of the log stream

    Returns:
        Dictionary containing log events and next token if available
    """
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'run/{run_id}/task/{task_id}'

    try:
        return await _get_logs_from_stream(
            client,
            log_group_name,
            log_stream_name,
            start_time,
            end_time,
            limit,
            next_token,
            start_from_head,
        )
    except ValueError as e:
        error_message = f'Invalid timestamp format: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except botocore.exceptions.BotoCoreError as e:
        error_message = (
            f'AWS error retrieving task logs for run {run_id}, task {task_id}: {str(e)}'
        )
        logger.error(error_message)
        await ctx.error(error_message)
        raise
    except Exception as e:
        error_message = (
            f'Unexpected error retrieving task logs for run {run_id}, task {task_id}: {str(e)}'
        )
        logger.error(error_message)
        await ctx.error(error_message)
        raise
