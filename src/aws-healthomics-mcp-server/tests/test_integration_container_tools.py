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

"""Integration tests for container image management tools."""

import json
import pytest
from awslabs.aws_healthomics_mcp_server.tools.helper_tools import (
    generate_ecr_repository_policy_for_omics,
)
from awslabs.aws_healthomics_mcp_server.tools.workflow_image_management import (
    verify_container_images_for_omics,
)
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_integration_policy_generation_and_verification():
    """Test integration between policy generation and image verification."""
    mock_ctx = AsyncMock()

    # Step 1: Generate a policy for HealthOmics
    policy_result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=['123456789012'], include_cross_account_access=False
    )

    # Verify policy was generated correctly
    assert 'policy_document' in policy_result
    policy_doc = policy_result['policy_document']

    # Step 2: Mock ECR client to simulate repository with the generated policy
    mock_ecr_client = MagicMock()

    # Mock repository exists
    mock_ecr_client.describe_repositories.return_value = {
        'repositories': [{'repositoryName': 'my-repo'}]
    }

    # Mock image exists
    mock_ecr_client.describe_images.return_value = {
        'imageDetails': [{'imageDigest': 'sha256:abc123', 'imageTags': ['latest']}]
    }

    # Mock repository policy with the generated policy
    mock_ecr_client.get_repository_policy.return_value = {'policyText': json.dumps(policy_doc)}

    # Step 3: Verify the image with the generated policy
    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    ) as mock_create_client:
        mock_create_client.return_value = mock_ecr_client

        verification_result = await verify_container_images_for_omics(
            ctx=mock_ctx, image_uris='123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:latest'
        )

    # Verify the image verification succeeded
    assert verification_result['total_images_checked'] == 1
    assert verification_result['existing_images'] == 1
    assert verification_result['accessible_to_omics'] == 1

    # Check specific verification details
    uri = '123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:latest'
    image_result = verification_result['verification_results'][uri]

    assert image_result['exists'] is True
    assert image_result['accessible_to_omics'] is True
    assert image_result['policy_compliant'] is True
    assert len(image_result['errors']) == 0


@pytest.mark.asyncio
async def test_integration_policy_generation_with_cross_account():
    """Test policy generation with cross-account access and verification."""
    mock_ctx = AsyncMock()

    # Generate policy with cross-account access
    policy_result = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=None, include_cross_account_access=True
    )

    # Verify cross-account statement exists
    policy_doc = policy_result['policy_document']
    cross_account_statement = None
    for statement in policy_doc['Statement']:
        if statement.get('Sid') == 'AllowCrossAccountAccess':
            cross_account_statement = statement
            break

    assert cross_account_statement is not None
    assert cross_account_statement['Principal'] == '*'
    assert 'Condition' in cross_account_statement

    # Mock verification with this policy
    mock_ecr_client = MagicMock()
    mock_ecr_client.describe_repositories.return_value = {
        'repositories': [{'repositoryName': 'cross-account-repo'}]
    }
    mock_ecr_client.describe_images.return_value = {
        'imageDetails': [{'imageDigest': 'sha256:def456'}]
    }
    mock_ecr_client.get_repository_policy.return_value = {'policyText': json.dumps(policy_doc)}

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    ) as mock_create_client:
        mock_create_client.return_value = mock_ecr_client

        verification_result = await verify_container_images_for_omics(
            ctx=mock_ctx,
            image_uris='987654321098.dkr.ecr.eu-west-1.amazonaws.com/cross-account-repo:v1.0',
        )

    # Verify cross-account access works
    assert verification_result['accessible_to_omics'] == 1

    uri = '987654321098.dkr.ecr.eu-west-1.amazonaws.com/cross-account-repo:v1.0'
    image_result = verification_result['verification_results'][uri]
    assert image_result['policy_compliant'] is True


