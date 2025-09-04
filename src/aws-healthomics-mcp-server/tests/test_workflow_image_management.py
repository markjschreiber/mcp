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

"""Unit tests for workflow image management tools."""

import json
import pytest
from awslabs.aws_healthomics_mcp_server.tools.workflow_image_management import (
    _check_image_exists,
    _check_policy_compliance,
    _check_repository_exists,
    _create_ecr_client_for_region,
    _parse_ecr_uri,
    _verify_single_image,
    verify_container_images_for_omics,
)
from unittest.mock import AsyncMock, MagicMock, patch


class TestParseEcrUri:
    """Test ECR URI parsing functionality."""

    def test_parse_valid_uri_with_tag(self):
        """Test parsing valid ECR URI with tag."""
        uri = '123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:latest'
        result = _parse_ecr_uri(uri)

        assert result is not None
        assert result['account_id'] == '123456789012'
        assert result['region'] == 'us-east-1'
        assert result['repository_name'] == 'my-repo'
        assert result['tag'] == 'latest'

    def test_parse_valid_uri_without_tag(self):
        """Test parsing valid ECR URI without tag (defaults to latest)."""
        uri = '123456789012.dkr.ecr.us-west-2.amazonaws.com/my-repo'
        result = _parse_ecr_uri(uri)

        assert result is not None
        assert result['account_id'] == '123456789012'
        assert result['region'] == 'us-west-2'
        assert result['repository_name'] == 'my-repo'
        assert result['tag'] == 'latest'

    def test_parse_uri_with_complex_repo_name(self):
        """Test parsing ECR URI with complex repository name."""
        uri = '123456789012.dkr.ecr.eu-west-1.amazonaws.com/namespace/my-app:v1.2.3'
        result = _parse_ecr_uri(uri)

        assert result is not None
        assert result['account_id'] == '123456789012'
        assert result['region'] == 'eu-west-1'
        assert result['repository_name'] == 'namespace/my-app'
        assert result['tag'] == 'v1.2.3'

    def test_parse_invalid_uri_format(self):
        """Test parsing invalid URI format."""
        invalid_uris = [
            'invalid-uri',
            'docker.io/library/ubuntu:latest',
            '123456789012.dkr.ecr.amazonaws.com/repo:tag',  # Missing region
            'not-a-number.dkr.ecr.us-east-1.amazonaws.com/repo:tag',  # Invalid account ID
        ]

        for uri in invalid_uris:
            result = _parse_ecr_uri(uri)
            assert result is None


class TestEcrClientCreation:
    """Test ECR client creation functionality."""

    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_image_management.create_aws_client')
    def test_create_ecr_client_same_region(self, mock_create_client):
        """Test creating ECR client for same region."""
        mock_client = MagicMock()
        mock_client.meta.region_name = 'us-east-1'
        mock_create_client.return_value = mock_client

        result = _create_ecr_client_for_region('us-east-1')

        assert result == mock_client
        mock_create_client.assert_called_once_with('ecr')

    @patch('awslabs.aws_healthomics_mcp_server.utils.aws_utils.get_aws_session')
    @patch('awslabs.aws_healthomics_mcp_server.tools.workflow_image_management.create_aws_client')
    def test_create_ecr_client_different_region(self, mock_create_client, mock_get_session):
        """Test creating ECR client for different region."""
        mock_default_client = MagicMock()
        mock_default_client.meta.region_name = 'us-east-1'
        mock_create_client.return_value = mock_default_client

        mock_session = MagicMock()
        mock_regional_client = MagicMock()
        mock_session.client.return_value = mock_regional_client
        mock_get_session.return_value = mock_session

        result = _create_ecr_client_for_region('us-west-2')

        assert result == mock_regional_client
        mock_session.client.assert_called_once_with('ecr', region_name='us-west-2')


