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

"""Unit tests for workflow management tools."""

import botocore.exceptions
import pytest
from awslabs.aws_healthomics_mcp_server.tools.workflow_management import (
    get_workflow,
    list_workflows,
)
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_list_workflows_success():
    """Test successful listing of workflows."""
    # Mock response data
    creation_time = datetime.now(timezone.utc)
    mock_response = {
        'items': [
            {
                'id': 'wfl-12345',
                'arn': 'arn:aws:omics:us-east-1:123456789012:workflow/wfl-12345',
                'name': 'test-workflow-1',
                'description': 'Test workflow 1',
                'status': 'ACTIVE',
                'parameters': {'param1': 'value1'},
                'storageType': 'DYNAMIC',
                'type': 'WDL',
                'creationTime': creation_time,
            },
            {
                'id': 'wfl-67890',
                'arn': 'arn:aws:omics:us-east-1:123456789012:workflow/wfl-67890',
                'name': 'test-workflow-2',
                'status': 'ACTIVE',
                'storageType': 'STATIC',
                'storageCapacity': 100,
                'type': 'CWL',
                'creationTime': creation_time,
            },
        ],
        'nextToken': 'next-page-token',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_workflows.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_workflows(ctx=mock_ctx, max_results=10, next_token=None)

    # Verify client was called correctly
    mock_client.list_workflows.assert_called_once_with(maxResults=10)

    # Verify result structure
    assert 'workflows' in result
    assert 'nextToken' in result
    assert result['nextToken'] == 'next-page-token'
    assert len(result['workflows']) == 2

    # Verify first workflow
    wf1 = result['workflows'][0]
    assert wf1['id'] == 'wfl-12345'
    assert wf1['name'] == 'test-workflow-1'
    assert wf1['description'] == 'Test workflow 1'
    assert wf1['status'] == 'ACTIVE'
    assert wf1['parameters'] == {'param1': 'value1'}
    assert wf1['storageType'] == 'DYNAMIC'
    assert wf1['type'] == 'WDL'
    assert wf1['creationTime'] == creation_time.isoformat()

    # Verify second workflow
    wf2 = result['workflows'][1]
    assert wf2['id'] == 'wfl-67890'
    assert wf2['status'] == 'ACTIVE'
    assert wf2['storageType'] == 'STATIC'
    assert wf2['storageCapacity'] == 100


@pytest.mark.asyncio
async def test_list_workflows_empty_response():
    """Test listing workflows with empty response."""
    mock_response = {'items': []}

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_workflows.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_workflows(ctx=mock_ctx, max_results=10, next_token=None)

    # Verify empty result
    assert result['workflows'] == []
    assert 'nextToken' not in result


@pytest.mark.asyncio
async def test_list_workflows_with_pagination():
    """Test listing workflows with pagination."""
    mock_response = {
        'items': [{'id': 'wfl-12345', 'name': 'test-workflow'}],
        'nextToken': 'next-page-token',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_workflows.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await list_workflows(ctx=mock_ctx, max_results=10, next_token='current-token')

    # Verify pagination parameters
    mock_client.list_workflows.assert_called_once_with(
        maxResults=10, startingToken='current-token'
    )
    assert result['nextToken'] == 'next-page-token'


@pytest.mark.asyncio
async def test_list_workflows_boto_error():
    """Test handling of BotoCoreError in list_workflows."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_workflows.side_effect = botocore.exceptions.BotoCoreError()

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.BotoCoreError):
            await list_workflows(ctx=mock_ctx, max_results=10, next_token=None)

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error listing workflows' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_list_workflows_unexpected_error():
    """Test handling of unexpected errors in list_workflows."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.list_workflows.side_effect = Exception('Unexpected error')

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(Exception, match='Unexpected error'):
            await list_workflows(ctx=mock_ctx, max_results=10, next_token=None)

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Unexpected error listing workflows' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_workflow_success():
    """Test successful retrieval of workflow details."""
    # Mock response data
    creation_time = datetime.now(timezone.utc)
    mock_response = {
        'id': 'wfl-12345',
        'arn': 'arn:aws:omics:us-east-1:123456789012:workflow/wfl-12345',
        'name': 'test-workflow',
        'status': 'ACTIVE',
        'type': 'WDL',
        'description': 'Test workflow description',
        'parameterTemplate': {'param1': {'type': 'string'}},
        'creationTime': creation_time,
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type=None)

    # Verify client was called correctly
    mock_client.get_workflow.assert_called_once_with(id='wfl-12345')

    # Verify result contains all expected fields
    assert result['id'] == 'wfl-12345'
    assert result['arn'] == 'arn:aws:omics:us-east-1:123456789012:workflow/wfl-12345'
    assert result['name'] == 'test-workflow'
    assert result['status'] == 'ACTIVE'
    assert result['type'] == 'WDL'
    assert result['description'] == 'Test workflow description'
    assert result['parameterTemplate'] == {'param1': {'type': 'string'}}
    assert result['creationTime'] == creation_time.isoformat()


@pytest.mark.asyncio
async def test_get_workflow_with_export():
    """Test workflow retrieval with export type."""
    # Mock response data
    mock_response = {
        'id': 'wfl-12345',
        'name': 'test-workflow',
        'definition': 'workflow test { ... }',
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_workflow(
            ctx=mock_ctx, workflow_id='wfl-12345', export_type='DEFINITION'
        )

    # Verify export parameter was passed
    mock_client.get_workflow.assert_called_once_with(id='wfl-12345', export='DEFINITION')

    # Verify definition was included in result
    assert result['definition'] == 'workflow test { ... }'


@pytest.mark.asyncio
async def test_get_workflow_invalid_export_type():
    """Test workflow retrieval with invalid export type."""
    mock_ctx = AsyncMock()

    with pytest.raises(ValueError, match='Invalid export type'):
        await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type='INVALID')

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Invalid export type' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_workflow_minimal_response():
    """Test workflow retrieval with minimal response fields."""
    # Mock response with minimal fields
    creation_time = datetime.now(timezone.utc)
    mock_response = {
        'id': 'wfl-12345',
        'arn': 'arn:aws:omics:us-east-1:123456789012:workflow/wfl-12345',
        'name': 'test-workflow',
        'status': 'ACTIVE',
        'type': 'WDL',
        'creationTime': creation_time,
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type=None)

    # Verify required fields
    assert result['id'] == 'wfl-12345'
    assert result['status'] == 'ACTIVE'
    assert result['creationTime'] == creation_time.isoformat()

    # Verify optional fields are not present
    assert 'description' not in result
    assert 'parameterTemplate' not in result
    assert 'definition' not in result


@pytest.mark.asyncio
async def test_get_workflow_boto_error():
    """Test handling of BotoCoreError in get_workflow."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.side_effect = botocore.exceptions.BotoCoreError()

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(botocore.exceptions.BotoCoreError):
            await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type=None)

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'AWS error getting workflow' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_workflow_unexpected_error():
    """Test handling of unexpected errors in get_workflow."""
    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.side_effect = Exception('Unexpected error')

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        with pytest.raises(Exception, match='Unexpected error'):
            await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type=None)

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Unexpected error getting workflow' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_get_workflow_none_timestamp():
    """Test handling of None timestamp in get_workflow."""
    # Mock response with None timestamp
    mock_response = {
        'id': 'wfl-12345',
        'name': 'test-workflow',
        'status': 'ACTIVE',
        'type': 'WDL',
        'creationTime': None,
    }

    # Mock context and client
    mock_ctx = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_workflow.return_value = mock_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_management.get_omics_client',
        return_value=mock_client,
    ):
        result = await get_workflow(ctx=mock_ctx, workflow_id='wfl-12345', export_type=None)

    # Verify timestamp handling
    assert result['creationTime'] is None
