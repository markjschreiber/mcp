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

"""Workflow image management tools for the AWS HealthOmics MCP server."""

import json
import re
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import (
    create_aws_client,
)
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Any, Dict, List, Optional, Union


def _parse_ecr_uri(uri: str) -> Optional[Dict[str, str]]:
    """Parse ECR URI and return components."""
    ecr_pattern = re.compile(r'^(\d+)\.dkr\.ecr\.([^.]+)\.amazonaws\.com/([^:]+)(?::(.+))?$')
    match = ecr_pattern.match(uri)
    if not match:
        return None

    account_id, region, repository_name, tag = match.groups()
    return {
        'account_id': account_id,
        'region': region,
        'repository_name': repository_name,
        'tag': tag or 'latest',
    }


def _create_ecr_client_for_region(region: str):
    """Create ECR client for specific region."""
    ecr_client = create_aws_client('ecr')
    if region != ecr_client.meta.region_name:
        from awslabs.aws_healthomics_mcp_server.utils.aws_utils import get_aws_session

        session = get_aws_session()
        ecr_client = session.client('ecr', region_name=region)
    return ecr_client


def _check_repository_exists(ecr_client, repository_name: str) -> bool:
    """Check if ECR repository exists."""
    try:
        ecr_client.describe_repositories(repositoryNames=[repository_name])
        return True
    except ecr_client.exceptions.RepositoryNotFoundException:
        return False


def _check_image_exists(ecr_client, repository_name: str, tag: str) -> bool:
    """Check if image with specific tag exists in repository."""
    try:
        response = ecr_client.describe_images(
            repositoryName=repository_name, imageIds=[{'imageTag': tag}]
        )
        return bool(response.get('imageDetails'))
    except ecr_client.exceptions.ImageNotFoundException:
        return False


def _check_policy_compliance(
    ecr_client, repository_name: str, required_actions: List[str], omics_principal: str
) -> Dict[str, bool]:
    """Check if repository policy allows HealthOmics access."""
    try:
        policy_response = ecr_client.get_repository_policy(repositoryName=repository_name)
        policy_text = policy_response.get('policyText', '{}')
        policy = json.loads(policy_text)

        accessible_to_omics = False
        policy_compliant = False

        for statement in policy.get('Statement', []):
            if statement.get('Effect', '').upper() != 'ALLOW':
                continue

            # Normalize principals
            principals = statement.get('Principal', {})
            if isinstance(principals, str):
                principals = {'Service': [principals]}
            elif isinstance(principals, list):
                principals = {'Service': principals}

            service_principals = principals.get('Service', [])
            if isinstance(service_principals, str):
                service_principals = [service_principals]

            # Check if HealthOmics has access
            if omics_principal in service_principals or '*' in service_principals:
                accessible_to_omics = True

                # Check actions
                actions = statement.get('Action', [])
                if isinstance(actions, str):
                    actions = [actions]

                # Check if all required actions are present
                has_all_actions = all(
                    action in actions or 'ecr:*' in actions or '*' in actions
                    for action in required_actions
                )

                if has_all_actions:
                    policy_compliant = True
                    break

        result = {
            'accessible_to_omics': accessible_to_omics,
            'policy_compliant': policy_compliant,
            'has_policy': True,
        }

        # Include the actual policy when there are compliance issues
        if not policy_compliant:
            result['current_policy'] = policy_text

        return result

    except ecr_client.exceptions.RepositoryPolicyNotFoundException:
        return {'accessible_to_omics': False, 'policy_compliant': False, 'has_policy': False}


