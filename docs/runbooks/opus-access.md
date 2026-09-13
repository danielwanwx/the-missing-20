# Restore Opus 4.6 access

Verified September 12, 2026. The application uses AWS profile `missing20-sandbox`, which assumes `Missing20DeveloperRole`, in `us-west-2`. A real minimal Converse request to `us.anthropic.claude-opus-4-6-v1` returned `AccessDeniedException`: no identity-based policy allows `bedrock:InvokeModel`. A separate `GetInferenceProfile` request was also denied. Login is valid and Nova Pro works. This evidence establishes an IAM blocker, not an expired session or a model-quality result.

The existing Chrome console shows two inline role policies: Nova Pro and Nova 2 Lite. It also shows a permissions boundary. The boundary's contents have not yet been verified. The application role cannot list its IAM policies through the API. Do not broaden that role's IAM administration rights to fix inference access.

## Administrator action

Open IAM → Roles → `Missing20DeveloperRole` → Permissions using an administrator identity. Add a separate, narrowly scoped policy for this model; retain existing policies. The following is a review template, **not an applied change**. Replace `ACCOUNT_ID` with the intended AWS account ID.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeOpus46USProfile",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:us-west-2:ACCOUNT_ID:inference-profile/us.anthropic.claude-opus-4-6-v1"
    },
    {
      "Sid": "InvokeOpus46DestinationsThroughProfile",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-opus-4-6-v1",
        "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-opus-4-6-v1",
        "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-opus-4-6-v1"
      ],
      "Condition": {
        "StringEquals": {
          "bedrock:InferenceProfileArn": "arn:aws:bedrock:us-west-2:ACCOUNT_ID:inference-profile/us.anthropic.claude-opus-4-6-v1"
        }
      }
    },
    {
      "Sid": "InspectOpus46Profile",
      "Effect": "Allow",
      "Action": "bedrock:GetInferenceProfile",
      "Resource": "arn:aws:bedrock:us-west-2:ACCOUNT_ID:inference-profile/us.anthropic.claude-opus-4-6-v1"
    }
  ]
}
```

The [AWS Opus 4.6 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-6.html) lists Oregon as a supported source region with Virginia, Ohio and Oregon destinations. The [inference-profile prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html) require permissions for the profile and its destination models. The [geographic inference guidance](https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html) confirms that `bedrock:InferenceProfileArn` is populated for foundation-model evaluations, which is why the condition belongs only on that statement. Verify the existing permissions boundary and any organization policy also permit this exact use; do not remove the boundary or grant general administrator access. Changing the console's selected region alone does not supply missing role permissions.

After the administrator applies the intended change, repeat one minimal request and one streaming application request with the original sandbox role. If a different error then identifies account-level model access or Anthropic use-case requirements, follow [AWS model-access guidance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html). An IAM denial alone does not prove those additional requirements are missing.

## Application and comparison boundary

Select Opus explicitly only after invocation succeeds. Do not silently fall back to Nova. Historical Opus success does not prove current authorization, and a successful connectivity probe does not establish answer accuracy.

The existing [paired evaluation protocol](../research/2026-09-12-paired-evaluation-protocol.md) freezes Nova for both single-agent and Graph candidates. An Opus comparison needs a separately frozen model configuration and pricing/budget allowance before paid runs; do not mix models and attribute a quality change to multi-agent architecture. The native conversation's repeated-evidence context growth also needs correction regardless of model selection.
