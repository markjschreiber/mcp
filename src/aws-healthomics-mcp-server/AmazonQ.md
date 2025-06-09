# AWS HealthOmics MCP Server Design Document

## Overview

The AWS HealthOmics MCP Server provides AI assistants with the ability to interact with AWS HealthOmics services through the Model Context Protocol (MCP). This server enables AI tools to manage genomic workflows, analyze runs, and troubleshoot issues through natural language interactions.

## Core Functionality

The server provides tools for:

1. **Workflow Management**
   - Create and validate workflows
   - List and retrieve workflow details
   - Manage workflow versions
   - Package workflow definitions

2. **Workflow Execution**
   - Start workflow runs
   - Monitor run status
   - List and manage tasks
   - Access run details

3. **Analysis and Troubleshooting**
   - Analyze run performance
   - Access various log types (run, engine, task, manifest)
   - Diagnose run failures
   - Monitor resource utilization

4. **Region Management**
   - Get supported AWS regions for HealthOmics

## Architecture

### Directory Structure

```
aws-healthomics-mcp-server/
├── README.md                # Server documentation
├── pyproject.toml           # Package configuration
├── AmazonQ.md              # Design documentation
├── awslabs/
│   └── aws_healthomics_mcp_server/
│       ├── __init__.py     # Package initialization
│       ├── server.py       # Main server implementation
│       ├── models.py       # Pydantic models
│       ├── consts.py       # Constants
│       ├── workflow_analysis.py  # Analysis functionality
│       └── troubleshooting.py    # Troubleshooting tools
└── tests/                  # Unit tests
    ├── conftest.py        # Test fixtures
    ├── test_server.py     # Server tests
    ├── test_troubleshooting.py  # Troubleshooting tests
    └── test_workflow_analysis.py # Analysis tests
```

## Implemented Tools

### Workflow Management

1. **ListWorkflows**
   - List available HealthOmics workflows
   - Support pagination and result limiting
   - Return workflow details and metadata

2. **CreateWorkflow**
   - Create new workflows with definitions
   - Support parameter templates
   - Handle workflow metadata

3. **GetWorkflow**
   - Retrieve detailed workflow information
   - Support definition and parameter template export
   - Access workflow versions

4. **CreateWorkflowVersion**
   - Create new versions of existing workflows
   - Support different storage types
   - Handle version-specific parameters

5. **ValidateWorkflow**
   - Validate workflow syntax
   - Support multiple workflow types (WDL, CWL, Nextflow)
   - Provide detailed validation results

6. **PackageWorkflow**
   - Package workflow files into ZIP format
   - Support main and additional files
   - Generate base64-encoded output

### Workflow Execution

1. **StartRun**
   - Start workflow runs with parameters
   - Support different storage types
   - Handle caching configuration
   - Manage IAM roles and permissions

2. **ListRuns**
   - List workflow runs with filtering
   - Support status-based filtering
   - Handle date range queries
   - Implement pagination

3. **GetRun**
   - Retrieve detailed run information
   - Access run status and metadata
   - Get execution details

4. **ListRunTasks**
   - List tasks for specific runs
   - Filter by task status
   - Support pagination
   - Access task details

5. **GetRunTask**
   - Get detailed task information
   - Access task status and metadata
   - Retrieve resource utilization

### Analysis and Troubleshooting

1. **AnalyzeRun**
   - Analyze run performance
   - Calculate resource utilization
   - Support multiple run analysis
   - Configure resource headroom

2. **DiagnoseRunFailure**
   - Diagnose failed workflow runs
   - Analyze error patterns
   - Provide remediation suggestions
   - Access relevant logs

3. **GetRunLogs**
   - Access high-level workflow execution logs
   - Filter by time range
   - Support pagination
   - Track workflow events

4. **GetRunEngineLogs**
   - Access workflow engine logs (STDOUT/STDERR)
   - Monitor engine initialization
   - Track task scheduling
   - Debug engine issues

5. **GetRunManifestLogs**
   - Access run manifest logs
   - Review runtime information
   - Access input digests
   - Monitor resource metrics

6. **GetTaskLogs**
   - Access task-specific logs
   - Monitor task execution
   - Debug task failures
   - Track task output

### Region Management

1. **GetSupportedRegions**
   - List AWS regions where HealthOmics is available
   - Get region count
   - Access region codes

## Implementation Details

### Log Function Improvements

Recent updates include:

1. **Centralized Log Retrieval**
   - Unified log retrieval logic in workflow_analysis.py
   - Consistent parameter handling across log functions
   - Improved error handling and reporting

2. **Enhanced Parameters**
   - Added start_from_head parameter to all log functions
   - Default to retrieving most recent logs for troubleshooting
   - Configurable log limits and pagination

3. **UTC Timezone Handling**
   - Fixed timestamp conversion issues
   - Proper handling of UTC timestamps
   - Consistent time formatting

### Error Handling

1. **Hierarchical Error Handling**
   - Specific handling for ClientError
   - Dedicated handling for BotoCoreError
   - Generic exception handling as fallback

2. **Contextual Error Messages**
   - Clear error descriptions
   - Actionable error messages
   - Proper error propagation

### Testing

1. **Comprehensive Test Coverage**
   - 89% coverage for troubleshooting module
   - 50% coverage for workflow analysis module
   - 33 passing unit tests

2. **Test Infrastructure**
   - Shared fixtures in conftest.py
   - Mock AWS clients
   - Sample log events
   - MCP context mocking

3. **Test Categories**
   - Parameter validation tests
   - Error scenario coverage
   - Log retrieval verification
   - Tool functionality validation

## Configuration

The server supports configuration through environment variables:

- `AWS_REGION` - AWS region for HealthOmics operations
- `AWS_PROFILE` - AWS profile for authentication
- `FASTMCP_LOG_LEVEL` - Server logging level

## Security Considerations

1. **Authentication**
   - AWS credentials management
   - IAM role validation
   - Secure credential handling

2. **Input Validation**
   - Parameter validation using Pydantic
   - Workflow content validation
   - Safe file handling

3. **Error Handling**
   - Secure error messages
   - Protected stack traces
   - Controlled error propagation

## Future Enhancements

1. **Additional Analysis Tools**
   - Cost optimization recommendations
   - Performance benchmarking
   - Resource utilization trends

2. **Enhanced Troubleshooting**
   - Automated error pattern detection
   - Intelligent remediation suggestions
   - Historical analysis

3. **Workflow Optimization**
   - Resource right-sizing
   - Cache optimization
   - Performance tuning

## Conclusion

The AWS HealthOmics MCP Server provides a comprehensive interface for AI assistants to interact with AWS HealthOmics services. Recent improvements in log handling, error management, and test coverage have enhanced its reliability and maintainability. The server enables efficient workflow management, execution monitoring, and troubleshooting through a well-structured set of tools and resources.
