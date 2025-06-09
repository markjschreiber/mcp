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

import subprocess
from loguru import logger
from typing import Tuple


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
