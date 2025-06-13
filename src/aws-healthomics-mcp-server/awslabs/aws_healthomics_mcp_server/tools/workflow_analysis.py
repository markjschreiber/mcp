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
import json
import os
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from botocore.exceptions import ClientError
from datetime import datetime, timezone
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
        description='List of run IDs to analyze for performance optimization',
    ),
    include_analysis_prompt: bool = Field(
        True,
        description='Whether to include AI analysis instructions in the response',
    ),
) -> Dict[str, Any]:
    """Analyze run performance using manifest data and AI-powered insights.

    This function retrieves run manifest logs containing detailed task metrics
    and returns structured data with analysis instructions for the consuming AI agent.

    The manifest logs contain comprehensive information about:
    - Task resource allocation vs actual usage
    - CPU and memory utilization patterns
    - Runtime performance metrics
    - Cost optimization opportunities

    Args:
        ctx: MCP context for error reporting
        run_ids: List of run IDs to analyze
        include_analysis_prompt: Whether to include analysis instructions

    Returns:
        Dictionary containing structured manifest data and analysis instructions
    """
    try:
        logger.info(f'Analyzing runs {run_ids} using manifest data')

        # Get AWS session and clients
        region = os.environ.get('AWS_REGION', DEFAULT_REGION)
        session = get_aws_session(region)
        omics_client = session.client('omics')

        analysis_results = {
            'runs': [],
            'summary': {
                'totalRuns': len(run_ids),
                'analysisTimestamp': datetime.now(timezone.utc).isoformat(),
                'analysisType': 'manifest-based',
            },
        }

        # Process each run
        for run_id in run_ids:
            try:
                logger.debug(f'Processing run {run_id}')

                # Get basic run information
                run_response = omics_client.get_run(id=run_id)
                run_uuid = run_response.get('uuid')

                if not run_uuid:
                    logger.warning(f'No UUID found for run {run_id}, skipping manifest analysis')
                    continue

                # Get manifest logs
                manifest_logs = await get_run_manifest_logs_internal(
                    run_id=run_id,
                    run_uuid=run_uuid,
                    limit=1000,  # Get comprehensive manifest data
                )

                # Parse and structure the manifest data
                run_analysis = await _parse_manifest_for_analysis(
                    run_id, run_response, manifest_logs, ctx
                )

                if run_analysis:
                    analysis_results['runs'].append(run_analysis)

            except Exception as e:
                logger.error(f'Error processing run {run_id}: {str(e)}')
                # Continue with other runs rather than failing completely
                continue

        # Add analysis instructions if requested
        if include_analysis_prompt:
            analysis_results['analysis_instructions'] = _get_analysis_instructions()

        logger.info(
            f'Successfully prepared analysis data for {len(analysis_results["runs"])} runs'
        )
        return analysis_results

    except Exception as e:
        error_message = f'Error analyzing runs: {str(e)}'
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
    params = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'limit': limit,
        'startFromHead': start_from_head,
    }

    if next_token:
        params['nextToken'] = next_token

    if start_time:
        # Ensure start_time is a string before calling replace
        start_time_str = str(start_time) if not isinstance(start_time, str) else start_time
        start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        params['startTime'] = int(start_dt.timestamp() * 1000)

    if end_time:
        # Ensure end_time is a string before calling replace
        end_time_str = str(end_time) if not isinstance(end_time, str) else end_time
        end_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
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


