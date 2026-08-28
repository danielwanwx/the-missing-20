---
knowledge_id: retryable-document-lock
version: knowledge-v1
title: Retryable document lock definition
allowed_use: ERROR_DEFINITION_ONLY
---

A document-lock failure is retryable only when the message is marked FAILED, the error
code is DOCUMENT_LOCKED_RETRYABLE, retry_eligible is true, and the lock-cleared signal
is true. This definition explains the error class; it does not prove the state of a
particular message.