class TestRepositoryExists:
    """Test repository existence checking."""

    def test_repository_exists_success(self):
        """Test successful repository existence check."""
        mock_client = MagicMock()
        mock_client.describe_repositories.return_value = {
            'repositories': [{'repositoryName': 'my-repo'}]
        }

        result = _check_repository_exists(mock_client, 'my-repo')

        assert result is True
        mock_client.describe_repositories.assert_called_once_with(repositoryNames=['my-repo'])

    def test_repository_not_found(self):
        """Test repository not found."""
        mock_client = MagicMock()
        mock_client.exceptions.RepositoryNotFoundException = Exception
        mock_client.describe_repositories.side_effect = Exception()

        result = _check_repository_exists(mock_client, 'nonexistent-repo')

        assert result is False


class TestImageExists:
    """Test image existence checking."""

    def test_image_exists_success(self):
        """Test successful image existence check."""
        mock_client = MagicMock()
        mock_client.describe_images.return_value = {
            'imageDetails': [{'imageDigest': 'sha256:abc123', 'imageTags': ['latest']}]
        }

        result = _check_image_exists(mock_client, 'my-repo', 'latest')

        assert result is True
        mock_client.describe_images.assert_called_once_with(
            repositoryName='my-repo', imageIds=[{'imageTag': 'latest'}]
        )

    def test_image_not_found(self):
        """Test image not found."""
        mock_client = MagicMock()
        mock_client.exceptions.ImageNotFoundException = Exception
        mock_client.describe_images.side_effect = Exception()

        result = _check_image_exists(mock_client, 'my-repo', 'nonexistent-tag')

        assert result is False

    def test_image_exists_empty_details(self):
        """Test image exists check with empty image details."""
        mock_client = MagicMock()
        mock_client.describe_images.return_value = {'imageDetails': []}

        result = _check_image_exists(mock_client, 'my-repo', 'latest')

        assert result is False


class TestPolicyCompliance:
    """Test policy compliance checking."""

    def test_policy_compliance_success(self):
        """Test successful policy compliance check."""
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': {'Service': 'omics.amazonaws.com'},
                    'Action': [
                        'ecr:BatchGetImage',
                        'ecr:GetDownloadUrlForLayer',
                    ],
                }
            ],
        }

        mock_client = MagicMock()
        mock_client.get_repository_policy.return_value = {
            'policyText': json.dumps(policy_document)
        }

        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]

        result = _check_policy_compliance(
            mock_client, 'my-repo', required_actions, 'omics.amazonaws.com'
        )

        assert result['accessible_to_omics'] is True
        assert result['policy_compliant'] is True
        assert result['has_policy'] is True

    def test_policy_compliance_missing_actions(self):
        """Test policy compliance with missing actions."""
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': {'Service': 'omics.amazonaws.com'},
                    'Action': ['ecr:BatchGetImage'],  # Missing other actions
                }
            ],
        }

        mock_client = MagicMock()
        mock_client.get_repository_policy.return_value = {
            'policyText': json.dumps(policy_document)
        }

        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]

        result = _check_policy_compliance(
            mock_client, 'my-repo', required_actions, 'omics.amazonaws.com'
        )

        assert result['accessible_to_omics'] is True
        assert result['policy_compliant'] is False
        assert result['has_policy'] is True

    def test_policy_compliance_wrong_principal(self):
        """Test policy compliance with wrong principal."""
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': {'Service': 'lambda.amazonaws.com'},  # Wrong service
                    'Action': [
                        'ecr:BatchGetImage',
                        'ecr:GetDownloadUrlForLayer',
                    ],
                }
            ],
        }

        mock_client = MagicMock()
        mock_client.get_repository_policy.return_value = {
            'policyText': json.dumps(policy_document)
        }

        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]

        result = _check_policy_compliance(
            mock_client, 'my-repo', required_actions, 'omics.amazonaws.com'
        )

        assert result['accessible_to_omics'] is False
        assert result['policy_compliant'] is False
        assert result['has_policy'] is True

    def test_policy_compliance_wildcard_actions(self):
        """Test policy compliance with wildcard actions."""
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': {'Service': 'omics.amazonaws.com'},
                    'Action': 'ecr:*',  # Wildcard action
                }
            ],
        }

        mock_client = MagicMock()
        mock_client.get_repository_policy.return_value = {
            'policyText': json.dumps(policy_document)
        }

        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]

        result = _check_policy_compliance(
            mock_client, 'my-repo', required_actions, 'omics.amazonaws.com'
        )

        assert result['accessible_to_omics'] is True
        assert result['policy_compliant'] is True
        assert result['has_policy'] is True

    def test_policy_compliance_no_policy(self):
        """Test policy compliance when no policy exists."""
        mock_client = MagicMock()
        mock_client.exceptions.RepositoryPolicyNotFoundException = Exception
        mock_client.get_repository_policy.side_effect = Exception()

        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]

        result = _check_policy_compliance(
            mock_client, 'my-repo', required_actions, 'omics.amazonaws.com'
        )

        assert result['accessible_to_omics'] is False
        assert result['policy_compliant'] is False
        assert result['has_policy'] is False


