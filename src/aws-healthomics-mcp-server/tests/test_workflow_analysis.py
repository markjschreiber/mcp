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

"""Tests for workflow analysis tools."""

import botocore.exceptions
import pytest
from awslabs.aws_healthomics_mcp_server.prompts.workflow_analysis import (
    _normalize_run_ids,
)
from awslabs.aws_healthomics_mcp_server.tools.workflow_analysis import (
    _get_logs_from_stream,
    get_run_engine_logs,
    get_run_logs,
    get_run_manifest_logs,
    get_task_logs,
)
from mcp.server.fastmcp import Context
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_context():
    """Create a mock MCP context."""
    context = AsyncMock(spec=Context)
    return context


@pytest.fixture
def mock_logs_client():
    """Create a mock CloudWatch Logs client."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_log_events():
    """Sample log events for testing."""
    return [
        {
            'timestamp': 1640995200000,  # 2022-01-01 00:00:00 UTC
            'message': 'Starting workflow execution',
        },
        {
            'timestamp': 1640995260000,  # 2022-01-01 00:01:00 UTC
            'message': 'Task completed successfully',
        },
        {
            'timestamp': 1640995320000,  # 2022-01-01 00:02:00 UTC
            'message': 'Workflow execution completed',
        },
    ]


class TestGetLogsFromStream:
    """Test the helper function _get_logs_from_stream."""

    @pytest.mark.asyncio
    async def test_get_logs_from_stream_basic(self, mock_logs_client, sample_log_events):
        """Test basic log retrieval functionality."""
        # Arrange
        mock_logs_client.get_log_events.return_value = {
            'events': sample_log_events,
            'nextForwardToken': 'next-token-123',
        }

        # Act
        result = await _get_logs_from_stream(
            client=mock_logs_client,
            log_group_name='/aws/omics/WorkflowLog',
            log_stream_name='run/12345',
            limit=100,
        )

        # Assert
        assert 'events' in result
        assert 'nextToken' in result
        assert len(result['events']) == 3
        assert result['nextToken'] == 'next-token-123'

        # Check event transformation
        first_event = result['events'][0]
        assert 'timestamp' in first_event
        assert 'message' in first_event
        assert first_event['message'] == 'Starting workflow execution'
        # The timestamp should be converted from milliseconds to UTC ISO format
        # 1640995200000 ms = 2022-01-01T00:00:00Z UTC
        assert first_event['timestamp'] == '2022-01-01T00:00:00Z'

        # Verify API call
        mock_logs_client.get_log_events.assert_called_once_with(
            logGroupName='/aws/omics/WorkflowLog',
            logStreamName='run/12345',
            limit=100,
            startFromHead=True,
        )

    @pytest.mark.asyncio
    async def test_get_logs_from_stream_with_time_filters(
        self, mock_logs_client, sample_log_events
    ):
        """Test log retrieval with time filters."""
        # Arrange
        mock_logs_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        start_time = '2022-01-01T00:00:00Z'
        end_time = '2022-01-01T00:05:00Z'

        # Act
        result = await _get_logs_from_stream(
            client=mock_logs_client,
            log_group_name='/aws/omics/WorkflowLog',
            log_stream_name='run/12345',
            start_time=start_time,
            end_time=end_time,
            limit=50,
            start_from_head=False,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

        # Verify API call with time parameters
        call_args = mock_logs_client.get_log_events.call_args[1]
        assert call_args['logGroupName'] == '/aws/omics/WorkflowLog'
        assert call_args['logStreamName'] == 'run/12345'
        assert call_args['limit'] == 50
        assert call_args['startFromHead'] is False
        assert 'startTime' in call_args
        assert 'endTime' in call_args

    @pytest.mark.asyncio
    async def test_get_logs_from_stream_with_next_token(self, mock_logs_client, sample_log_events):
        """Test log retrieval with pagination token."""
        # Arrange
        mock_logs_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await _get_logs_from_stream(
            client=mock_logs_client,
            log_group_name='/aws/omics/WorkflowLog',
            log_stream_name='run/12345',
            next_token='existing-token-456',
        )

        # Assert
        assert 'events' in result

        # Verify API call includes next token
        mock_logs_client.get_log_events.assert_called_once_with(
            logGroupName='/aws/omics/WorkflowLog',
            logStreamName='run/12345',
            limit=100,
            startFromHead=True,
            nextToken='existing-token-456',
        )

    @pytest.mark.asyncio
    async def test_get_logs_from_stream_no_next_token_in_response(
        self, mock_logs_client, sample_log_events
    ):
        """Test log retrieval when response doesn't include next token."""
        # Arrange
        mock_logs_client.get_log_events.return_value = {
            'events': sample_log_events,
            # No nextForwardToken in response
        }

        # Act
        result = await _get_logs_from_stream(
            client=mock_logs_client,
            log_group_name='/aws/omics/WorkflowLog',
            log_stream_name='run/12345',
        )

        # Assert
        assert 'events' in result
        assert 'nextToken' not in result


