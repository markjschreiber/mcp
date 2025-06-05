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

import csv
import os
import subprocess
import tempfile
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from loguru import logger
from typing import Any, Dict, List, Optional


def get_logs_client():
    """Get an AWS CloudWatch Logs client.

    Returns:
        boto3.client: Configured CloudWatch Logs client
    """
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    session = get_aws_session(region)
    return session.client('logs')


async def analyze_run(
    run_ids: List[str],
    headroom: Optional[float] = 0.1,
) -> Dict[str, Any]:
    """Analyze run performance using the run analyzer.

    Args:
        run_ids: List of run IDs to analyze
        headroom: Resource headroom factor (0.0-1.0, default: 0.1)

    Returns:
        Dictionary containing analysis results
    """
    # Validate headroom
    if not 0.0 <= headroom <= 1.0:
        return {'error': 'Headroom must be between 0.0 and 1.0'}

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
                logger.error(f'Error running run analyzer: {process.stderr}')
                return {'error': f'Run analyzer failed: {process.stderr}'}

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
    except Exception as e:
        logger.error(f'Error analyzing run: {str(e)}')
        return {'error': str(e)}


async def get_run_logs(
    run_id: str,
    task_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: Optional[int] = 100,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve logs for a run or task.

    Args:
        run_id: ID of the run
        task_id: Optional ID of a specific task
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination

    Returns:
        Dictionary containing log events and next token if available
    """
    client = get_logs_client()

    # Construct log group and log stream names
    log_group_name = '/aws/omics/WorkflowLog'
    log_stream_name = f'run/{run_id}'

    if task_id:
        log_stream_name += f'/task/{task_id}'
    else:
        log_stream_name += '/engine'

    params = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'limit': limit,
        'startFromHead': True,
    }

    if next_token:
        params['nextToken'] = next_token

    if start_time:
        from datetime import datetime

        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        params['startTime'] = int(start_dt.timestamp() * 1000)

    if end_time:
        from datetime import datetime

        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        params['endTime'] = int(end_dt.timestamp() * 1000)

    try:
        response = client.get_log_events(**params)

        # Transform the response to a more user-friendly format
        events = []
        for event in response.get('events', []):
            events.append(
                {
                    'timestamp': datetime.fromtimestamp(
                        event.get('timestamp', 0) / 1000
                    ).isoformat(),
                    'message': event.get('message', ''),
                }
            )

        result = {'events': events}
        if 'nextForwardToken' in response:
            result['nextToken'] = response['nextForwardToken']

        return result
    except Exception as e:
        logger.error(f'Error retrieving logs: {str(e)}')
        return {'error': str(e)}
