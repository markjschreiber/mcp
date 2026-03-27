Configuration APIs

HealthOmics provides APIs to create, manage, and delete VPC configurations. You can reuse configurations across multiple workflow runs.

Topics
CreateConfiguration

GetConfiguration

ListConfigurations

DeleteConfiguration

CreateConfiguration
Creates a new configuration resource with VPC networking settings. For a step-by-step example, see Step 4: Create a configuration resource.

Request syntax:


aws omics create-configuration \
  --name configuration-name \
  --description description \
  --run-configurations '{"vpcConfig":{"securityGroupIds":["security-group-id"],"subnetIds":["subnet-id"]}}' \
  --tags Key=key,Value=value \
  --region region
Parameters:

name (required) — A unique name for the configuration (maximum 50 characters).

description (optional) — A description of the configuration.

run-configurations (optional) — VPC configuration settings:

vpcConfig.securityGroupIds — A list of 1–5 security group IDs.

vpcConfig.subnetIds — A list of 1–16 subnet IDs.

tags (optional) — Resource tags.

Response:


{
  "arn": "arn:aws:omics:region:account-id:configuration/configuration-name",
  "uuid": "configuration-uuid",
  "name": "configuration-name",
  "runConfigurations": {
    "vpcConfig": {
      "securityGroupIds": ["security-group-id"],
      "subnetIds": ["subnet-id"],
      "vpcId": "vpc-id"
    }
  },
  "status": "CREATING",
  "creationTime": "timestamp",
  "tags": {}
}
Configuration status values:

CREATING — The configuration is being created and network resources are being provisioned (up to 15 minutes).

ACTIVE — The configuration is ready to use.

DELETING — The configuration is being deleted.

DELETED — The configuration has been deleted.

GetConfiguration
Retrieves details of a specific configuration.

Request syntax:


aws omics get-configuration \
  --name configuration-name \
  --region region
Response:


{
  "arn": "arn:aws:omics:region:account-id:configuration/configuration-name",
  "uuid": "configuration-uuid",
  "name": "configuration-name",
  "runConfigurations": {
    "vpcConfig": {
      "securityGroupIds": ["security-group-id"],
      "subnetIds": ["subnet-id"],
      "vpcId": "vpc-id"
    }
  },
  "status": "ACTIVE",
  "creationTime": "timestamp",
  "tags": {}
}
ListConfigurations
Lists all configurations in your account.

Request syntax:


aws omics list-configurations \
  --region region
Response:


{
  "items": [
    {
      "arn": "arn:aws:omics:region:account-id:configuration/configuration-name",
      "name": "configuration-name",
      "description": "description",
      "status": "ACTIVE",
      "creationTime": "timestamp"
    }
  ]
}
DeleteConfiguration
Deletes a configuration. You cannot delete a configuration that is currently in use by active workflow runs.

Request syntax:


aws omics delete-configuration \
  --name configuration-name \
  --region region
Note
The configuration status changes to DELETING while network resources are being cleaned up, and then to DELETED once the process is complete.
