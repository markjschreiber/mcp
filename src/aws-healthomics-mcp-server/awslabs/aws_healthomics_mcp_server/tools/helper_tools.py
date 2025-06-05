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

"""Helper tools for the AWS HealthOmics MCP server."""

from awslabs.aws_healthomics_mcp_server.consts import (
    ERROR_INVALID_WORKFLOW_TYPE,
    WORKFLOW_TYPE_WDL,
    WORKFLOW_TYPES,
)
from awslabs.aws_healthomics_mcp_server.utils.aws_utils import (
    create_zip_file,
    encode_to_base64,
)
from awslabs.aws_healthomics_mcp_server.utils.wdl_utils import (
    extract_wdl_inputs,
    validate_wdl,
)
from loguru import logger
from typing import Any, Dict, Optional


async def package_workflow(
    main_file_content: str,
    main_file_name: str = 'main.wdl',
    additional_files: Optional[Dict[str, str]] = None,
) -> str:
    """Package workflow definition files into a base64-encoded ZIP.

    Args:
        main_file_content: Content of the main workflow file
        main_file_name: Name of the main workflow file (default: main.wdl)
        additional_files: Dictionary of additional files (filename: content)

    Returns:
        Base64-encoded ZIP file containing the workflow definition
    """
    try:
        # Create a dictionary of files
        files = {main_file_name: main_file_content}

        if additional_files:
            files.update(additional_files)

        # Create ZIP file
        zip_data = create_zip_file(files)

        # Encode to base64
        base64_data = encode_to_base64(zip_data)

        return base64_data
    except Exception as e:
        logger.error(f'Error packaging workflow: {str(e)}')
        return {'error': str(e)}


async def validate_workflow(
    workflow_content: str,
    workflow_type: str = 'WDL',
) -> Dict[str, Any]:
    """Validate workflow syntax.

    Args:
        workflow_content: Content of the workflow file
        workflow_type: Type of workflow (WDL, CWL, or Nextflow)

    Returns:
        Dictionary containing validation results
    """
    # Validate workflow type
    if workflow_type not in WORKFLOW_TYPES:
        return {'error': ERROR_INVALID_WORKFLOW_TYPE.format(WORKFLOW_TYPES)}

    try:
        if workflow_type == WORKFLOW_TYPE_WDL:
            is_valid, error_message = validate_wdl(workflow_content)

            return {
                'isValid': is_valid,
                'errorMessage': error_message if not is_valid else '',
            }
        else:
            # For other workflow types, we don't have built-in validation yet
            return {
                'isValid': True,
                'message': f'Validation for {workflow_type} is not implemented yet. The workflow is assumed to be valid.',
            }
    except Exception as e:
        logger.error(f'Error validating workflow: {str(e)}')
        return {'error': str(e)}


async def generate_parameter_template(
    workflow_content: str,
    workflow_type: str = 'WDL',
) -> Dict[str, Any]:
    """Generate parameter template from workflow.

    Args:
        workflow_content: Content of the workflow file
        workflow_type: Type of workflow (WDL, CWL, or Nextflow)

    Returns:
        Dictionary containing the generated parameter template
    """
    # Validate workflow type
    if workflow_type not in WORKFLOW_TYPES:
        return {'error': ERROR_INVALID_WORKFLOW_TYPE.format(WORKFLOW_TYPES)}

    try:
        if workflow_type == WORKFLOW_TYPE_WDL:
            parameter_template = extract_wdl_inputs(workflow_content)

            return {
                'parameterTemplate': parameter_template,
            }
        else:
            # For other workflow types, we don't have built-in parameter extraction yet
            return {
                'error': f'Parameter template generation for {workflow_type} is not implemented yet.',
            }
    except Exception as e:
        logger.error(f'Error generating parameter template: {str(e)}')
        return {'error': str(e)}