class TestVerifySingleImage:
    """Test single image verification."""

    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._check_policy_compliance'
    )
    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._check_image_exists'
    )
    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._check_repository_exists'
    )
    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    )
    def test_verify_single_image_success(
        self, mock_create_client, mock_repo_exists, mock_image_exists, mock_policy_check
    ):
        """Test successful single image verification."""
        # Setup mocks
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_repo_exists.return_value = True
        mock_image_exists.return_value = True
        mock_policy_check.return_value = {
            'accessible_to_omics': True,
            'policy_compliant': True,
            'has_policy': True,
        }

        uri = '123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:latest'
        required_actions = [
            'ecr:BatchGetImage',
            'ecr:GetDownloadUrlForLayer',
        ]
        omics_principal = 'omics.amazonaws.com'

        result = _verify_single_image(uri, required_actions, omics_principal)

        # Verify result
        assert result['uri'] == uri
        assert result['exists'] is True
        assert result['accessible_to_omics'] is True
        assert result['policy_compliant'] is True
        assert len(result['errors']) == 0
        assert len(result['warnings']) == 0

        # Verify function calls
        mock_create_client.assert_called_once_with('us-east-1')
        mock_repo_exists.assert_called_once_with(mock_client, 'my-repo')
        mock_image_exists.assert_called_once_with(mock_client, 'my-repo', 'latest')
        mock_policy_check.assert_called_once_with(
            mock_client, 'my-repo', required_actions, omics_principal
        )

    def test_verify_single_image_invalid_uri(self):
        """Test single image verification with invalid URI."""
        uri = 'invalid-uri-format'
        required_actions = ['ecr:BatchGetImage']
        omics_principal = 'omics.amazonaws.com'

        result = _verify_single_image(uri, required_actions, omics_principal)

        assert result['uri'] == uri
        assert result['exists'] is False
        assert result['accessible_to_omics'] is False
        assert result['policy_compliant'] is False
        assert len(result['errors']) == 1
        assert 'Invalid ECR URI format' in result['errors'][0]

    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    )
    def test_verify_single_image_client_error(self, mock_create_client):
        """Test single image verification with client creation error."""
        mock_create_client.side_effect = Exception('Client creation failed')

        uri = '123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:latest'
        required_actions = ['ecr:BatchGetImage']
        omics_principal = 'omics.amazonaws.com'

        result = _verify_single_image(uri, required_actions, omics_principal)

        assert result['exists'] is False
        assert len(result['errors']) == 1
        assert 'Failed to create ECR client' in result['errors'][0]

    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._check_repository_exists'
    )
    @patch(
        'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._create_ecr_client_for_region'
    )
    def test_verify_single_image_repo_not_found(self, mock_create_client, mock_repo_exists):
        """Test single image verification with repository not found."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_repo_exists.return_value = False

        uri = '123456789012.dkr.ecr.us-east-1.amazonaws.com/nonexistent-repo:latest'
        required_actions = ['ecr:BatchGetImage']
        omics_principal = 'omics.amazonaws.com'

        result = _verify_single_image(uri, required_actions, omics_principal)

        assert result['exists'] is False
        assert len(result['errors']) == 1
        assert 'Repository nonexistent-repo not found' in result['errors'][0]


class TestVerifyContainerImagesForOmics:
    """Test main container image verification function."""

    @pytest.mark.asyncio
    async def test_verify_container_images_single_string(self):
        """Test verification with single image URI string."""
        mock_ctx = AsyncMock()

        with patch(
            'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._verify_single_image'
        ) as mock_verify:
            mock_verify.return_value = {
                'uri': 'test-uri',
                'exists': True,
                'accessible_to_omics': True,
                'policy_compliant': True,
                'errors': [],
                'warnings': [],
            }

            result = await verify_container_images_for_omics(mock_ctx, 'test-uri')

            assert result['total_images_checked'] == 1
            assert result['existing_images'] == 1
            assert result['accessible_to_omics'] == 1
            assert 'test-uri' in result['verification_results']

    @pytest.mark.asyncio
    async def test_verify_container_images_list(self):
        """Test verification with list of image URIs."""
        mock_ctx = AsyncMock()

        uris = ['uri1', 'uri2', 'uri3']

        def mock_verify_side_effect(uri, *args):
            return {
                'uri': uri,
                'exists': True,
                'accessible_to_omics': uri != 'uri2',  # uri2 not accessible
                'policy_compliant': uri != 'uri2',
                'errors': [],
                'warnings': [],
            }

        with patch(
            'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._verify_single_image'
        ) as mock_verify:
            mock_verify.side_effect = mock_verify_side_effect

            result = await verify_container_images_for_omics(mock_ctx, uris)

            assert result['total_images_checked'] == 3
            assert result['existing_images'] == 3
            assert result['accessible_to_omics'] == 2  # uri2 not accessible
            assert len(result['verification_results']) == 3

    @pytest.mark.asyncio
    async def test_verify_container_images_empty_list(self):
        """Test verification with empty list."""
        mock_ctx = AsyncMock()

        with pytest.raises(ValueError, match='No image URIs provided'):
            await verify_container_images_for_omics(mock_ctx, [])

        mock_ctx.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_container_images_with_exception(self):
        """Test verification with exception during processing."""
        mock_ctx = AsyncMock()

        with patch(
            'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._verify_single_image'
        ) as mock_verify:
            mock_verify.side_effect = Exception('Verification failed')

            result = await verify_container_images_for_omics(mock_ctx, 'test-uri')

            assert result['total_images_checked'] == 1
            assert result['existing_images'] == 0
            assert result['accessible_to_omics'] == 0

            # Check error was captured
            verification_result = result['verification_results']['test-uri']
            assert len(verification_result['errors']) == 1
            assert 'Unexpected error verifying' in verification_result['errors'][0]

    @pytest.mark.asyncio
    async def test_verify_container_images_mixed_results(self):
        """Test verification with mixed success/failure results."""
        mock_ctx = AsyncMock()

        uris = ['good-uri', 'bad-uri', 'no-policy-uri']

        def mock_verify_side_effect(uri, *args):
            if uri == 'good-uri':
                return {
                    'uri': uri,
                    'exists': True,
                    'accessible_to_omics': True,
                    'policy_compliant': True,
                    'errors': [],
                    'warnings': [],
                }
            elif uri == 'bad-uri':
                return {
                    'uri': uri,
                    'exists': False,
                    'accessible_to_omics': False,
                    'policy_compliant': False,
                    'errors': ['Repository not found'],
                    'warnings': [],
                }
            else:  # no-policy-uri
                return {
                    'uri': uri,
                    'exists': True,
                    'accessible_to_omics': False,
                    'policy_compliant': False,
                    'errors': [],
                    'warnings': ['No repository policy found'],
                }

        with patch(
            'awslabs.aws_healthomics_mcp_server.tools.workflow_image_management._verify_single_image'
        ) as mock_verify:
            mock_verify.side_effect = mock_verify_side_effect

            result = await verify_container_images_for_omics(mock_ctx, uris)

            assert result['total_images_checked'] == 3
            assert result['existing_images'] == 2  # good-uri and no-policy-uri exist
            assert result['accessible_to_omics'] == 1  # only good-uri is accessible

            # Check individual results
            assert result['verification_results']['good-uri']['exists'] is True
            assert result['verification_results']['bad-uri']['exists'] is False
            assert result['verification_results']['no-policy-uri']['exists'] is True
            assert len(result['verification_results']['no-policy-uri']['warnings']) == 1
