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

"""WDL utility functions for the HealthOmics MCP server."""

import re
import subprocess
from loguru import logger
from typing import Dict, Tuple, Union


def is_miniwdl_installed() -> bool:
    """Check if miniwdl is installed.

    Returns:
        bool: True if miniwdl is installed, False otherwise
    """
    try:
        subprocess.run(['miniwdl', '--version'], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def validate_wdl(wdl_content: str) -> Tuple[bool, str]:
    """Validate WDL syntax using miniwdl if available.

    Args:
        wdl_content: WDL content to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not is_miniwdl_installed():
        logger.warning('miniwdl is not installed, skipping WDL validation')
        return True, ''

    # Write WDL content to a temporary file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.wdl', mode='w') as temp_file:
        temp_file.write(wdl_content)
        temp_file.flush()

        # Run miniwdl check
        result = subprocess.run(
            ['miniwdl', 'check', temp_file.name],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return True, ''
        else:
            return False, result.stderr


def extract_wdl_inputs(wdl_content: str) -> Dict[str, Dict[str, Union[str, bool]]]:
    """Extract input parameters from WDL content.

    Args:
        wdl_content: WDL content to parse

    Returns:
        Dict[str, Dict[str, Union[str, bool]]]: Parameter template
    """
    if not is_miniwdl_installed():
        logger.warning('miniwdl is not installed, using regex-based WDL input extraction')
        return _extract_wdl_inputs_regex(wdl_content)

    # Write WDL content to a temporary file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.wdl', mode='w') as temp_file:
        temp_file.write(wdl_content)
        temp_file.flush()

        # Run miniwdl input
        result = subprocess.run(
            ['miniwdl', 'input', temp_file.name],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.error(f'Error extracting WDL inputs: {result.stderr}')
            return {}

        # Parse the output
        parameter_template = {}
        for line in result.stdout.strip().split('\n'):
            if not line or ':' not in line:
                continue

            param_name, param_type = line.split(':', 1)
            param_name = param_name.strip()
            param_type = param_type.strip()

            # Check if the parameter has a default value
            has_default = '=' in param_type
            optional = has_default

            if has_default:
                param_type = param_type.split('=')[0].strip()

            parameter_template[param_name] = {
                'description': f'Parameter of type {param_type}',
                'optional': optional,
            }

        return parameter_template


def _extract_wdl_inputs_regex(wdl_content: str) -> Dict[str, Dict[str, Union[str, bool]]]:
    """Extract input parameters from WDL content using regex.

    Args:
        wdl_content: WDL content to parse

    Returns:
        Dict[str, Dict[str, Union[str, bool]]]: Parameter template
    """
    # Simple regex to find workflow inputs
    workflow_match = re.search(
        r'workflow\s+(\w+)\s*\{(.*?)input\s*\{(.*?)\}',
        wdl_content,
        re.DOTALL,
    )

    if not workflow_match:
        logger.error('Could not find workflow input section in WDL')
        return {}

    input_section = workflow_match.group(3)

    # Extract parameters
    parameter_template = {}
    for line in input_section.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Remove trailing comma if present
        if line.endswith(','):
            line = line[:-1]

        # Skip if line doesn't contain a parameter definition
        if ':' not in line:
            continue

        # Parse parameter
        parts = line.split(':')
        param_name = parts[0].strip()
        param_type = parts[1].strip()

        # Check if the parameter has a default value
        has_default = '=' in param_type
        optional = has_default

        if has_default:
            param_type = param_type.split('=')[0].strip()

        parameter_template[param_name] = {
            'description': f'Parameter of type {param_type}',
            'optional': optional,
        }

    return parameter_template
