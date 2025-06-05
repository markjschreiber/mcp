# AWS Labs aws-healthomics MCP Server

An AWS Labs Model Context Protocol (MCP) server for AWS HealthOmics

## Instructions

Instructions for using this aws-healthomics MCP server. This can be used by clients to improve the LLM's understanding of available tools, resources, etc. for the AWS HealthOmics service

## TODO (REMOVE AFTER COMPLETING)

* [ ] Optionally add an ["RFC issue"](https://github.com/awslabs/mcp/issues) for the community to review
* [ ] Generate a `uv.lock` file with `uv sync` -> See [Getting Started](https://docs.astral.sh/uv/getting-started/)
* [ ] Remove the example tools in `./awslabs/aws_healthomics_mcp_server/server.py`
* [ ] Add your own tool(s) following the [DESIGN_GUIDELINES.md](https://github.com/awslabs/mcp/blob/main/DESIGN_GUIDELINES.md)
* [ ] Keep test coverage at or above the `main` branch - NOTE: GitHub Actions run this command for CodeCov metrics `uv run --frozen pytest --cov --cov-branch --cov-report=term-missing`
* [ ] Document the MCP Server in this "README.md"
* [ ] Add a section for this aws-healthomics MCP Server at the top level of this repository "../../README.md"
* [ ] Create the "../../doc/servers/aws-healthomics-mcp-server.md" file with these contents:

    ```markdown
    ---
    title: aws-healthomics MCP Server
    ---

    {% include "../../src/aws-healthomics-mcp-server/README.md" %}
    ```

* [ ] Reference within the "../../doc/index.md" like this:

    ```markdown
    ### aws-healthomics MCP Server

    An AWS Labs Model Context Protocol (MCP) server for AWS HealthOmics

    **Features:**

    - Feature one
    - Feature two
    - ...

    Instructions for using this aws-healthomics MCP server. This can be used by clients to improve the LLM's understanding of available tools, resources, etc. for the AWS HealthOmics service

    [Learn more about the aws-healthomics MCP Server](servers/aws-healthomics-mcp-server.md)
    ```

* [ ] Submit a PR and pass all the checks
