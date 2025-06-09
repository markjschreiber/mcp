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

"""Tests for troubleshooting tools."""

import botocore.exceptions
import pytest
from awslabs.aws_healthomics_mcp_server.tools.troubleshooting import (
    diagnose_run_failure,
    get_omics_client,
)
from mcp.server.fastmcp import Context
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_context():
    """Create a mock MCP context."""
    context = AsyncMock(spec=Context)
    return context


@pytest.fixture
def mock_omics_client():
    """Create a mock HealthOmics client."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_failed_run_response():
    """Sample failed run response."""
    return {
        'id': 'run-12345',
        'status': 'FAILED',
        'failureReason': 'Task execution failed due to insufficient memory',
        'name': 'test-workflow-run',
        'workflowId': 'workflow-67890',
    }


@pytest.fixture
def sample_running_run_response():
    """Sample running run response."""
    return {
        'id': 'run-12345',
        'status': 'RUNNING',
        'name': 'test-workflow-run',
        'workflowId': 'workflow-67890',
    }


@pytest.fixture
def sample_failed_tasks():
    """Sample failed tasks response."""
    return {
        'items': [
            {
                'taskId': 'task-111',
                'name': 'preprocessing',
                'status': 'FAILED',
                'statusMessage': 'Container exited with code 1',
            },
            {
                'taskId': 'task-222',
                'name': 'analysis',
                'status': 'FAILED',
                'statusMessage': 'Out of memory error',
            },
        ]
    }


@pytest.fixture
def sample_log_events():
    """Sample log events."""
    return {
        'events': [
            {'message': 'Starting task execution'},
            {'message': 'Error: insufficient memory'},
            {'message': 'Task failed with exit code 1'},
        ]
    }


class TestGetOmicsClient:
    """Test the get_omics_client function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_aws_session')
    def test_get_omics_client_success(self, mock_get_aws_session):
        """Test successful HealthOmics client creation."""
        # Arrange
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_get_aws_session.return_value = mock_session
        mock_session.client.return_value = mock_client

        # Act
        result = get_omics_client()

        # Assert
        assert result == mock_client
        mock_session.client.assert_called_once_with('omics')

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_aws_session')
    def test_get_omics_client_failure(self, mock_get_aws_session):
        """Test HealthOmics client creation failure."""
        # Arrange
        mock_get_aws_session.side_effect = Exception('AWS session error')

        # Act & Assert
        with pytest.raises(Exception, match='AWS session error'):
            get_omics_client()