def _verify_single_image(
    uri: str, required_actions: List[str], omics_principal: str
) -> Dict[str, Any]:
    """Verify a single container image URI."""
    result = {
        'uri': uri,
        'exists': False,
        'accessible_to_omics': False,
        'policy_compliant': False,
        'errors': [],
        'warnings': [],
    }

    # Parse URI
    parsed = _parse_ecr_uri(uri)
    if not parsed:
        result['errors'].append(f'Invalid ECR URI format: {uri}')
        return result

    repository_name = parsed['repository_name']
    region = parsed['region']
    tag = parsed['tag']

    # Create ECR client
    try:
        ecr_client = _create_ecr_client_for_region(region)
    except Exception as e:
        result['errors'].append(f'Failed to create ECR client for region {region}: {str(e)}')
        return result

    # Check repository exists
    if not _check_repository_exists(ecr_client, repository_name):
        result['errors'].append(f'Repository {repository_name} not found in region {region}')
        return result

    result['exists'] = True
    logger.info(f'Repository {repository_name} exists in region {region}')

    # Check image exists
    if not _check_image_exists(ecr_client, repository_name, tag):
        result['errors'].append(f'Image with tag {tag} not found in repository {repository_name}')
        return result

    logger.info(f'Image {repository_name}:{tag} exists')

    # Check policy compliance
    try:
        policy_check = _check_policy_compliance(
            ecr_client, repository_name, required_actions, omics_principal
        )
        result['accessible_to_omics'] = policy_check['accessible_to_omics']
        result['policy_compliant'] = policy_check['policy_compliant']

        if not policy_check['has_policy']:
            result['warnings'].append(
                f'No repository policy found for {repository_name}. '
                f'HealthOmics will not be able to access this private repository. '
                f'Consider adding a policy that allows {omics_principal} to perform: {", ".join(required_actions)}'
            )
        elif not policy_check['accessible_to_omics']:
            result['warnings'].append(
                f'Repository policy does not grant access to {omics_principal}. '
                'HealthOmics may not be able to pull this image.'
            )
        elif not policy_check['policy_compliant']:
            result['warnings'].append(
                f'Repository policy grants access to {omics_principal} but missing required actions: '
                f'{", ".join(required_actions)}. HealthOmics may not be able to pull this image.'
            )
        else:
            logger.info(f'Repository {repository_name} has compliant policy for HealthOmics')

    except Exception as e:
        result['errors'].append(
            f'Error checking repository policy for {repository_name}: {str(e)}'
        )

    return result


async def verify_container_images_for_omics(
    ctx: Context,
    image_uris: Union[List[str], str] = Field(
        ...,
        description='List of container image URIs to verify, or a single URI string',
    ),
) -> Dict[str, Any]:
    """Verify that container images are accessible to AWS HealthOmics.

    This function checks that container images exist in ECR and that the repository
    has the necessary policy to allow the omics.amazonaws.com principal to perform
    required actions: ecr:GetDownloadUrlForLayer, ecr:BatchGetImage, ecr:BatchCheckLayerAvailability.

    IMPORTANT CAVEATS:
    1. Actual access will be determined at runtime and can be influenced by additional
       factors that are not checked here, such as Service Control Policies (SCPs),
       permission boundaries, and other resource-based restrictions.
    2. The permissions may not be sufficient for cross-account scenarios where additional
       trust relationships and cross-account policies may be required.
    3. This verification only checks basic ECR repository policies and does not validate
       all possible AWS IAM configurations that could affect access.

    Args:
        ctx: MCP context for error reporting
        image_uris: List of container image URIs to verify (ECR format: account.dkr.ecr.region.amazonaws.com/repo:tag)

    Returns:
        Dictionary containing verification results for each image URI
    """
    # Handle both single string and list inputs
    if isinstance(image_uris, str):
        uris_to_check = [image_uris]
    else:
        uris_to_check = image_uris

    if not uris_to_check:
        error_message = 'No image URIs provided for verification'
        logger.error(error_message)
        await ctx.error(error_message)
        raise ValueError(error_message)

    required_actions = [
        'ecr:BatchGetImage',
        'ecr:GetDownloadUrlForLayer',
    ]
    omics_principal = 'omics.amazonaws.com'

    results = {}

    for uri in uris_to_check:
        uri = uri.strip()
        try:
            result = _verify_single_image(uri, required_actions, omics_principal)
        except Exception as e:
            result = {
                'uri': uri,
                'exists': False,
                'accessible_to_omics': False,
                'policy_compliant': False,
                'errors': [f'Unexpected error verifying {uri}: {str(e)}'],
                'warnings': [],
            }
            logger.error(f'Unexpected error verifying {uri}: {str(e)}')

        results[uri] = result

    # Generate summary
    total_images = len(results)
    accessible_images = sum(
        1 for r in results.values() if r['accessible_to_omics'] and r['policy_compliant']
    )
    existing_images = sum(1 for r in results.values() if r['exists'])

    return {
        'total_images_checked': total_images,
        'existing_images': existing_images,
        'accessible_to_omics': accessible_images,
        'verification_results': results,
    }


