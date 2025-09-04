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

"""Unit tests for helper tools."""

import pytest
from awslabs.aws_healthomics_mcp_server.consts import HEALTHOMICS_SUPPORTED_REGIONS
from awslabs.aws_healthomics_mcp_server.tools.helper_tools import get_supported_regions
from botocore.exceptions import BotoCoreError, ClientError
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_supported_regions_success():
    """Test successful retrieval of regions from SSM."""
    # Mock SSM response
    mock_ssm_response = {
        'Parameters': [
            {'Value': 'us-east-1'},
            {'Value': 'us-west-2'},
            {'Value': 'eu-west-1'},
        ]
    }

    # Mock context and SSM client
    mock_ctx = AsyncMock()
    mock_ssm = MagicMock()
    mock_ssm.get_parameters_by_path.return_value = mock_ssm_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.get_ssm_client',
        return_value=mock_ssm,
    ):
        result = await get_supported_regions(mock_ctx)

    # Verify results
    assert result['count'] == 3
    assert result['regions'] == ['eu-west-1', 'us-east-1', 'us-west-2']
    assert 'note' not in result

    # Verify SSM was called correctly
    mock_ssm.get_parameters_by_path.assert_called_once_with(
        Path='/aws/service/global-infrastructure/services/omics/regions'
    )


@pytest.mark.asyncio
async def test_get_supported_regions_empty_ssm():
    """Test fallback to hardcoded regions when SSM returns empty list."""
    # Mock SSM response with no parameters
    mock_ssm_response = {'Parameters': []}

    # Mock context and SSM client
    mock_ctx = AsyncMock()
    mock_ssm = MagicMock()
    mock_ssm.get_parameters_by_path.return_value = mock_ssm_response

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.get_ssm_client',
        return_value=mock_ssm,
    ):
        result = await get_supported_regions(mock_ctx)

    # Verify fallback to hardcoded regions
    assert result['count'] == len(HEALTHOMICS_SUPPORTED_REGIONS)
    assert result['regions'] == sorted(HEALTHOMICS_SUPPORTED_REGIONS)
    assert 'note' not in result


@pytest.mark.asyncio
async def test_get_supported_regions_boto_error():
    """Test handling of BotoCoreError."""
    # Mock context and SSM client
    mock_ctx = AsyncMock()
    mock_ssm = MagicMock()
    mock_ssm.get_parameters_by_path.side_effect = BotoCoreError()

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.get_ssm_client',
        return_value=mock_ssm,
    ):
        result = await get_supported_regions(mock_ctx)

    # Verify fallback to hardcoded regions with note
    assert result['count'] == len(HEALTHOMICS_SUPPORTED_REGIONS)
    assert result['regions'] == sorted(HEALTHOMICS_SUPPORTED_REGIONS)
    assert 'note' in result
    assert 'Using hardcoded region list due to error:' in result['note']


@pytest.mark.asyncio
async def test_get_supported_regions_client_error():
    """Test handling of ClientError."""
    # Mock context and SSM client
    mock_ctx = AsyncMock()
    mock_ssm = MagicMock()
    mock_ssm.get_parameters_by_path.side_effect = ClientError(
        {'Error': {'Code': 'InvalidParameter', 'Message': 'Test error'}}, 'GetParametersByPath'
    )

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.get_ssm_client',
        return_value=mock_ssm,
    ):
        result = await get_supported_regions(mock_ctx)

    # Verify fallback to hardcoded regions with note
    assert result['count'] == len(HEALTHOMICS_SUPPORTED_REGIONS)
    assert result['regions'] == sorted(HEALTHOMICS_SUPPORTED_REGIONS)
    assert 'note' in result
    assert 'Using hardcoded region list due to error:' in result['note']


@pytest.mark.asyncio
async def test_get_supported_regions_unexpected_error():
    """Test handling of unexpected errors."""
    # Mock context and SSM client
    mock_ctx = AsyncMock()
    mock_ssm = MagicMock()
    mock_ssm.get_parameters_by_path.side_effect = Exception('Unexpected error')

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.get_ssm_client',
        return_value=mock_ssm,
    ):
        result = await get_supported_regions(mock_ctx)

    # Verify fallback to hardcoded regions with note
    assert result['count'] == len(HEALTHOMICS_SUPPORTED_REGIONS)
    assert result['regions'] == sorted(HEALTHOMICS_SUPPORTED_REGIONS)
    assert 'note' in result
    assert 'Using hardcoded region list due to error:' in result['note']

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Unexpected error retrieving supported regions' in mock_ctx.error.call_args[0][0]