@pytest.mark.asyncio
async def test_integration_policy_mismatch_detection():
    """Test that verification correctly detects policy mismatches."""
    mock_ctx = AsyncMock()

    # Generate a policy for HealthOmics (not used in this test, just ensuring it works)
    await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=None, include_cross_account_access=False
    )

    # Create a different policy that doesn't allow HealthOmics access
    wrong_policy = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Principal': {'Service': 'lambda.amazonaws.com'},  # Wrong service
                'Action': [
                    'ecr:GetDownloadUrlForLayer',
                    'ecr:BatchGetImage',
                    'ecr:BatchCheckLayerAvailability',
                ],
            }
        ],
    }

    # Mock ECR client with the wrong policy
    mock_ecr_client = MagicMock()
    mock_ecr_client.describe_repositories.return_value = {
        'repositories': [{'repositoryName': 'wrong-policy-repo'}]
    }
    mock_ecr_client.describe_images.return_value = {
        'imageDetails': [{'imageDigest': 'sha256:ghi789'}]
    }
    mock_ecr_client.get_repository_policy.return_value = {'policyText': json.dumps(wrong_policy)}

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    ) as mock_create_client:
        mock_create_client.return_value = mock_ecr_client

        verification_result = await verify_container_images_for_omics(
            ctx=mock_ctx,
            image_uris='123456789012.dkr.ecr.us-west-2.amazonaws.com/wrong-policy-repo:latest',
        )

    # Verify the policy mismatch is detected
    assert (
        verification_result['accessible_to_omics'] == 0
    )  # Should be 0 because policy doesn't allow HealthOmics

    uri = '123456789012.dkr.ecr.us-west-2.amazonaws.com/wrong-policy-repo:latest'
    image_result = verification_result['verification_results'][uri]

    assert image_result['exists'] is True
    assert image_result['accessible_to_omics'] is False
    assert image_result['policy_compliant'] is False
    assert len(image_result['warnings']) > 0
    assert any(
        'does not grant access to omics.amazonaws.com' in warning
        for warning in image_result['warnings']
    )


@pytest.mark.asyncio
async def test_integration_multiple_images_with_generated_policies():
    """Test verification of multiple images with different policy configurations."""
    mock_ctx = AsyncMock()

    # Generate different policies
    basic_policy = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=None, include_cross_account_access=False
    )

    cross_account_policy = await generate_ecr_repository_policy_for_omics(
        ctx=mock_ctx, additional_principals=['999888777666'], include_cross_account_access=True
    )

    # Mock different ECR clients for different regions/repositories
    def mock_create_client_side_effect(region):
        mock_client = MagicMock()
        mock_client.describe_repositories.return_value = {
            'repositories': [{'repositoryName': 'test-repo'}]
        }
        mock_client.describe_images.return_value = {
            'imageDetails': [{'imageDigest': 'sha256:test'}]
        }

        if region == 'us-east-1':
            # First repo has basic policy
            mock_client.get_repository_policy.return_value = {
                'policyText': json.dumps(basic_policy['policy_document'])
            }
        elif region == 'eu-west-1':
            # Second repo has cross-account policy
            mock_client.get_repository_policy.return_value = {
                'policyText': json.dumps(cross_account_policy['policy_document'])
            }
        else:
            # Third repo has no policy
            mock_client.exceptions.RepositoryPolicyNotFoundException = Exception
            mock_client.get_repository_policy.side_effect = Exception()

        return mock_client

    image_uris = [
        '123456789012.dkr.ecr.us-east-1.amazonaws.com/basic-repo:latest',
        '123456789012.dkr.ecr.eu-west-1.amazonaws.com/cross-account-repo:latest',
        '123456789012.dkr.ecr.ap-south-1.amazonaws.com/no-policy-repo:latest',
    ]

    with patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    ) as mock_create_client:
        mock_create_client.side_effect = mock_create_client_side_effect

        verification_result = await verify_container_images_for_omics(
            ctx=mock_ctx, image_uris=image_uris
        )

    # Verify results
    assert verification_result['total_images_checked'] == 3
    assert verification_result['existing_images'] == 3
    assert verification_result['accessible_to_omics'] == 2  # Only first two have proper policies

    # Check individual results
    results = verification_result['verification_results']

    # Basic policy repo should be accessible
    basic_result = results['123456789012.dkr.ecr.us-east-1.amazonaws.com/basic-repo:latest']
    assert basic_result['accessible_to_omics'] is True
    assert basic_result['policy_compliant'] is True

    # Cross-account policy repo should be accessible
    cross_result = results[
        '123456789012.dkr.ecr.eu-west-1.amazonaws.com/cross-account-repo:latest'
    ]
    assert cross_result['accessible_to_omics'] is True
    assert cross_result['policy_compliant'] is True

    # No policy repo should not be accessible
    no_policy_result = results[
        '123456789012.dkr.ecr.ap-south-1.amazonaws.com/no-policy-repo:latest'
    ]
    assert no_policy_result['accessible_to_omics'] is False
    assert no_policy_result['policy_compliant'] is False
    assert len(no_policy_result['warnings']) > 0
