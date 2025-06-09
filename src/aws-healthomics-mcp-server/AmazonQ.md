# AWS HealthOmics MCP Server Design Document

## Overview

The AWS HealthOmics MCP Server is designed to provide AI assistants with the ability to interact with AWS HealthOmics services through the Model Context Protocol (MCP). This server will enable AI tools to create, manage, and analyze genomic workflows, making it easier for users to leverage AWS HealthOmics capabilities through natural language interactions.

## Core Functionality

The server will provide tools for:

1. **Workflow Management** - Creating, listing, and managing HealthOmics workflows
2. **Workflow Execution** - Running workflows with appropriate parameters and monitoring their status
3. **Results Retrieval** - Accessing and analyzing workflow outputs
4. **Performance Analysis** - Analyzing workflow performance with the run analyzer tool
5. **Troubleshooting** - Accessing logs and diagnosing issues

## Architecture

### Directory Structure

```
src/aws-healthomics-mcp-server/
├── README.md                   # Server documentation
├── pyproject.toml              # Package configuration
├── awslabs/
│   └── aws_healthomics_mcp_server/
│       ├── __init__.py
│       ├── server.py           # Main server implementation
│       ├── models.py           # Pydantic models for request/response validation
│       ├── consts.py           # Constants used across the server
│       ├── tools/              # Tool implementations
│       │   ├── __init__.py
│       │   ├── workflow_management.py
│       │   ├── workflow_execution.py
│       │   ├── workflow_analysis.py
│       │   └── troubleshooting.py
│       └── utils/              # Utility functions
│           ├── __init__.py
│           ├── s3_utils.py
│           ├── wdl_utils.py
│           └── aws_utils.py
└── tests/                      # Unit tests
    ├── __init__.py
    ├── conftest.py
    ├── test_server.py
    └── tools/
        ├── __init__.py
        ├── test_workflow_management.py
        ├── test_workflow_execution.py
        └── test_workflow_analysis.py
```

### Key Components

1. **Server Module** (`server.py`)
   - Main FastMCP server implementation
   - Tool registration and routing

2. **Models Module** (`models.py`)
   - Pydantic models for request/response validation
   - Data structures for HealthOmics entities

3. **Constants Module** (`consts.py`)
   - Service constants
   - Error messages
   - Default values

4. **Tool Modules**
   - Specialized modules for different HealthOmics functionality areas

5. **Utility Modules**
   - Helper functions for common operations

## MCP Tools Implementation

### 1. Workflow Management Tools

#### `list_workflows`
```python
@mcp.tool(name='ListWorkflows')
async def list_workflows(
    max_results: Optional[int] = 10,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List available HealthOmics workflows.

    Args:
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination

    Returns:
        Dictionary containing workflow information and next token if available
    """
```

#### `create_workflow`
```python
@mcp.tool(name='CreateWorkflow')
async def create_workflow(
    name: str,
    definition_zip_base64: str,
    description: Optional[str] = None,
    parameter_template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new HealthOmics workflow.

    Args:
        name: Name of the workflow
        definition_zip_base64: Base64-encoded workflow definition ZIP file
        description: Optional description of the workflow
        parameter_template: Optional parameter template for the workflow

    Returns:
        Dictionary containing the created workflow information
    """
```

#### `get_workflow`
```python
@mcp.tool(name='GetWorkflow')
async def get_workflow(
    workflow_id: str,
    export_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Get details about a specific workflow.

    Args:
        workflow_id: ID of the workflow to retrieve
        export_type: Optional export type (DEFINITION, PARAMETER_TEMPLATE)

    Returns:
        Dictionary containing workflow details
    """
```

#### `create_workflow_version`
```python
@mcp.tool(name='CreateWorkflowVersion')
async def create_workflow_version(
    workflow_id: str,
    version_name: str,
    definition_zip_base64: str,
    description: Optional[str] = None,
    parameter_template: Optional[Dict[str, Any]] = None,
    storage_type: Optional[str] = "DYNAMIC",
    storage_capacity: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a new version of an existing workflow.

    Args:
        workflow_id: ID of the workflow
        version_name: Name for the new version
        definition_zip_base64: Base64-encoded workflow definition ZIP file
        description: Optional description of the workflow version
        parameter_template: Optional parameter template for the workflow
        storage_type: Storage type (STATIC or DYNAMIC)
        storage_capacity: Storage capacity in GB (required for STATIC)

    Returns:
        Dictionary containing the created workflow version information
    """
```

### 2. Workflow Execution Tools

#### `start_run`
```python
@mcp.tool(name='StartRun')
async def start_run(
    workflow_id: str,
    role_arn: str,
    name: str,
    output_uri: str,
    parameters: Dict[str, Any],
    workflow_version_name: Optional[str] = None,
    storage_type: Optional[str] = "DYNAMIC",
    storage_capacity: Optional[int] = None,
    cache_id: Optional[str] = None,
    cache_behavior: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a workflow run.

    Args:
        workflow_id: ID of the workflow to run
        role_arn: ARN of the IAM role to use for the run
        name: Name for the run
        output_uri: S3 URI for the run outputs
        parameters: Parameters for the workflow
        workflow_version_name: Optional version name to run
        storage_type: Storage type (STATIC or DYNAMIC)
        storage_capacity: Storage capacity in GB (required for STATIC)
        cache_id: Optional ID of a run cache to use
        cache_behavior: Optional cache behavior (CACHE_ALWAYS or CACHE_ON_FAILURE)

    Returns:
        Dictionary containing the run information
    """
```

