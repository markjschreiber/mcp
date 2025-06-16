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

"""Tests for run analysis tools."""

from awslabs.aws_healthomics_mcp_server.tools.run_analysis import (
    _convert_datetime_to_string,
    _normalize_run_ids,
    _safe_json_dumps,
)
from datetime import datetime


class TestNormalizeRunIds:
    """Test the _normalize_run_ids function."""

    def test_normalize_run_ids_list(self):
        """Test normalizing a list of run IDs."""
        # Arrange
        run_ids = ['run1', 'run2', 'run3']

        # Act
        result = _normalize_run_ids(run_ids)

        # Assert
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_run_ids_json_string(self):
        """Test normalizing a JSON string of run IDs."""
        # Arrange
        run_ids = '["run1", "run2", "run3"]'

        # Act
        result = _normalize_run_ids(run_ids)

        # Assert
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_run_ids_comma_separated(self):
        """Test normalizing a comma-separated string of run IDs."""
        # Arrange
        run_ids = 'run1,run2,run3'

        # Act
        result = _normalize_run_ids(run_ids)

        # Assert
        assert result == ['run1', 'run2', 'run3']

    def test_normalize_run_ids_single_string(self):
        """Test normalizing a single run ID string."""
        # Arrange
        run_ids = 'run1'

        # Act
        result = _normalize_run_ids(run_ids)

        # Assert
        assert result == ['run1']

    def test_normalize_run_ids_with_spaces(self):
        """Test normalizing comma-separated string with spaces."""
        # Arrange
        run_ids = 'run1, run2 , run3'

        # Act
        result = _normalize_run_ids(run_ids)

        # Assert
        assert result == ['run1', 'run2', 'run3']


class TestConvertDatetimeToString:
    """Test the _convert_datetime_to_string function."""

    def test_convert_datetime_object(self):
        """Test converting a datetime object."""
        # Arrange
        dt = datetime(2023, 1, 1, 12, 0, 0)

        # Act
        result = _convert_datetime_to_string(dt)

        # Assert
        assert result == '2023-01-01T12:00:00'

    def test_convert_dict_with_datetime(self):
        """Test converting a dictionary containing datetime objects."""
        # Arrange
        data = {'timestamp': datetime(2023, 1, 1, 12, 0, 0), 'name': 'test', 'count': 42}

        # Act
        result = _convert_datetime_to_string(data)

        # Assert
        expected = {'timestamp': '2023-01-01T12:00:00', 'name': 'test', 'count': 42}
        assert result == expected

    def test_convert_list_with_datetime(self):
        """Test converting a list containing datetime objects."""
        # Arrange
        data = [datetime(2023, 1, 1, 12, 0, 0), 'test', 42]

        # Act
        result = _convert_datetime_to_string(data)

        # Assert
        expected = ['2023-01-01T12:00:00', 'test', 42]
        assert result == expected

    def test_convert_non_datetime_object(self):
        """Test converting non-datetime objects."""
        # Arrange
        data = 'test string'

        # Act
        result = _convert_datetime_to_string(data)

        # Assert
        assert result == 'test string'


class TestSafeJsonDumps:
    """Test the _safe_json_dumps function."""

    def test_safe_json_dumps_with_datetime(self):
        """Test JSON serialization with datetime objects."""
        # Arrange
        data = {'timestamp': datetime(2023, 1, 1, 12, 0, 0), 'name': 'test'}

        # Act
        result = _safe_json_dumps(data)

        # Assert
        assert '"timestamp": "2023-01-01T12:00:00"' in result
        assert '"name": "test"' in result

    def test_safe_json_dumps_regular_data(self):
        """Test JSON serialization with regular data."""
        # Arrange
        data = {'name': 'test', 'count': 42}

        # Act
        result = _safe_json_dumps(data)

        # Assert
        assert '"name": "test"' in result
        assert '"count": 42' in result