@pytest.mark.asyncio
async def test_generate_ecr_repository_policy_for_omics_basic():
    """Test basic ECR policy generation for HealthOmics."""
    from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
        generate_ecr_repository_policy_for_omics,
    )

    mock_ctx = AsyncMock()

    result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=None, include_cross_account_access=False
    )

    # Verify basic structure
    assert 'policy_document' in result
    assert 'policy_json' in result
    assert 'usage_instructions' in result
    assert 'required_actions' in result
    assert 'principals_included' in result

    # Verify policy document structure
    policy_doc = result['policy_document']
    assert policy_doc['Version'] == '2012-10-17'
    assert len(policy_doc['Statement']) == 1

    # Verify HealthOmics statement
    omics_statement = policy_doc['Statement'][0]
    assert omics_statement['Sid'] == 'AllowHealthOmicsAccess'
    assert omics_statement['Effect'] == 'Allow'
    assert omics_statement['Principal']['Service'] == 'omics.amazonaws.com'

    # Verify required actions
    expected_actions = [
        'ecr:GetDownloadUrlForLayer',
        'ecr:BatchGetImage',
        'ecr:BatchCheckLayerAvailability',
    ]
    assert omics_statement['Action'] == expected_actions
    assert result['required_actions'] == expected_actions

    # Verify principals
    assert result['principals_included'] == ['omics.amazonaws.com']

    # Verify usage instructions
    assert len(result['usage_instructions']) > 0
    assert any(
        'aws ecr set-repository-policy' in instruction
        for instruction in result['usage_instructions']
    )


@pytest.mark.asyncio
async def test_generate_ecr_repository_policy_with_additional_principals():
    """Test ECR policy generation with additional principals."""
    from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
        generate_ecr_repository_policy_for_omics,
    )

    mock_ctx = AsyncMock()

    additional_principals = [
        '123456789012',  # Account ID
        'arn:aws:iam::123456789012:role/MyRole',  # IAM role ARN
        'lambda.amazonaws.com',  # Service principal
    ]

    result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx,
        additional_principals=additional_principals,
        include_cross_account_access=False,
    )

    # Verify policy document has additional statement
    policy_doc = result['policy_document']
    assert len(policy_doc['Statement']) == 2

    # Find the additional principals statement
    additional_statement = None
    for statement in policy_doc['Statement']:
        if statement.get('Sid') == 'AllowAdditionalPrincipals':
            additional_statement = statement
            break

    assert additional_statement is not None
    assert additional_statement['Effect'] == 'Allow'

    # Verify AWS principals (account ID converted to root ARN, IAM role ARN)
    expected_aws_principals = [
        'arn:aws:iam::123456789012:root',
        'arn:aws:iam::123456789012:role/MyRole',
    ]
    assert additional_statement['Principal']['AWS'] == expected_aws_principals

    # Verify service principals
    assert additional_statement['Principal']['Service'] == ['lambda.amazonaws.com']

    # Verify principals included list
    expected_principals = ['omics.amazonaws.com'] + additional_principals
    assert result['principals_included'] == expected_principals


@pytest.mark.asyncio
async def test_generate_ecr_repository_policy_with_cross_account():
    """Test ECR policy generation with cross-account access."""
    from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
        generate_ecr_repository_policy_for_omics,
    )

    mock_ctx = AsyncMock()

    result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=None, include_cross_account_access=True
    )

    # Verify policy document has cross-account statement
    policy_doc = result['policy_document']
    assert len(policy_doc['Statement']) == 2

    # Find the cross-account statement
    cross_account_statement = None
    for statement in policy_doc['Statement']:
        if statement.get('Sid') == 'AllowCrossAccountAccess':
            cross_account_statement = statement
            break

    assert cross_account_statement is not None
    assert cross_account_statement['Effect'] == 'Allow'
    assert cross_account_statement['Principal'] == '*'

    # Verify condition
    assert 'Condition' in cross_account_statement
    condition = cross_account_statement['Condition']
    assert 'StringEquals' in condition
    assert condition['StringEquals']['aws:PrincipalServiceName'] == 'omics.amazonaws.com'


@pytest.mark.asyncio
async def test_generate_ecr_repository_policy_complete():
    """Test ECR policy generation with all options."""
    from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
        generate_ecr_repository_policy_for_omics,
    )

    mock_ctx = AsyncMock()

    additional_principals = ['123456789012', 'batch.amazonaws.com']

    result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx,
        additional_principals=additional_principals,
        include_cross_account_access=True,
    )

    # Verify policy document has all three statements
    policy_doc = result['policy_document']
    assert len(policy_doc['Statement']) == 3

    # Verify all statement SIDs are present
    sids = [statement['Sid'] for statement in policy_doc['Statement']]
    expected_sids = [
        'AllowHealthOmicsAccess',
        'AllowAdditionalPrincipals',
        'AllowCrossAccountAccess',
    ]
    assert all(sid in sids for sid in expected_sids)

    # Verify policy JSON is valid
    import json

    parsed_policy = json.loads(result['policy_json'])
    assert parsed_policy == policy_doc


@pytest.mark.asyncio
async def test_generate_ecr_repository_policy_error():
    """Test error handling in ECR policy generation."""
    from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
        generate_ecr_repository_policy_for_omics,
    )

    mock_ctx = AsyncMock()

    # Mock json.dumps to raise an exception
    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.helper_tools.json.dumps',
        side_effect=Exception('JSON error'),
    ):
        with pytest.raises(Exception, match='JSON error'):
            await generate_ecr_repository_policy_for_omics(
                ctx=mock_ctx, additional_principals=None, include_cross_account_access=False
            )

    # Verify error was reported to context
    mock_ctx.error.assert_called_once()
    assert 'Error generating ECR policy' in mock_ctx.error.call_args[0][0]