def _check_registry_policy_compliance(ecr_client, omics_principal: str) -> Dict[str, Any]:
    """Check if registry policy allows HealthOmics to use pull through cache."""
    try:
        policy_response = ecr_client.get_registry_policy()
        policy_text = policy_response.get('policyText', '{}')
        policy = json.loads(policy_text)

        required_actions = [
            'ecr:CreateRepository',
            'ecr:BatchImportUpstreamImage',
        ]

        accessible_to_omics = False
        policy_compliant = False

        for statement in policy.get('Statement', []):
            if statement.get('Effect', '').upper() != 'ALLOW':
                continue

            # Normalize principals
            principals = statement.get('Principal', {})
            if isinstance(principals, str):
                principals = {'Service': [principals]}
            elif isinstance(principals, list):
                principals = {'Service': principals}

            service_principals = principals.get('Service', [])
            if isinstance(service_principals, str):
                service_principals = [service_principals]

            # Check if HealthOmics has access
            if omics_principal in service_principals or '*' in service_principals:
                accessible_to_omics = True

                # Check actions
                actions = statement.get('Action', [])
                if isinstance(actions, str):
                    actions = [actions]

                # Check if all required actions are present
                has_all_actions = all(
                    action in actions or 'ecr:*' in actions or '*' in actions
                    for action in required_actions
                )

                if has_all_actions:
                    policy_compliant = True
                    break

        result = {
            'accessible_to_omics': accessible_to_omics,
            'policy_compliant': policy_compliant,
            'has_policy': True,
            'required_actions': required_actions,
        }

        # Include the actual policy when there are compliance issues
        if not policy_compliant:
            result['current_policy'] = policy_text

        return result

    except ecr_client.exceptions.RegistryPolicyNotFoundException:
        return {
            'accessible_to_omics': False,
            'policy_compliant': False,
            'has_policy': False,
            'required_actions': ['ecr:CreateRepository', 'ecr:BatchImportUpstreamImage'],
        }


