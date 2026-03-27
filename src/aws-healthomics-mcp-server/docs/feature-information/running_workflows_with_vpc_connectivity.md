Running workflows with VPC networking

Starting a run with VPC networking
To use VPC networking in a workflow run, specify the networking-mode parameter and the configuration-name:


aws omics start-run \
  --workflow-id 1234567 \
  --role-arn arn:aws:iam::123456789012:role/OmicsWorkflowRole \
  --output-uri s3://my-bucket/outputs/ \
  --networking-mode VPC \
  --configuration-name my-vpc-config \
  --region us-west-2
Parameters:

networking-mode — Set to VPC to enable VPC networking. The default is RESTRICTED.

configuration-name (required) — The name of the configuration to use.

Viewing run network configuration
Use GetRun to view the networking configuration for a run:


aws omics get-run \
  --id run-id \
  --region region
The response includes the networking mode, configuration details, and VPC configuration. The following example shows the VPC-related fields from the response:


{
  "arn": "arn:aws:omics:region:account-id:run/run-id",
  "id": "run-id",
  "status": "status",
  "workflowId": "workflow-id",
  "networkingMode": "VPC",
  "configuration": {
    "name": "configuration-name",
    "arn": "arn:aws:omics:region:account-id:configuration/configuration-name",
    "uuid": "configuration-uuid"
  },
  "vpcConfig": {
    "subnets": ["subnet-id-1", "subnet-id-2"],
    "securityGroupIds": ["security-group-id"],
    "vpcId": "vpc-id"
  }
}
Configuration immutability
Workflows use a snapshot of the configuration as it existed when the run started. You can safely modify or delete configurations during run execution without affecting active runs.