class TestDiagnoseRunFailure:
    """Test the diagnose_run_failure function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_run_engine_logs')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_task_logs')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_success(
        self,
        mock_get_task_logs,
        mock_get_run_engine_logs,
        mock_get_omics_client,
        mock_context,
        sample_failed_run_response,
        sample_failed_tasks,
        sample_log_events,
    ):
        """Test successful run failure diagnosis."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.return_value = sample_failed_run_response
        mock_client.list_run_tasks.return_value = sample_failed_tasks

        # Mock log responses
        mock_get_run_engine_logs.return_value = sample_log_events
        mock_get_task_logs.return_value = sample_log_events

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        assert result['runId'] == 'run-12345'
        assert result['status'] == 'FAILED'
        assert result['failureReason'] == 'Task execution failed due to insufficient memory'
        assert len(result['engineLogs']) == 3
        assert len(result['failedTasks']) == 2
        assert len(result['recommendations']) > 0

        # Verify failed task details
        first_task = result['failedTasks'][0]
        assert first_task['taskId'] == 'task-111'
        assert first_task['name'] == 'preprocessing'
        assert first_task['statusMessage'] == 'Container exited with code 1'
        assert len(first_task['logs']) == 3

        # Verify API calls
        mock_client.get_run.assert_called_once_with(id='run-12345')
        mock_client.list_run_tasks.assert_called_once_with(
            id='run-12345',
            status='FAILED',
            maxResults=10,
        )

        # Verify log function calls with correct parameters
        mock_get_run_engine_logs.assert_called_once_with(
            ctx=mock_context,
            run_id='run-12345',
            limit=100,
            start_from_head=False,
        )

        # Verify task log calls
        assert mock_get_task_logs.call_count == 2
        mock_get_task_logs.assert_any_call(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-111',
            limit=50,
            start_from_head=False,
        )
        mock_get_task_logs.assert_any_call(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-222',
            limit=50,
            start_from_head=False,
        )

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_not_failed(
        self,
        mock_get_omics_client,
        mock_context,
        sample_running_run_response,
    ):
        """Test diagnosis of a run that is not in FAILED state."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.return_value = sample_running_run_response

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        assert result['status'] == 'RUNNING'
        assert 'Run is not in FAILED state' in result['message']
        assert 'Current status: RUNNING' in result['message']

        # Verify no further API calls were made
        mock_client.list_run_tasks.assert_not_called()

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_run_engine_logs')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_engine_logs_error(
        self,
        mock_get_run_engine_logs,
        mock_get_omics_client,
        mock_context,
        sample_failed_run_response,
        sample_failed_tasks,
    ):
        """Test diagnosis when engine log retrieval fails."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.return_value = sample_failed_run_response
        mock_client.list_run_tasks.return_value = {'items': []}  # No failed tasks

        # Mock engine logs to raise an exception
        mock_get_run_engine_logs.side_effect = Exception('Log retrieval failed')

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        assert result['runId'] == 'run-12345'
        assert result['status'] == 'FAILED'
        assert len(result['engineLogs']) == 1
        assert 'Error retrieving engine logs' in result['engineLogs'][0]
        assert len(result['failedTasks']) == 0

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_run_engine_logs')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_task_logs')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_task_logs_error(
        self,
        mock_get_task_logs,
        mock_get_run_engine_logs,
        mock_get_omics_client,
        mock_context,
        sample_failed_run_response,
        sample_failed_tasks,
        sample_log_events,
    ):
        """Test diagnosis when task log retrieval fails."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.return_value = sample_failed_run_response
        mock_client.list_run_tasks.return_value = sample_failed_tasks

        # Mock successful engine logs but failed task logs
        mock_get_run_engine_logs.return_value = sample_log_events
        mock_get_task_logs.side_effect = Exception('Task log retrieval failed')

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        assert result['runId'] == 'run-12345'
        assert len(result['engineLogs']) == 3  # Engine logs succeeded
        assert len(result['failedTasks']) == 2  # Tasks are still included

        # Check that task logs contain error messages
        for task in result['failedTasks']:
            assert len(task['logs']) == 1
            assert 'Error retrieving task logs' in task['logs'][0]

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_boto_error(
        self,
        mock_get_omics_client,
        mock_context,
    ):
        """Test diagnosis with boto client error."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.side_effect = botocore.exceptions.ClientError(
            error_response={
                'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Run not found'}
            },
            operation_name='GetRun',
        )

        # Act & Assert
        with pytest.raises(botocore.exceptions.ClientError):
            await diagnose_run_failure(
                ctx=mock_context,
                run_id='run-12345',
            )

        # Verify error was reported to context
        mock_context.error.assert_called_once()
        error_call_args = mock_context.error.call_args[0][0]
        assert 'AWS error diagnosing run failure' in error_call_args
        assert 'run-12345' in error_call_args

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_unexpected_error(
        self,
        mock_get_omics_client,
        mock_context,
    ):
        """Test diagnosis with unexpected error."""
        # Arrange
        mock_get_omics_client.side_effect = Exception('Unexpected error')

        # Act & Assert
        with pytest.raises(Exception, match='Unexpected error'):
            await diagnose_run_failure(
                ctx=mock_context,
                run_id='run-12345',
            )

        # Verify error was reported to context
        mock_context.error.assert_called_once()
        error_call_args = mock_context.error.call_args[0][0]
        assert 'Unexpected error diagnosing run failure' in error_call_args
        assert 'run-12345' in error_call_args

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_run_engine_logs')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_no_failure_reason(
        self,
        mock_get_run_engine_logs,
        mock_get_omics_client,
        mock_context,
        sample_log_events,
    ):
        """Test diagnosis when run has no failure reason."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client

        # Run response without failureReason
        run_response = {
            'id': 'run-12345',
            'status': 'FAILED',
            'name': 'test-workflow-run',
            'workflowId': 'workflow-67890',
        }
        mock_client.get_run.return_value = run_response
        mock_client.list_run_tasks.return_value = {'items': []}
        mock_get_run_engine_logs.return_value = sample_log_events

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        assert result['failureReason'] == 'No failure reason provided'

    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_omics_client')
    @patch('awslabs.aws_healthomics_mcp_server.tools.troubleshooting.get_run_engine_logs')
    @pytest.mark.asyncio
    async def test_diagnose_run_failure_recommendations_included(
        self,
        mock_get_run_engine_logs,
        mock_get_omics_client,
        mock_context,
        sample_failed_run_response,
        sample_log_events,
    ):
        """Test that diagnosis includes helpful recommendations."""
        # Arrange
        mock_client = MagicMock()
        mock_get_omics_client.return_value = mock_client
        mock_client.get_run.return_value = sample_failed_run_response
        mock_client.list_run_tasks.return_value = {'items': []}
        mock_get_run_engine_logs.return_value = sample_log_events

        # Act
        result = await diagnose_run_failure(
            ctx=mock_context,
            run_id='run-12345',
        )

        # Assert
        recommendations = result['recommendations']
        assert len(recommendations) > 0

        # Check for specific recommendations
        recommendation_text = ' '.join(recommendations)
        assert 'IAM role permissions' in recommendation_text
        assert 'container images' in recommendation_text
        assert 'input files' in recommendation_text
        assert 'syntax errors' in recommendation_text
        assert 'parameter values' in recommendation_text