#### `list_runs`
```python
@mcp.tool(name='ListRuns')
async def list_runs(
    max_results: Optional[int] = 10,
    next_token: Optional[str] = None,
    status: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """List workflow runs.

    Args:
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination
        status: Filter by run status
        created_after: Filter for runs created after this timestamp (ISO format)
        created_before: Filter for runs created before this timestamp (ISO format)

    Returns:
        Dictionary containing run information and next token if available
    """
```

#### `get_run`
```python
@mcp.tool(name='GetRun')
async def get_run(
    run_id: str,
) -> Dict[str, Any]:
    """Get details about a specific run.

    Args:
        run_id: ID of the run to retrieve

    Returns:
        Dictionary containing run details
    """
```

#### `list_run_tasks`
```python
@mcp.tool(name='ListRunTasks')
async def list_run_tasks(
    run_id: str,
    max_results: Optional[int] = 10,
    next_token: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List tasks for a specific run.

    Args:
        run_id: ID of the run
        max_results: Maximum number of results to return (default: 10)
        next_token: Token for pagination
        status: Filter by task status

    Returns:
        Dictionary containing task information and next token if available
    """
```

### 3. Workflow Analysis Tools

#### `analyze_run`
```python
@mcp.tool(name='AnalyzeRun')
async def analyze_run(
    run_ids: List[str],
    headroom: Optional[float] = 0.1,
) -> Dict[str, Any]:
    """Analyze run performance using the run analyzer.

    Args:
        run_ids: List of run IDs to analyze
        headroom: Resource headroom factor (0.0-1.0, default: 0.1)

    Returns:
        Dictionary containing analysis results
    """
```

#### `get_run_logs`
```python
@mcp.tool(name='GetRunLogs')
async def get_run_logs(
    run_id: str,
    task_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: Optional[int] = 100,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve logs for a run or task.

    Args:
        run_id: ID of the run
        task_id: Optional ID of a specific task
        start_time: Optional start time for log retrieval (ISO format)
        end_time: Optional end time for log retrieval (ISO format)
        limit: Maximum number of log events to return (default: 100)
        next_token: Token for pagination

    Returns:
        Dictionary containing log events and next token if available
    """
```

### 4. Helper Tools

#### `package_workflow`
```python
@mcp.tool(name='PackageWorkflow')
async def package_workflow(
    main_file_content: str,
    main_file_name: str = "main.wdl",
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
```

#### `validate_workflow`
```python
@mcp.tool(name='ValidateWorkflow')
async def validate_workflow(
    workflow_content: str,
    workflow_type: str = "WDL",
) -> Dict[str, Any]:
    """Validate workflow syntax.

    Args:
        workflow_content: Content of the workflow file
        workflow_type: Type of workflow (WDL, CWL, or Nextflow)

    Returns:
        Dictionary containing validation results
    """
```

## Configuration

The server will support the following configuration options through environment variables:

- `AWS_REGION` - AWS region for HealthOmics operations
- `AWS_PROFILE` - AWS profile to use for credentials
- `DEFAULT_ROLE_ARN` - Default IAM role ARN for workflow execution
- `DEFAULT_OUTPUT_URI` - Default S3 URI for workflow outputs
- `DEFAULT_STORAGE_TYPE` - Default storage type (STATIC or DYNAMIC)
- `FASTMCP_LOG_LEVEL` - Logging level for the server

## Integration Points

The server will integrate with:

1. **AWS HealthOmics API** - For workflow management and execution
2. **Amazon S3** - For workflow inputs/outputs and run cache
3. **Amazon CloudWatch** - For accessing workflow logs
4. **AWS IAM** - For role-based access to resources
5. **WDL/CWL/Nextflow Tools** - For workflow validation and parameter generation

## Security Considerations

1. **IAM Role Management**
   - The server will require appropriate IAM permissions to interact with HealthOmics
   - Users must provide a role ARN with appropriate permissions for workflow execution

2. **Data Access**
   - The server will only access S3 locations explicitly provided in API calls
   - No sensitive data will be stored by the server

3. **Input Validation**
   - All inputs will be validated using Pydantic models
   - Workflow content will be validated before submission

## Testing Strategy

1. **Unit Tests**
   - Test individual tool functions with mocked AWS responses
   - Validate input/output models

2. **Integration Tests**
   - Test end-to-end workflow with AWS services (marked as "live" tests)
   - Verify correct interaction with HealthOmics API

3. **Mock Tests**
   - Use mocked responses for testing error handling

## Documentation

The server will include:

1. **README.md** - Overview, installation, and usage instructions
2. **API Documentation** - Detailed documentation for each tool
3. **Example Workflows** - Sample workflows for common use cases
4. **Troubleshooting Guide** - Common issues and solutions

## Implementation Plan

1. **Phase 1: Core Infrastructure**
   - Set up project structure
   - Implement basic server with AWS authentication
   - Create models and constants

2. **Phase 2: Workflow Management**
   - Implement workflow listing and retrieval
   - Add workflow creation and versioning

3. **Phase 3: Workflow Execution**
   - Implement run starting and monitoring
   - Add task listing and details

4. **Phase 4: Analysis and Helpers**
   - Implement run analyzer integration
   - Add log retrieval
   - Create helper tools

5. **Phase 5: Testing and Documentation**
   - Complete unit and integration tests
   - Finalize documentation
   - Create example workflows

## Conclusion

The AWS HealthOmics MCP Server will provide a powerful interface for AI assistants to interact with AWS HealthOmics services. By implementing the tools outlined in this design document, the server will enable users to create, run, and analyze genomic workflows through natural language interactions, making AWS HealthOmics more accessible and easier to use.