def _check_repository_creation_template(
    ecr_client, prefix: str, omics_principal: str
) -> Dict[str, Any]:
    """Check if repository creation template exists and has proper policy for HealthOmics."""
    try:
        response = ecr_client.describe_repository_creation_templates(prefixes=[prefix])
        templates = response.get('repositoryCreationTemplates', [])

        if not templates:
            return {
                'has_template': False,
                'template_compliant': False,
                'errors': [f'No repository creation template found for prefix: {prefix}'],
            }

        template = templates[0]
        applied_for = template.get('appliedFor', [])

        # Check if template applies to pull through cache
        if 'PULL_THROUGH_CACHE' not in applied_for:
            result = {
                'has_template': True,
                'template_compliant': False,
                'errors': [
                    f'Repository creation template for prefix {prefix} does not apply to PULL_THROUGH_CACHE'
                ],
                'template_details': {
                    'prefix': template.get('prefix'),
                    'appliedFor': applied_for,
                    'encryptionConfiguration': template.get('encryptionConfiguration'),
                },
            }
            # Include repository policy if it exists
            repository_policy = template.get('repositoryPolicy')
            if repository_policy:
                result['current_repository_policy'] = repository_policy
            return result

        # Check repository policy in template
        repository_policy = template.get('repositoryPolicy')
        if not repository_policy:
            return {
                'has_template': True,
                'template_compliant': False,
                'warnings': [
                    f'Repository creation template for prefix {prefix} has no repository policy'
                ],
                'template_details': {
                    'prefix': template.get('prefix'),
                    'appliedFor': applied_for,
                    'encryptionConfiguration': template.get('encryptionConfiguration'),
                },
            }

        # Parse and check the repository policy
        try:
            policy = json.loads(repository_policy)
            required_actions = ['ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer']

            accessible_to_omics = False
            policy_compliant = False

            for statement in policy.get('Statement', []):
                if statement.get('Effect', '').upper() != 'ALLOW':
                    continue

                # Check principals
                principals = statement.get('Principal', {})
                if isinstance(principals, str):
                    principals = {'Service': [principals]}
                elif isinstance(principals, list):
                    principals = {'Service': principals}

                service_principals = principals.get('Service', [])
                if isinstance(service_principals, str):
                    service_principals = [service_principals]

                if omics_principal in service_principals or '*' in service_principals:
                    accessible_to_omics = True

                    # Check actions
                    actions = statement.get('Action', [])
                    if isinstance(actions, str):
                        actions = [actions]

                    has_all_actions = all(
                        action in actions or 'ecr:*' in actions or '*' in actions
                        for action in required_actions
                    )

                    if has_all_actions:
                        policy_compliant = True
                        break

            result = {
                'has_template': True,
                'template_compliant': policy_compliant,
                'accessible_to_omics': accessible_to_omics,
                'template_details': {
                    'prefix': template.get('prefix'),
                    'appliedFor': applied_for,
                    'encryptionConfiguration': template.get('encryptionConfiguration'),
                },
            }

            # Include the actual policy when there are compliance issues
            if not policy_compliant:
                result['current_repository_policy'] = repository_policy

            return result

        except json.JSONDecodeError:
            return {
                'has_template': True,
                'template_compliant': False,
                'errors': [f'Invalid JSON in repository policy for template {prefix}'],
                'current_repository_policy': repository_policy,
                'template_details': {
                    'prefix': template.get('prefix'),
                    'appliedFor': applied_for,
                    'encryptionConfiguration': template.get('encryptionConfiguration'),
                },
            }

    except Exception as e:
        logger.error(f'Error checking repository creation template for {prefix}: {str(e)}')
        return {
            'has_template': False,
            'template_compliant': False,
            'errors': [f'Error checking repository creation template for {prefix}: {str(e)}'],
        }