async def _get_run_manifest_logs_internal(
    run_id: str,
    run_uuid: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    start_from_head: bool = True,
) -> Dict[str, Any]:
    """Internal function to get run manifest logs without Pydantic Field decorators."""
    try:
        client = get_logs_client()
        log_group_name = f'/aws/omics/WorkflowLog/{run_uuid}'

        params = {
            'logGroupName': log_group_name,
            'limit': limit,
            'startFromHead': start_from_head,
        }

        if next_token:
            params['nextToken'] = next_token

        if start_time:
            # Ensure start_time is a string before calling replace
            start_time_str = str(start_time) if not isinstance(start_time, str) else start_time
            start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            params['startTime'] = int(start_dt.timestamp() * 1000)

        if end_time:
            # Ensure end_time is a string before calling replace
            end_time_str = str(end_time) if not isinstance(end_time, str) else end_time
            end_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            params['endTime'] = int(end_dt.timestamp() * 1000)

        response = client.get_log_events(**params)

        # Transform the response to a more user-friendly format
        events = []
        for event in response.get('events', []):
            timestamp_ms = event.get('timestamp', 0)
            timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            events.append(
                {
                    'timestamp': timestamp_dt.isoformat().replace('+00:00', 'Z'),
                    'message': event.get('message', ''),
                }
            )

        return {
            'events': events,
            'nextForwardToken': response.get('nextForwardToken'),
            'nextBackwardToken': response.get('nextBackwardToken'),
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.warning(f'Log group not found for run UUID {run_uuid}')
            return {'events': [], 'error': 'Log group not found'}
        else:
            logger.error(f'AWS error retrieving manifest logs: {str(e)}')
            raise
    except Exception as e:
        logger.error(f'Error retrieving manifest logs: {str(e)}')
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


# Internal wrapper functions for use by other modules (without Pydantic Field decorators)


async def get_run_manifest_logs_internal(
    run_id: str,
    run_uuid: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    start_from_head: bool = True,
) -> Dict[str, Any]:
    """Internal wrapper for get_run_manifest_logs without Pydantic Field decorators."""
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
    except Exception as e:
        logger.error(f'Error retrieving manifest logs: {str(e)}')
        raise


async def get_run_engine_logs_internal(
    run_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    start_from_head: bool = True,
) -> Dict[str, Any]:
    """Internal wrapper for get_run_engine_logs without Pydantic Field decorators."""
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = (
        f'run/{run_id}/engine'  # Fixed: should be run/{run_id}/engine, not engine/run/{run_id}
    )

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
    except Exception as e:
        logger.error(f'Error retrieving engine logs: {str(e)}')
        raise


async def get_task_logs_internal(
    run_id: str,
    task_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    start_from_head: bool = True,
) -> Dict[str, Any]:
    """Internal wrapper for get_task_logs without Pydantic Field decorators."""
    client = get_logs_client()
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'run/{run_id}/task/{task_id}'  # Fixed: should be run/{run_id}/task/{task_id}, not task/run/{run_id}/{task_id}

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
    except Exception as e:
        logger.error(f'Error retrieving task logs: {str(e)}')
        raise


async def _parse_manifest_for_analysis(
    run_id: str, run_response: Dict[str, Any], manifest_logs: Dict[str, Any], ctx: Context
) -> Optional[Dict[str, Any]]:
    """Parse manifest logs to extract key metrics for analysis."""
    try:
        # Extract basic run information
        run_info = {
            'runId': run_id,
            'runName': run_response.get('name', ''),
            'status': run_response.get('status', ''),
            'workflowId': run_response.get('workflowId', ''),
            'creationTime': run_response.get('creationTime', ''),
            'startTime': run_response.get('startTime', ''),
            'stopTime': run_response.get('stopTime', ''),
            'runOutputUri': run_response.get('runOutputUri', ''),
        }

        # Parse manifest log events
        log_events = manifest_logs.get('events', [])
        if not log_events:
            logger.warning(f'No manifest log events found for run {run_id}')
            return None

        # Extract task metrics and run details from manifest logs
        task_metrics = []
        run_details = {}

        for event in log_events:
            message = event.get('message', '').strip()

            try:
                # Each line in the manifest should be a JSON object
                if message.startswith('{') and message.endswith('}'):
                    parsed_message = json.loads(message)

                    # Check if this is a run-level object (has workflow info but no task-specific fields)
                    if (
                        'workflow' in parsed_message
                        and 'metrics' in parsed_message
                        and 'name' in parsed_message
                        and 'cpus' not in parsed_message
                    ):  # Run objects don't have cpus field
                        # This is run-level information
                        run_details = {
                            'arn': parsed_message.get('arn', ''),
                            'digest': parsed_message.get('digest', ''),
                            'runningSeconds': parsed_message.get('metrics', {}).get(
                                'runningSeconds', 0
                            ),
                            'parameters': parsed_message.get('parameters', {}),
                            'parameterTemplate': parsed_message.get('parameterTemplate', {}),
                            'storageType': parsed_message.get('storageType', ''),
                            'roleArn': parsed_message.get('roleArn', ''),
                            'startedBy': parsed_message.get('startedBy', ''),
                            'outputUri': parsed_message.get('outputUri', ''),
                            'resourceDigests': parsed_message.get('resourceDigests', {}),
                        }

                    # Check if this is a task-level object (has cpus, memory, instanceType)
                    elif (
                        'cpus' in parsed_message
                        and 'memory' in parsed_message
                        and 'instanceType' in parsed_message
                    ):
                        # This is task-level information
                        task_metric = _extract_task_metrics_from_manifest(parsed_message)
                        if task_metric:
                            task_metrics.append(task_metric)

            except json.JSONDecodeError:
                logger.debug(f'Non-JSON message in manifest (skipping): {message[:100]}...')
                continue
            except Exception as e:
                logger.warning(f'Error parsing manifest message: {str(e)}')
                continue

        # Calculate summary statistics
        total_tasks = len(task_metrics)
        total_allocated_cpus = sum(task.get('allocatedCpus', 0) for task in task_metrics)
        total_allocated_memory = sum(task.get('allocatedMemoryGiB', 0) for task in task_metrics)
        total_actual_cpu_usage = sum(task.get('avgCpuUtilization', 0) for task in task_metrics)
        total_actual_memory_usage = sum(
            task.get('avgMemoryUtilizationGiB', 0) for task in task_metrics
        )

        # Calculate efficiency ratios
        overall_cpu_efficiency = (
            (total_actual_cpu_usage / total_allocated_cpus) if total_allocated_cpus > 0 else 0
        )
        overall_memory_efficiency = (
            (total_actual_memory_usage / total_allocated_memory)
            if total_allocated_memory > 0
            else 0
        )

        return {
            'runInfo': run_info,
            'runDetails': run_details,
            'taskMetrics': task_metrics,
            'summary': {
                'totalTasks': total_tasks,
                'totalAllocatedCpus': total_allocated_cpus,
                'totalAllocatedMemoryGiB': total_allocated_memory,
                'totalActualCpuUsage': total_actual_cpu_usage,
                'totalActualMemoryUsageGiB': total_actual_memory_usage,
                'overallCpuEfficiency': overall_cpu_efficiency,
                'overallMemoryEfficiency': overall_memory_efficiency,
                'manifestLogCount': len(log_events),
            },
        }

    except Exception as e:
        logger.error(f'Error parsing manifest for run {run_id}: {str(e)}')
        await ctx.error(f'Error parsing manifest for run {run_id}: {str(e)}')
        return None


def _extract_task_metrics_from_manifest(task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract key metrics from a task manifest object based on the actual structure."""
    try:
        metrics = {
            'taskName': task_data.get('name', 'unknown'),
            'taskArn': task_data.get('arn', ''),
            'taskUuid': task_data.get('uuid', ''),
        }

        # Resource allocation (what was requested/reserved)
        metrics['allocatedCpus'] = task_data.get('cpus', 0)
        metrics['allocatedMemoryGiB'] = task_data.get('memory', 0)
        metrics['instanceType'] = task_data.get('instanceType', '')
        metrics['gpus'] = task_data.get('gpus', 0)
        metrics['image'] = task_data.get('image', '')

        # Extract metrics from the metrics object
        task_metrics = task_data.get('metrics', {})

        # CPU metrics
        metrics['reservedCpus'] = task_metrics.get('cpusReserved', 0)
        metrics['avgCpuUtilization'] = task_metrics.get('cpusAverage', 0)
        metrics['maxCpuUtilization'] = task_metrics.get('cpusMaximum', 0)

        # Memory metrics
        metrics['reservedMemoryGiB'] = task_metrics.get('memoryReservedGiB', 0)
        metrics['avgMemoryUtilizationGiB'] = task_metrics.get('memoryAverageGiB', 0)
        metrics['maxMemoryUtilizationGiB'] = task_metrics.get('memoryMaximumGiB', 0)

        # GPU metrics
        metrics['reservedGpus'] = task_metrics.get('gpusReserved', 0)

        # Timing information
        metrics['runningSeconds'] = task_metrics.get('runningSeconds', 0)
        metrics['startTime'] = task_data.get('startTime', '')
        metrics['stopTime'] = task_data.get('stopTime', '')
        metrics['creationTime'] = task_data.get('creationTime', '')
        metrics['status'] = task_data.get('status', '')

        # Calculate efficiency ratios (actual usage vs reserved resources)
        if metrics['reservedCpus'] > 0:
            metrics['cpuEfficiencyRatio'] = metrics['avgCpuUtilization'] / metrics['reservedCpus']
            metrics['maxCpuEfficiencyRatio'] = (
                metrics['maxCpuUtilization'] / metrics['reservedCpus']
            )
        else:
            metrics['cpuEfficiencyRatio'] = 0
            metrics['maxCpuEfficiencyRatio'] = 0

        if metrics['reservedMemoryGiB'] > 0:
            metrics['memoryEfficiencyRatio'] = (
                metrics['avgMemoryUtilizationGiB'] / metrics['reservedMemoryGiB']
            )
            metrics['maxMemoryEfficiencyRatio'] = (
                metrics['maxMemoryUtilizationGiB'] / metrics['reservedMemoryGiB']
            )
        else:
            metrics['memoryEfficiencyRatio'] = 0
            metrics['maxMemoryEfficiencyRatio'] = 0

        # Calculate potential waste (reserved but unused resources)
        metrics['wastedCpus'] = max(0, metrics['reservedCpus'] - metrics['avgCpuUtilization'])
        metrics['wastedMemoryGiB'] = max(
            0, metrics['reservedMemoryGiB'] - metrics['avgMemoryUtilizationGiB']
        )

        # Flag potential optimization opportunities
        metrics['isOverProvisioned'] = (
            metrics['cpuEfficiencyRatio'] < 0.5 or metrics['memoryEfficiencyRatio'] < 0.5
        )
        metrics['isUnderProvisioned'] = (
            metrics['maxCpuEfficiencyRatio'] > 0.9 or metrics['maxMemoryEfficiencyRatio'] > 0.9
        )

        return metrics

    except Exception as e:
        logger.warning(f'Error extracting task metrics: {str(e)}')
        return None


def _get_analysis_instructions() -> Dict[str, Any]:
    """Generate comprehensive analysis instructions for the AI agent."""
    return {
        'prompt': """
Please analyze the AWS HealthOmics workflow run data provided above and generate a comprehensive performance analysis report. The data includes detailed task metrics from run manifest logs showing actual resource utilization vs reserved resources.

## Key Analysis Areas:

### 1. Resource Utilization Efficiency
- **CPU Efficiency**: Compare `avgCpuUtilization` vs `reservedCpus` for each task
- **Memory Efficiency**: Compare `avgMemoryUtilizationGiB` vs `reservedMemoryGiB` for each task
- **Identify Over-Provisioned Tasks**: Tasks with efficiency ratios < 50% (wasting resources)
- **Identify Under-Provisioned Tasks**: Tasks with max utilization > 90% (may need more resources)

### 2. Cost Optimization Opportunities
- Calculate potential savings from right-sizing over-provisioned tasks
- Estimate cost of wasted CPU and memory resources (`wastedCpus`, `wastedMemoryGiB`)
- Recommend optimal instance types based on actual usage patterns
- Prioritize optimization efforts by potential impact

### 3. Performance Analysis
- Analyze `runningSeconds` for each task to identify bottlenecks
- Compare similar tasks (same `taskName` pattern) for consistency
- Look for tasks that could benefit from different resource configurations
- Identify workflow parallelization opportunities

### 4. Instance Type Optimization
- Review `instanceType` assignments vs actual resource usage
- Recommend more cost-effective instance types where appropriate
- Consider memory-optimized vs compute-optimized instances based on usage patterns

### 5. Specific Recommendations
For each task, provide:
- Current resource allocation vs actual usage
- Recommended resource allocation
- Estimated cost savings
- Priority level (high/medium/low impact)

## Data Structure Reference:
- `cpuEfficiencyRatio`: Actual CPU usage / Reserved CPUs
- `memoryEfficiencyRatio`: Actual memory usage / Reserved memory
- `isOverProvisioned`: Boolean flag for tasks wasting >50% of resources
- `isUnderProvisioned`: Boolean flag for tasks using >90% of max resources
- `wastedCpus/wastedMemoryGiB`: Unused reserved resources

Please provide specific, actionable recommendations with quantified benefits.
        """,
        'analysis_focus_areas': [
            'resource_utilization_efficiency',
            'cost_optimization_opportunities',
            'performance_bottlenecks',
            'instance_type_optimization',
            'workflow_parallelization_opportunities',
        ],
        'key_metrics_to_analyze': [
            'cpuEfficiencyRatio',
            'memoryEfficiencyRatio',
            'maxCpuEfficiencyRatio',
            'maxMemoryEfficiencyRatio',
            'wastedCpus',
            'wastedMemoryGiB',
            'isOverProvisioned',
            'isUnderProvisioned',
            'runningSeconds',
            'instanceType',
        ],
        'optimization_thresholds': {
            'over_provisioned_threshold': 0.5,
            'under_provisioned_threshold': 0.9,
            'efficiency_target': 0.7,
        },
    }
