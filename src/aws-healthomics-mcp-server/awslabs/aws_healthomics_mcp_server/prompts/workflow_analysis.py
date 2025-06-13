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

"""Workflow analysis prompts for the AWS HealthOmics MCP server."""

import json
import os
from awslabs.aws_healthomics_mcp_server.consts import DEFAULT_REGION
from awslabs.aws_healthomics_mcp_server.tools.workflow_analysis import (
    get_run_manifest_logs_internal,
)
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session
from datetime import datetime, timezone
from loguru import logger
from pydantic import Field
from typing import Any, Dict, List, Optional


async def optimize_runs_prompt(
    run_ids: List[str] = Field(
        ...,
        description='List of run IDs to analyze for resource optimization',
    ),
) -> str:
    """The user wants to optimize resources used in a run or list of runs.

    This prompt retrieves run manifest logs containing detailed task metrics
    and returns structured data with analysis instructions for AI-powered insights.

    The manifest logs contain comprehensive information about:
    - Task resource allocation vs actual usage
    - CPU and memory utilization patterns
    - Runtime performance metrics
    - Cost optimization opportunities

    Args:
        ctx: MCP context for error reporting
        run_ids: List of run IDs to analyze

    Returns:
        Formatted prompt string with structured manifest data and analysis instructions
    """
    try:
        logger.info(f'Generating analysis prompt for runs {run_ids}')

        # Get the structured analysis data
        analysis_data = await _get_run_analysis_data(run_ids)

        if not analysis_data or not analysis_data.get('runs'):
            return f"""
I was unable to retrieve manifest data for the specified run IDs: {run_ids}

This could be because:
- The runs are still in progress (manifest logs are only available after completion)
- The run IDs are invalid
- There was an error accessing the CloudWatch logs

Please verify the run IDs and ensure the runs have completed successfully.
"""

        # Generate the comprehensive analysis prompt
        prompt = f"""
# AWS HealthOmics Workflow Performance Analysis

Please analyze the following AWS HealthOmics workflow run data and provide comprehensive performance optimization recommendations.

## Run Data Summary
- **Total Runs Analyzed**: {analysis_data['summary']['totalRuns']}
- **Analysis Timestamp**: {analysis_data['summary']['analysisTimestamp']}
- **Analysis Type**: {analysis_data['summary']['analysisType']}

## Detailed Run and Task Metrics

```json
{json.dumps(analysis_data, indent=2)}
```

## Analysis Instructions

Please provide a comprehensive performance analysis report focusing on these key areas:

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

## Key Metrics Reference
- `cpuEfficiencyRatio`: Actual CPU usage / Reserved CPUs
- `memoryEfficiencyRatio`: Actual memory usage / Reserved memory
- `isOverProvisioned`: Boolean flag for tasks wasting >50% of resources
- `isUnderProvisioned`: Boolean flag for tasks using >90% of max resources
- `wastedCpus/wastedMemoryGiB`: Unused reserved resources

## Optimization Thresholds
- **Over-provisioned threshold**: < 50% efficiency
- **Under-provisioned threshold**: > 90% max utilization
- **Target efficiency**: ~70% for optimal cost/performance balance

Please provide specific, actionable recommendations with quantified benefits and clear prioritization.
"""

        logger.info(f'Generated analysis prompt for {len(analysis_data["runs"])} runs')
        return prompt

    except Exception as e:
        error_message = f'Error generating analysis prompt: {str(e)}'
        logger.error(error_message)
        return f"""
Error generating analysis prompt for runs {run_ids}: {str(e)}

Please check the run IDs and try again. If the issue persists, the runs may still be in progress or there may be an issue accessing the manifest logs.
"""


async def _get_run_analysis_data(run_ids: List[str]) -> Dict[str, Any]:
    """Get structured analysis data for the specified runs."""
    try:
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
                    run_id, run_response, manifest_logs
                )

                if run_analysis:
                    analysis_results['runs'].append(run_analysis)

            except Exception as e:
                logger.error(f'Error processing run {run_id}: {str(e)}')
                # Continue with other runs rather than failing completely
                continue

        return analysis_results

    except Exception as e:
        logger.error(f'Error getting run analysis data: {str(e)}')
        return {}


async def _parse_manifest_for_analysis(
    run_id: str, run_response: Dict[str, Any], manifest_logs: Dict[str, Any]
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