async def check_ecr_pull_through_cache_for_omics(
    ctx: Context,
    region: Optional[str] = Field(
        None,
        description='AWS region to check (defaults to current region)',
    ),
) -> Dict[str, Any]:
    """Check which ECR pull through caches can be used by HealthOmics.

    This function examines ECR pull through cache rules and validates that they have
    the necessary registry permissions and repository creation templates to work with
    AWS HealthOmics workflows.

    For each pull through cache prefix, it checks:
    1. Registry permissions policy allows HealthOmics to create repositories and pull images
    2. Repository creation template exists and applies to pull through cache
    3. Repository creation template has proper policy for HealthOmics access

    IMPORTANT CAVEATS:
    1. Actual access will be determined at runtime and can be influenced by additional
       factors that are not checked here, such as Service Control Policies (SCPs),
       permission boundaries, and other resource-based restrictions.
    2. The permissions may not be sufficient for cross-account scenarios where additional
       trust relationships and cross-account policies may be required.
    3. This verification only checks basic ECR registry and repository creation template
       policies and does not validate all possible AWS IAM configurations that could
       affect access.

    Args:
        ctx: MCP context for error reporting
        region: AWS region to check (defaults to current region)

    Returns:
        Dictionary containing analysis of pull through cache compatibility with HealthOmics
    """
    try:
        # Create ECR client for the specified region
        if region:
            ecr_client = _create_ecr_client_for_region(region)
        else:
            ecr_client = create_aws_client('ecr')
            region = ecr_client.meta.region_name

        omics_principal = 'omics.amazonaws.com'

        # Get pull through cache rules
        try:
            ptc_response = ecr_client.describe_pull_through_cache_rules()
            ptc_rules = ptc_response.get('pullThroughCacheRules', [])
        except Exception as e:
            error_message = f'Error retrieving pull through cache rules: {str(e)}'
            logger.error(error_message)
            await ctx.error(error_message)
            raise

        if not ptc_rules:
            return {
                'region': region,
                'pull_through_cache_rules': [],
                'registry_policy_compliant': False,
                'compatible_prefixes': [],
                'total_rules': 0,
                'compatible_rules': 0,
                'message': 'No pull through cache rules found in this region',
            }

        # Check registry policy compliance
        registry_policy_check = _check_registry_policy_compliance(ecr_client, omics_principal)

        # Analyze each pull through cache rule
        rule_analysis = {}
        compatible_prefixes = []

        for rule in ptc_rules:
            prefix = rule.get('ecrRepositoryPrefix', '')
            upstream_registry_url = rule.get('upstreamRegistryUrl', '')

            # Check repository creation template
            template_check = _check_repository_creation_template(
                ecr_client, prefix, omics_principal
            )

            # Determine if this prefix is compatible with HealthOmics
            is_compatible = (
                registry_policy_check['policy_compliant'] and template_check['template_compliant']
            )

            if is_compatible:
                compatible_prefixes.append(prefix)

            rule_analysis[prefix] = {
                'upstream_registry_url': upstream_registry_url,
                'registry_id': rule.get('registryId'),
                'creation_time': rule.get('createdAt'),
                'is_compatible_with_omics': is_compatible,
                'template_check': template_check,
                'issues': [],
                'recommendations': [],
            }

            # Add issues and recommendations
            if not registry_policy_check['policy_compliant']:
                rule_analysis[prefix]['issues'].append(
                    'Registry policy does not allow HealthOmics to create repositories and pull images'
                )
                rule_analysis[prefix]['recommendations'].append(
                    f'Add registry policy allowing {omics_principal} to perform: {", ".join(registry_policy_check["required_actions"])}'
                )

            if not template_check['has_template']:
                rule_analysis[prefix]['issues'].append(
                    f'No repository creation template found for prefix {prefix}'
                )
                rule_analysis[prefix]['recommendations'].append(
                    f'Create repository creation template for prefix {prefix} that applies to PULL_THROUGH_CACHE'
                )
            elif not template_check['template_compliant']:
                rule_analysis[prefix]['issues'].append(
                    'Repository creation template does not allow HealthOmics access'
                )
                rule_analysis[prefix]['recommendations'].append(
                    f'Update repository creation template policy to allow {omics_principal} access'
                )

        return {
            'region': region,
            'pull_through_cache_rules': list(rule_analysis.keys()),
            'registry_policy_compliant': registry_policy_check['policy_compliant'],
            'registry_policy_details': registry_policy_check,
            'compatible_prefixes': compatible_prefixes,
            'total_rules': len(ptc_rules),
            'compatible_rules': len(compatible_prefixes),
            'rule_analysis': rule_analysis,
            'summary': {
                'message': f'Found {len(ptc_rules)} pull through cache rules, {len(compatible_prefixes)} compatible with HealthOmics',
                'next_steps': [
                    'Use compatible prefixes in your HealthOmics workflow container URIs',
                    'Fix registry policy and repository creation templates for incompatible prefixes',
                    'Test container image pulls using the compatible prefixes',
                ]
                if compatible_prefixes
                else [
                    'Configure registry policy to allow HealthOmics access',
                    'Create repository creation templates for your pull through cache prefixes',
                    'Ensure templates apply to PULL_THROUGH_CACHE and allow HealthOmics access',
                ],
            },
        }

    except Exception as e:
        error_message = f'Error checking ECR pull through cache compatibility: {str(e)}'
        logger.error(error_message)
        await ctx.error(error_message)
        raise
