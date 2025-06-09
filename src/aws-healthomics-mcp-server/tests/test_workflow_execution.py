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

"""Unit tests for workflow execution tools."""

import botocore.exceptions
import pytest
from awslabs.aws_healthomics_mcp_server.tools.workflow_execution import get_run, list_runs
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_run_success():
    """Test successful retrieval of run details."""
    # Mock response data
    creation_time = datetime.now(timezone.utc)
    start_time = creation_time
    stop_time = datetime.now(timezone.utc)

    mock_response = {
        'id': 'run-12345',
        'arn': 'arn:aws:omics:us-east-1:123456789012:run/run-12345',
        'name': 'test-run',
        'status': 'COMPLETED',
        'workflowId': 'wfl-12345',
        'workflowType': 'WDL',
        'workflowVersionName': 'v1.0',
        'creationTime': creation_time,
        'startTime': start_time,
        'stopTime': stop_time,
        'outputUri': 's3://bucket/output/',
        'parameters': {'param1': 'value1'},
        'uuid': 'abc-123-def-456',
        'statusMessage': 'Run completed successfully',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_run(mock_ctx, run_id='run-12345')

    # Verify client was called correctly
    mock_client.get_run.assert_called_once_with(id='run-12345')

    # Verify result contains all expected fields
    assert result['id'] == 'run-12345'
    assert result['arn'] == 'arn:aws:omics:us-east-1:123456789012:run/run-12345'
    assert result['name'] == 'test-run'
    assert result['status'] == 'COMPLETED'
    assert result['workflowId'] == 'wfl-12345'
    assert result['workflowType'] == 'WDL'
    assert result['workflowVersionName'] == 'v1.0'
    assert result['creationTime'] == creation_time.isoformat()
    assert result['startTime'] == start_time.isoformat()
    assert result['stopTime'] == stop_time.isoformat()
    assert result['outputUri'] == 's3://bucket/output/'
    assert result['parameters'] == {'param1': 'value1'}
    assert result['uuid'] == 'abc-123-def-456'
    assert result['statusMessage'] == 'Run completed successfully'


@pytest.mark.asyncio
async def test_get_run_minimal_response():
    """Test run retrieval with minimal response fields."""
    # Mock response with minimal fields
    creation_time = datetime.now(timezone.utc)
    mock_response = {
        'id': 'run-12345',
        'arn': 'arn:aws:omics:us-east-1:123456789012:run/run-12345',
        'name': 'test-run',
        'status': 'QUEUED',
        'workflowId': 'wfl-12345',
        'workflowType': 'WDL',
        'creationTime': creation_time,
        'outputUri': 's3://bucket/output/',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_run(mock_ctx, run_id='run-12345')

    # Verify required fields
    assert result['id'] == 'run-12345'
    assert result['status'] == 'QUEUED'
    assert result['creationTime'] == creation_time.isoformat()

    # Verify optional fields are not present
    assert 'startTime' not in result
    assert 'stopTime' not in result
    assert 'parameters' not in result
    assert 'statusMessage' not in result
    assert 'failureReason' not in result


@pytest.mark.asyncio
async def test_get_run_failed_status():
    """Test run retrieval with failed status and failure reason."""
    # Mock response for failed run
    mock_response = {
        'id': 'run-12345',
        'status': 'FAILED',
        'failureReason': 'Resource quota exceeded',
        'statusMessage': 'Run failed due to resource constraints',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_run(mock_ctx, run_id='run-12345')

    # Verify failure information
    assert result['status'] == 'FAILED'
    assert result['failureReason'] == 'Resource quota exceeded'
    assert result['statusMessage'] == 'Run failed due to resource constraints'


@pytest.mark.asyncio
async def test_get_run_boto_error():
    """Test handling of BotoCoreError."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.side_effect = botocore.exceptions.BotoCoreError()

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.BotoCoreError):
            await get_run(mock_ctx, run_id='run-12345')

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error getting run' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_run_client_error():
    """Test handling of ClientError."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Run not found'}}, 'GetRun'
    )

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.ClientError):
            await get_run(mock_ctx, run_id='run-12345')

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error getting run' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_run_unexpected_error():
    """Test handling of unexpected errors."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.side_effect = Exception('Unexpected error')

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(Exception, match='Unexpected error'):
            await get_run(mock_ctx, run_id='run-12345')

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Unexpected error getting run' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_run_none_timestamps():
    """Test handling of None values for timestamps."""
    # Mock response with None timestamps
    mock_response = {
        'id': 'run-12345',
        'status': 'PENDING',
        'creationTime': None,
        'startTime': None,
        'stopTime': None,
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_run.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_run(mock_ctx, run_id='run-12345')

    # Verify timestamp handling
    assert result['creationTime'] is None
    assert 'startTime' not in result
    assert 'stopTime' not in result


# Tests for list_runs function


@pytest.mark.asyncio
async def test_list_runs_success():
    """Test successful listing of runs."""
    # Mock response data
    creation_time = datetime.now(timezone.utc)
    start_time = datetime.now(timezone.utc)
    stop_time = datetime.now(timezone.utc)

    mock_response = {
        'items': [
            {
                'id': 'run-12345',
                'arn': 'arn:aws:omics:us-east-1:123456789012:run/run-12345',
                'name': 'test-run-1',
                'status': 'COMPLETED',
                'workflowId': 'wfl-12345',
                'workflowType': 'WDL',
                'creationTime': creation_time,
                'startTime': start_time,
                'stopTime': stop_time,
            },
            {
                'id': 'run-67890',
                'arn': 'arn:aws:omics:us-east-1:123456789012:run/run-67890',
                'name': 'test-run-2',
                'status': 'RUNNING',
                'workflowId': 'wfl-67890',
                'workflowType': 'CWL',
                'creationTime': creation_time,
                'startTime': start_time,
            },
        ],
        'nextToken': 'next-page-token',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status=None,
            created_after=None,
            created_before=None,
        )

    # Verify client was called correctly
    mock_client.list_runs.assert_called_once_with(maxResults=10)

    # Verify result structure
    assert 'runs' in result
    assert 'nextToken' in result
    assert result['nextToken'] == 'next-page-token'
    assert len(result['runs']) == 2

    # Verify first run
    run1 = result['runs'][0]
    assert run1['id'] == 'run-12345'
    assert run1['name'] == 'test-run-1'
    assert run1['status'] == 'COMPLETED'
    assert run1['workflowId'] == 'wfl-12345'
    assert run1['workflowType'] == 'WDL'
    assert run1['creationTime'] == creation_time.isoformat()
    assert run1['startTime'] == start_time.isoformat()
    assert run1['stopTime'] == stop_time.isoformat()

    # Verify second run (no stopTime)
    run2 = result['runs'][1]
    assert run2['id'] == 'run-67890'
    assert run2['status'] == 'RUNNING'
    assert 'stopTime' not in run2


@pytest.mark.asyncio
async def test_list_runs_with_filters():
    """Test listing runs with various filters."""
    mock_response = {'items': []}

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        await list_runs(
            ctx=mock_ctx,
            max_results=25,
            next_token='previous-token',
            status='COMPLETED',
            created_after='2023-01-01T00:00:00Z',
            created_before='2023-12-31T23:59:59Z',
        )

    # Verify client was called with all filters
    mock_client.list_runs.assert_called_once_with(
        maxResults=25,
        startingToken='previous-token',
        status='COMPLETED',
        createdAfter='2023-01-01T00:00:00Z',
        createdBefore='2023-12-31T23:59:59Z',
    )


@pytest.mark.asyncio
async def test_list_runs_empty_response():
    """Test listing runs with empty response."""
    mock_response = {'items': []}

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status=None,
            created_after=None,
            created_before=None,
        )

    # Verify empty result
    assert result['runs'] == []
    assert 'nextToken' not in result


@pytest.mark.asyncio
async def test_list_runs_invalid_status():
    """Test listing runs with invalid status."""
    mock_ctx = AsyncMock()

    with pytest.raises(ValueError, match='Invalid run status'):
        await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status='INVALID_STATUS',
            created_after=None,
            created_before=None,
        )

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Invalid run status' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_list_runs_boto_error():
    """Test handling of BotoCoreError in list_runs."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.side_effect = botocore.exceptions.BotoCoreError()

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.BotoCoreError):
            await list_runs(
                ctx=mock_ctx,
                max_results=10,
                next_token=None,
                status=None,
                created_after=None,
                created_before=None,
            )

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error listing runs' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_list_runs_client_error():
    """Test handling of ClientError in list_runs."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}}, 'ListRuns'
    )

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.ClientError):
            await list_runs(
                ctx=mock_ctx,
                max_results=10,
                next_token=None,
                status=None,
                created_after=None,
                created_before=None,
            )

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error listing runs' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_list_runs_unexpected_error():
    """Test handling of unexpected errors in list_runs."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.side_effect = Exception('Unexpected error')

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(Exception, match='Unexpected error'):
            await list_runs(
                ctx=mock_ctx,
                max_results=10,
                next_token=None,
                status=None,
                created_after=None,
                created_before=None,
            )

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Unexpected error listing runs' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_list_runs_minimal_run_data():
    """Test listing runs with minimal run data."""
    # Mock response with minimal fields
    creation_time = datetime.now(timezone.utc)
    mock_response = {
        'items': [
            {
                'id': 'run-12345',
                'status': 'QUEUED',
                'creationTime': creation_time,
            }
        ]
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status=None,
            created_after=None,
            created_before=None,
        )

    # Verify minimal run data
    run = result['runs'][0]
    assert run['id'] == 'run-12345'
    assert run['status'] == 'QUEUED'
    assert run['creationTime'] == creation_time.isoformat()

    # Verify optional fields are not present
    assert run.get('arn') is None
    assert run.get('name') is None
    assert run.get('workflowId') is None
    assert run.get('workflowType') is None
    assert 'startTime' not in run
    assert 'stopTime' not in run


@pytest.mark.asyncio
async def test_list_runs_none_timestamps():
    """Test listing runs with None timestamps."""
    # Mock response with None timestamps
    mock_response = {
        'items': [
            {
                'id': 'run-12345',
                'status': 'PENDING',
                'creationTime': None,
                'startTime': None,
                'stopTime': None,
            }
        ]
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status=None,
            created_after=None,
            created_before=None,
        )

    # Verify timestamp handling
    run = result['runs'][0]
    assert run['creationTime'] is None
    assert 'startTime' not in run
    assert 'stopTime' not in run


@pytest.mark.asyncio
async def test_list_runs_default_parameters():
    """Test list_runs with default parameters."""
    mock_response = {'items': []}

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_runs.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_execution.get_omics_client',
        return_value=mock_client,
    ):
        await list_runs(
            ctx=mock_ctx,
            max_results=10,
            next_token=None,
            status=None,
            created_after=None,
            created_before=None,
        )

    # Verify client was called with default parameters only
    mock_client.list_runs.assert_called_once_with(maxResults=10)
