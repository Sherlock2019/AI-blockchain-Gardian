# Security Policy

Version: SECURITY-POLICY-v1. Synthetic document for demonstration only.

## 1. Least privilege

Users and agents receive the minimum permissions their role requires.
Permissions are granted by allow-list and reviewed periodically.

## 2. Segregation of duties

The person or agent requesting a payment is never the one approving it.

## 3. Audit records

Audit records are append-only. No user or agent may delete or alter an audit
record. Audit records must be verifiable independently of the application that
wrote them.

## 4. Data handling

Invoice contents, supplier details, prompts and personal information are not
published to shared or public ledgers. Only hashes and non-sensitive identifiers
leave the application boundary. Secrets are never committed to source control
and never written to logs.

## 5. Incident response

When an agent requests an action outside its scope, the request is refused,
recorded, and every other request from the same agent run is refused with it.
