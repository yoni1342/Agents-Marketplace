#!/usr/bin/env bash
# Run `alembic upgrade head` for the named service(s) as one-off Fargate tasks,
# before rolling the service. Fails the deploy if a migration fails.
#
#   ./run-migrations.sh marketplace
#   MIGRATION_IMAGE=123.dkr.ecr.../marketplace:<sha> ./run-migrations.sh marketplace
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER="${CLUSTER:-bench-prod}"
[ "$#" -eq 1 ] || { echo "usage: run-migrations.sh <service>"; exit 2; }

# Borrow network config from an existing service so the task lands in the same
# private subnets + SG with access to RDS.
NET=$(aws ecs describe-services --cluster "$CLUSTER" --services "$1" \
  --query 'services[0].networkConfiguration.awsvpcConfiguration' --output json)
SUBNETS=$(echo "$NET" | jq -r '.subnets | join(",")')
SGS=$(echo "$NET" | jq -r '.securityGroups | join(",")')

run_migration() {  # run_migration <service>
  local svc=$1 family="${CLUSTER}-${1}"
  local task_def="$family"
  if [ -n "${MIGRATION_IMAGE:-}" ]; then
    local td new_td
    td=$(aws ecs describe-task-definition --task-definition "$family" \
      --query 'taskDefinition' --output json)
    new_td=$(echo "$td" | jq --arg IMG "$MIGRATION_IMAGE" '
      .containerDefinitions[0].image=$IMG
      | del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy)')
    task_def=$(aws ecs register-task-definition --cli-input-json "$new_td" \
      --query 'taskDefinition.taskDefinitionArn' --output text)
  fi
  local overrides
  overrides=$(jq -nc --arg name "$svc" \
    '{containerOverrides:[{name:$name, command:["alembic","upgrade","head"]}]}')
  local arn
  arn=$(aws ecs run-task --cluster "$CLUSTER" --launch-type FARGATE \
    --task-definition "$task_def" \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SGS],assignPublicIp=DISABLED}" \
    --overrides "$overrides" \
    --query 'tasks[0].taskArn' --output text)
  echo "started $svc migration: $arn"
  aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$arn"
  local code
  code=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$arn" \
    --query 'tasks[0].containers[0].exitCode' --output text)
  [ "$code" = "0" ] || { echo "::error::migration $svc exited $code"; exit 1; }
  echo "$svc migration ok"
}

run_migration "$1"
echo "all migrations complete"
