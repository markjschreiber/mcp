# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
# and limitations under the License.
"""Tests for the aws-healthomics MCP Server."""

import pytest
from awslabs.aws_healthomics_mcp_server.server import example_tool


@pytest.mark.asyncio
async def test_example_tool():
    """Tests Basic Happy Path of example tool."""
    # Arrange
    test_query = 'test query'
    expected_project_name = 'awslabs aws-healthomics MCP Server'
    expected_response = f"Hello from {expected_project_name}! Your query was {test_query}. Replace this with your tool's logic"

    # Act
    result = await example_tool(test_query)

    # Assert
    assert result == expected_response


# @pytest.mark.asyncio
# async def test_example_tool_failure():
#     # Arrange
#     test_query = 'test query'
#     expected_project_name = 'awslabs aws-healthomics MCP Server'
#     expected_response = f"Hello from {expected_project_name}! Your query was {test_query}. Replace this your tool's new logic"

#     # Act
#     result = await example_tool(test_query)

#     # Assert
#     assert result != expected_response
