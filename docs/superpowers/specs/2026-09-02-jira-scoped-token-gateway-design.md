# Jira Scoped Token Gateway Support

## Purpose

Make the existing read-only CAPA evidence adapter work with Atlassian scoped API tokens while preserving the legacy Jira Cloud API-token path.

## Observed behavior

The verified CAPA issue is `QRC-1` in `Quality Release CAPA`. A scoped Jira token with `read:jira-work` can read it only through Atlassian's Gateway endpoint:

`https://api.atlassian.com/ex/jira/<cloud-id>/rest/api/3/search/jql`

The current adapter instead sends Basic authentication to the site URL. That returns no usable CAPA evidence for the scoped token.

## Design

Add an optional `JIRA_CLOUD_ID` configuration value.

- When it is set, build Jira evidence URLs through the Gateway endpoint and authenticate with `Authorization: Bearer <JIRA_API_TOKEN>`.
- When it is absent, preserve the existing site-URL plus Basic-auth behavior for legacy personal API tokens.
- Continue using the existing bounded JQL, projected fields, safe provider record, and read-only adapter contract.
- Add focused tests for both authentication/url modes; no write endpoints are introduced.

## Configuration

The local environment will supply the existing Jira site URL, observer email, token, project key, and the discovered non-secret cloud ID. Tokens remain only in the ignored local `.env`; examples contain placeholders only.

## Verification

1. Unit tests assert Gateway URL and Bearer header selection when `JIRA_CLOUD_ID` exists.
2. Legacy-mode tests assert unchanged Basic-auth behavior.
3. A live read-only `search/jql` query returns `QRC-1`.
4. The local `/api/v1/saas-evidence` endpoint reports Jira as `VERIFIED` alongside Airtable and Slack.

## Boundaries

This change does not create, edit, transition, or delete Jira issues. It does not broaden the token beyond the existing seven-day `read:jira-work` scope.