class TestGetRunLogs:
    """Test the get_run_logs function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_logs_success(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test successful run log retrieval."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
            'nextForwardToken': 'next-token-123',
        }

        # Act - Call with explicit parameter values
        result = await get_run_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time=None,
            end_time=None,
            limit=50,
            next_token=None,
            start_from_head=False,
        )

        # Assert
        assert 'events' in result
        assert 'nextToken' in result
        assert len(result['events']) == 3
        assert result['nextToken'] == 'next-token-123'

        # Verify correct log stream name
        mock_client.get_log_events.assert_called_once()
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['logGroupName'] == '/aws/omics/WorkflowLog'
        assert call_args['logStreamName'] == 'run/run-12345'
        assert call_args['limit'] == 50
        assert call_args['startFromHead'] is False

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_logs_with_time_range(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test run log retrieval with time range."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_run_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time='2022-01-01T00:00:00Z',
            end_time='2022-01-01T00:05:00Z',
            limit=100,
            next_token=None,
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_logs_boto_error(self, mock_get_logs_client, mock_context):
        """Test run log retrieval with boto error."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.side_effect = botocore.exceptions.ClientError(
            error_response={
                'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Log stream not found'}
            },
            operation_name='GetLogEvents',
        )

        # Act & Assert
        with pytest.raises(botocore.exceptions.ClientError):
            await get_run_logs(
                ctx=mock_context,
                run_id='run-12345',
                start_time=None,
                end_time=None,
                limit=100,
                next_token=None,
                start_from_head=True,
            )

        # Verify error was reported to context
        mock_context.error.assert_called_once()

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_logs_invalid_timestamp(self, mock_get_logs_client, mock_context):
        """Test run log retrieval with invalid timestamp."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client

        # Act & Assert
        with pytest.raises(ValueError):
            await get_run_logs(
                ctx=mock_context,
                run_id='run-12345',
                start_time='invalid-timestamp',
                end_time=None,
                limit=100,
                next_token=None,
                start_from_head=True,
            )

        # Verify error was reported to context
        mock_context.error.assert_called_once()


class TestGetRunManifestLogs:
    """Test the get_run_manifest_logs function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_manifest_logs_with_uuid(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test manifest log retrieval with run UUID."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_run_manifest_logs(
            ctx=mock_context,
            run_id='run-12345',
            run_uuid='uuid-67890',
            start_time=None,
            end_time=None,
            limit=100,
            next_token=None,
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

        # Verify correct log stream name with UUID
        mock_client.get_log_events.assert_called_once()
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['logStreamName'] == 'manifest/run/run-12345/uuid-67890'

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_manifest_logs_without_uuid(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test manifest log retrieval without run UUID."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_run_manifest_logs(
            ctx=mock_context,
            run_id='run-12345',
            run_uuid=None,
            start_time=None,
            end_time=None,
            limit=100,
            next_token=None,
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

        # Verify correct log stream name without UUID
        mock_client.get_log_events.assert_called_once()
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['logStreamName'] == 'manifest/run/run-12345'


class TestGetRunEngineLogs:
    """Test the get_run_engine_logs function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_engine_logs_success(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test successful engine log retrieval."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_run_engine_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time=None,
            end_time=None,
            limit=100,
            next_token=None,
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

        # Verify correct log stream name
        mock_client.get_log_events.assert_called_once()
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['logStreamName'] == 'run/run-12345/engine'
        assert call_args['startFromHead'] is True

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_engine_logs_from_tail(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test engine log retrieval from tail."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_run_engine_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time=None,
            end_time=None,
            limit=100,
            next_token=None,
            start_from_head=False,
        )

        # Assert
        assert 'events' in result

        # Verify startFromHead parameter
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['startFromHead'] is False


class TestGetTaskLogs:
    """Test the get_task_logs function."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_task_logs_success(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test successful task log retrieval."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act
        result = await get_task_logs(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-67890',
            start_time=None,
            end_time=None,
            limit=100,
            next_token=None,
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert len(result['events']) == 3

        # Verify correct log stream name
        mock_client.get_log_events.assert_called_once()
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['logStreamName'] == 'run/run-12345/task/task-67890'

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_task_logs_with_pagination(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test task log retrieval with pagination."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
            'nextForwardToken': 'next-token-456',
        }

        # Act
        result = await get_task_logs(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-67890',
            start_time=None,
            end_time=None,
            limit=25,
            next_token='prev-token-123',
            start_from_head=True,
        )

        # Assert
        assert 'events' in result
        assert 'nextToken' in result
        assert result['nextToken'] == 'next-token-456'

        # Verify pagination parameters
        call_args = mock_client.get_log_events.call_args[1]
        assert call_args['nextToken'] == 'prev-token-123'
        assert call_args['limit'] == 25

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_task_logs_unexpected_error(self, mock_get_logs_client, mock_context):
        """Test task log retrieval with unexpected error."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.side_effect = Exception('Unexpected error')

        # Act & Assert
        with pytest.raises(Exception, match='Unexpected error'):
            await get_task_logs(
                ctx=mock_context,
                run_id='run-12345',
                task_id='task-67890',
                start_time=None,
                end_time=None,
                limit=100,
                next_token=None,
                start_from_head=True,
            )

        # Verify error was reported to context
        mock_context.error.assert_called_once()


class TestParameterValidation:
    """Test parameter validation for log functions."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_run_logs_with_valid_limits(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test run logs with valid limit values."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act & Assert - Test minimum valid limit
        result = await get_run_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time=None,
            end_time=None,
            limit=1,  # Minimum valid
            next_token=None,
            start_from_head=True,
        )
        assert 'events' in result

        # Test maximum valid limit
        result = await get_run_logs(
            ctx=mock_context,
            run_id='run-12345',
            start_time=None,
            end_time=None,
            limit=10000,  # Maximum valid
            next_token=None,
            start_from_head=True,
        )
        assert 'events' in result

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_analysis.get_logs_client')
    @pytest.mark.asyncio
    async def test_get_task_logs_with_valid_limits(
        self, mock_get_logs_client, mock_context, sample_log_events
    ):
        """Test task logs with valid limit values."""
        # Arrange
        mock_client = MagicMock()
        mock_get_logs_client.return_value = mock_client
        mock_client.get_log_events.return_value = {
            'events': sample_log_events,
        }

        # Act & Assert - Test minimum valid limit
        result = await get_task_logs(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-67890',
            start_time=None,
            end_time=None,
            limit=1,  # Minimum valid
            next_token=None,
            start_from_head=True,
        )
        assert 'events' in result

        # Test maximum valid limit
        result = await get_task_logs(
            ctx=mock_context,
            run_id='run-12345',
            task_id='task-67890',
            start_time=None,
            end_time=None,
            limit=10000,  # Maximum valid
            next_token=None,
            start_from_head=True,
        )
        assert 'events' in result


class TestNormalizeRunIds:
    """Test cases for the _normalize_run_ids function."""

    def test_normalize_list_input(self):
        """Test that list input is returned as-is."""
        input_list = ['run1', 'run2', 'run3']
        result = _normalize_run_ids(input_list)
        assert result == input_list

    def test_normalize_json_string_input(self):
        """Test that JSON string input is parsed correctly."""
        input_json = '["run1", "run2", "run3"]'
        result = _normalize_run_ids(input_json)
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_single_json_string(self):
        """Test that single item JSON string is handled."""
        input_json = '"run1"'
        result = _normalize_run_ids(input_json)
        assert result == ['run1']

    def test_normalize_comma_separated_string(self):
        """Test that comma-separated string is parsed correctly."""
        input_csv = 'run1,run2,run3'
        result = _normalize_run_ids(input_csv)
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_comma_separated_with_spaces(self):
        """Test that comma-separated string with spaces is handled."""
        input_csv = 'run1, run2 , run3'
        result = _normalize_run_ids(input_csv)
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_single_string(self):
        """Test that single string is converted to list."""
        input_str = 'run1'
        result = _normalize_run_ids(input_str)
        assert result == ['run1']

    def test_normalize_empty_string(self):
        """Test that empty string returns empty list."""
        input_str = ''
        result = _normalize_run_ids(input_str)
        assert result == ['']

    def test_normalize_invalid_json(self):
        """Test that invalid JSON falls back to string parsing."""
        input_str = '["run1", "run2"'  # Invalid JSON
        result = _normalize_run_ids(input_str)
        # Since it contains comma, it's treated as comma-separated
        assert result == ['["run1"', '"run2"']

    def test_normalize_invalid_json_no_comma(self):
        """Test that invalid JSON without comma is treated as single string."""
        input_str = '{"run1"'  # Invalid JSON without comma
        result = _normalize_run_ids(input_str)
        assert result == ['{"run1"']

    def test_normalize_mixed_types_in_json(self):
        """Test that mixed types in JSON are converted to strings."""
        input_json = '[123, "run2", 456]'
        result = _normalize_run_ids(input_json)
        assert result == ['123', 'run2', '456']
