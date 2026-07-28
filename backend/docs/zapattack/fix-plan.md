Absolutely, C. Since this will likely be handed to the coding agent working on Synbot Health, the prompt should instruct it to **investigate, validate, remediate, test, and document**—not blindly patch every ZAP alert. Some findings may be false positives, especially the SQL Injection and Path Traversal alerts.

Copy and paste the following:

```text
TASK: Synbot Health VAPT Remediation — OWASP ZAP Security Findings

Context

Synbot Health has undergone an authenticated OWASP ZAP vulnerability assessment against the locally deployed HTTPS application.

The latest ZAP report identified:

- 2 High-risk alert categories
- 4 Medium-risk alert categories
- 13 Low-risk alert categories
- 9 Informational alert categories
- 28 total alert categories

The application contains sensitive hospital and patient information. Security changes must therefore prioritize confidentiality, integrity, availability, authentication security, authorization enforcement, auditability, and protection of patient data.

The objective is not to suppress ZAP warnings or make the report appear clean. The objective is to investigate each finding, confirm whether it represents a genuine vulnerability, remediate confirmed weaknesses safely, preserve existing application functionality, and document any false positives or accepted residual risks.

IMPORTANT OPERATING RULES

1. Do not blindly modify code based only on the ZAP severity rating.

2. Trace every finding to:
   - The affected frontend component
   - Backend route or API endpoint
   - Request parameter
   - Authentication and authorization dependency
   - Database query or ORM operation
   - Reverse-proxy or Nginx configuration
   - Relevant environment configuration

3. Before changing code, determine whether each finding is:
   - Confirmed vulnerability
   - Security weakness or hardening opportunity
   - False positive
   - Expected application behaviour
   - Accepted residual risk requiring documentation

4. Do not weaken authentication, authorization, validation, encryption, logging, Content Security Policy, browser security controls, or existing security middleware to eliminate scanner findings.

5. Do not expose secrets, passwords, access tokens, refresh tokens, session identifiers, WebSocket tickets, patient information, database credentials, or personally identifiable information in:
   - Logs
   - URLs
   - Browser storage
   - Error responses
   - Test output
   - Screenshots
   - Documentation

6. Preserve all existing clinical workflows and application functionality.

7. Make changes incrementally. Run relevant tests after each remediation group rather than applying all changes simultaneously.

8. Do not perform destructive database operations, delete production data, reset schemas, or alter migrations without first documenting the reason and impact.

9. Do not claim a vulnerability is resolved unless the affected endpoint has been retested.

==================================================
PHASE 1 — CREATE A SECURITY FINDINGS REGISTER
==================================================

Create a structured remediation register containing:

| ID | Finding | Severity | Confidence | Affected Endpoint(s) | Suspected Component | Validation Result | Root Cause | Remediation | Test Result | Status |

Use these status values:

- Not Investigated
- Under Investigation
- Confirmed
- False Positive
- Remediated
- Retest Passed
- Retest Failed
- Accepted Risk

Group the findings into:

P0 — Critical release blockers
P1 — High-priority security remediation
P2 — Security hardening
P3 — Informational review

Do not classify findings only by ZAP severity. Consider exploitability, affected data, authentication requirements, confidence level, and potential impact on patient information.

==================================================
PHASE 2 — INVESTIGATE HIGH-RISK FINDINGS
==================================================

A. SQL INJECTION

ZAP reported:

- Severity: High
- Instances: 21

Treat this as the highest-priority investigation.

For every affected endpoint:

1. Identify:
   - HTTP method
   - Route
   - Request parameter
   - Authentication requirement
   - User role required
   - Backend handler
   - Service or repository method
   - Database operation

2. Inspect all database access paths for:
   - Raw SQL
   - String concatenation
   - f-strings used to construct SQL
   - Percent formatting in SQL
   - `.format()` used in SQL
   - Dynamically generated WHERE clauses
   - Dynamically generated ORDER BY clauses
   - User-controlled table names
   - User-controlled column names
   - Unsafe stored procedures
   - Direct execution of unvalidated input

3. Confirm whether the application uses:
   - Parameterized queries
   - Prepared statements
   - SQLAlchemy or another ORM
   - Bound query parameters

4. Do not assume an endpoint is safe merely because it uses an ORM. Inspect any raw SQL or dynamic query construction.

5. For identifiers and filters:
   - Enforce strict server-side data types
   - Validate UUIDs as UUIDs
   - Validate integers as integers
   - Validate dates using strict date schemas
   - Validate enumerations against explicit allowed values
   - Reject malformed values with controlled 4xx responses

6. If dynamic sorting or filtering is supported:
   - Use an explicit allow-list of permitted fields
   - Never insert arbitrary client input into SQL syntax

7. Confirm whether each ZAP result demonstrates actual query manipulation or merely produces a generic error, timeout, proxy error, or 5xx response.

8. If the finding is a false positive:
   - Record the evidence
   - Explain why the query is not injectable
   - Document the parameter validation and parameterized query path
   - Add a regression test where appropriate

9. Add automated tests for confirmed or high-risk endpoints using:
   - Normal values
   - Invalid types
   - Quotes
   - SQL metacharacters
   - Boolean-style payloads
   - Encoded input
   - Unexpectedly long input

Expected result:

- No user-controlled input is concatenated into SQL.
- Malformed input returns a controlled 400 or 422 response.
- No SQL syntax, database engine details, stack traces, or internal errors are returned.
- Existing valid requests continue to work.

B. PATH TRAVERSAL

ZAP reported:

- Severity: High
- Confidence: Low
- Endpoint:
  GET /calendar/events?month=%2Fevents

Treat this as an investigation priority, but do not assume it is confirmed because ZAP confidence is low.

Perform the following:

1. Trace the `month` parameter through:
   - Route validation
   - Request schema
   - Business logic
   - Database query
   - File-system operations
   - Template loading
   - Static-file operations

2. Determine whether the value is ever used in:
   - File paths
   - Directory paths
   - File reads
   - File writes
   - Template names
   - Shell commands
   - Dynamic imports

3. If `month` is intended to represent a calendar month:
   - Replace unrestricted strings with a strict schema
   - Prefer an explicit format such as YYYY-MM
   - Reject values containing path separators or invalid characters
   - Return a controlled 400 or 422 response

4. Confirm whether the ZAP alert was caused only by malformed input producing an unusual response.

5. If no file-system operation exists:
   - Document the finding as a false positive or input-validation weakness
   - Still implement strict validation if the parameter currently accepts unrestricted input

Expected result:

- Invalid month values are rejected.
- No file-system path can be influenced by the parameter.
- Valid calendar requests continue to function.

==================================================
PHASE 3 — REMEDIATE MEDIUM-RISK FINDINGS
==================================================

A. CROSS-ORIGIN RESOURCE SHARING — CORS

ZAP identified overly permissive cross-origin behaviour on endpoints including:

- POST /token
- POST /refresh
- POST /realtime/ws-ticket
- Other affected API endpoints

Review all CORS configuration.

Requirements:

1. Remove wildcard origins from sensitive authenticated endpoints.

2. Use an environment-controlled allow-list such as:

ALLOWED_ORIGINS=https://approved-synbot-domain

3. Allow only approved frontend origins.

4. Do not combine:

Access-Control-Allow-Origin: *

with credentialed cross-origin requests.

5. Restrict:
   - Allowed methods
   - Allowed headers
   - Exposed headers

6. Do not use permissive development origins in production.

7. Ensure localhost origins are enabled only in development environments.

8. Test:
   - Approved origin
   - Unapproved origin
   - Missing Origin header
   - Preflight OPTIONS request
   - Authenticated request
   - Token refresh request
   - WebSocket ticket request

Expected result:

- Approved origins function normally.
- Unapproved origins do not receive permissive CORS authorization.
- Authentication and token refresh continue to work.

B. CONTENT SECURITY POLICY — CSP

ZAP reported:

- Missing CSP directives with no fallback
- `script-src 'unsafe-inline'`
- `style-src 'unsafe-inline'`
- Systemic findings across multiple routes

Review the CSP configuration.

Current policy includes approximately:

default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
connect-src 'self';
frame-ancestors 'none';

Required work:

1. Add explicit directives where appropriate:

default-src 'self';
base-uri 'self';
object-src 'none';
frame-ancestors 'none';
form-action 'self';

2. Investigate all inline JavaScript before removing:

'unsafe-inline'

from `script-src`.

3. Prefer:
   - External bundled JavaScript
   - CSP nonces
   - CSP hashes

4. Do not remove `unsafe-inline` without testing the complete frontend because this may break the application.

5. Review inline styles separately.

6. Remove `style-src 'unsafe-inline'` only if the frontend framework and component library support a safer configuration.

7. If inline styles are temporarily required:
   - Document the reason
   - Record the residual risk
   - Create a future hardening task

8. Verify:
   - Login
   - Dashboard
   - Patient pages
   - Encounter pages
   - Calendar
   - Laboratory pages
   - Specialist pages
   - Reports
   - Tasks
   - Maps
   - Real-time features

Expected result:

- CSP is stricter without breaking the application.
- Required directives are explicitly defined.
- Any remaining unsafe directive is documented.

==================================================
PHASE 4 — COOKIE AND SESSION SECURITY
==================================================

Investigate:

- Cookie No HttpOnly Flag
- Cookie Without Secure Flag
- Cookie with SameSite=None
- Cookie without SameSite Attribute
- Loosely Scoped Cookie

For every application cookie, document:

- Cookie name
- Purpose
- Creator
- Domain
- Path
- Secure status
- HttpOnly status
- SameSite status
- Expiration
- Whether JavaScript requires access

Apply secure defaults where compatible:

Secure = true
HttpOnly = true
SameSite = Lax or Strict
Path = narrowest valid application path

Requirements:

1. Authentication and session cookies must use `Secure` in production.

2. Authentication and session cookies should use `HttpOnly` unless JavaScript access is strictly required and justified.

3. Explicitly define `SameSite`.

4. Use `SameSite=None` only when cross-site behaviour is genuinely required and always pair it with `Secure`.

5. Do not apply cookies to unnecessarily broad domains or paths.

6. Confirm:
   - Login
   - Logout
   - Token refresh
   - Session expiry
   - Role switching, if supported
   - Browser refresh
   - Multi-tab behaviour

==================================================
PHASE 5 — TOKEN AND BROWSER-STORAGE SECURITY
==================================================

ZAP detected sensitive authentication-related values in browser storage and URLs.

Review:

- Access-token storage
- Refresh-token storage
- localStorage
- sessionStorage
- WebSocket ticket handling
- Query-string authentication data

Important:

The ZAP report itself contains captured token-like values. Treat all tokens captured during testing as compromised test credentials and invalidate the related sessions.

Requirements:

1. Determine why refresh tokens are stored in localStorage.

2. Assess migration of refresh tokens to:

Secure + HttpOnly + explicitly configured SameSite cookies

3. Do not expose refresh tokens to frontend JavaScript unless required by the architecture and formally justified.

4. Keep access tokens:
   - Short-lived
   - Minimally exposed
   - Out of persistent browser storage where feasible

5. Review WebSocket tickets passed through query strings.

6. If query-string tickets are required for browser WebSocket authentication:
   - Make them single-use
   - Give them a very short lifetime
   - Bind them to the intended user and channel
   - Prevent replay
   - Redact them from logs
   - Avoid storing them in browser history
   - Ensure they cannot be reused after successful connection

7. Ensure:
   - Logout invalidates refresh tokens
   - Refresh-token rotation is enforced
   - Reuse of an old refresh token is rejected
   - Expired tokens are rejected
   - Revoked sessions cannot reconnect to real-time services

==================================================
PHASE 6 — HTTP SECURITY HEADERS
==================================================

Investigate and remediate:

- Strict-Transport-Security disabled
- Strict-Transport-Security header missing
- X-Content-Type-Options missing
- Server version disclosure
- X-Powered-By disclosure
- ASP.NET version disclosure
- Private IP disclosure
- In-page banner information leakage

Review headers at every relevant layer:

- Frontend server
- Backend application
- Nginx reverse proxy
- Load balancer
- Error responses
- Static-file responses

Apply production-safe security headers where appropriate:

Strict-Transport-Security:
max-age=31536000; includeSubDomains

X-Content-Type-Options:
nosniff

Referrer-Policy:
strict-origin-when-cross-origin

X-Frame-Options:
DENY

or enforce equivalent protection using:

Content-Security-Policy:
frame-ancestors 'none'

Permissions-Policy:
Disable browser capabilities not required by Synbot Health.

Important:

1. Enable HSTS only after confirming production HTTPS is correctly configured.

2. Do not enable HSTS on an environment that still requires HTTP access.

3. Do not use HSTS preload unless all requirements are understood and approved.

4. Remove or suppress unnecessary headers such as:
   - Server version
   - X-Powered-By
   - X-AspNet-Version

5. Configure custom error pages so 4xx and 5xx responses do not reveal:
   - Nginx version
   - Framework version
   - Internal IP addresses
   - Hostnames
   - Stack traces
   - Database details

6. Verify headers on:
   - Successful responses
   - Authentication failures
   - Validation errors
   - 404 responses
   - 500 responses
   - Static assets
   - API responses

==================================================
PHASE 7 — INFORMATIONAL FINDINGS
==================================================

Review but do not automatically modify:

- Authentication Request Identified
- Content-Type Header Missing
- Information in localStorage
- Information in sessionStorage
- Sensitive Information in URL
- Modern Web Application
- Cache-control directives
- Session Management Response Identified
- Timestamp Disclosure

For each finding:

1. Determine whether sensitive information is exposed.

2. Confirm whether the behaviour is expected.

3. Add appropriate Content-Type headers where missing.

4. Ensure authenticated patient and clinical responses use suitable cache controls, such as:

Cache-Control: no-store

where appropriate.

5. Do not remove timestamps that are required for:
   - Clinical records
   - Encounter history
   - Audit trails
   - Security events

6. Only remediate timestamp findings if they expose unnecessary internal implementation details.

7. Record harmless scanner observations as informational or accepted risk rather than making unnecessary code changes.

==================================================
PHASE 8 — ERROR HANDLING AND LOGGING
==================================================

Review application-wide error handling.

Requirements:

1. Client responses must not expose:
   - Stack traces
   - SQL errors
   - Database names
   - Table names
   - Internal file paths
   - Internal IP addresses
   - Framework versions
   - Secrets or tokens

2. Return controlled errors:

400 — Invalid request
401 — Authentication required
403 — Access denied
404 — Resource not found
409 — Conflict
422 — Validation failed
429 — Rate limit exceeded
500 — Generic internal server error

3. Keep detailed diagnostic information only in protected server logs.

4. Redact:
   - Authorization headers
   - Passwords
   - Access tokens
   - Refresh tokens
   - Session identifiers
   - WebSocket tickets
   - Patient identifiers where unnecessary

5. Preserve security-relevant audit events without logging sensitive payloads.

==================================================
PHASE 9 — REGRESSION AND SECURITY TESTING
==================================================

After remediation, run:

1. Existing unit tests

2. Existing integration tests

3. Authentication tests:
   - Valid login
   - Invalid login
   - Logout
   - Token refresh
   - Expired token
   - Revoked token
   - Refresh-token rotation

4. Authorization tests:
   - Unauthenticated access
   - Incorrect role
   - Cross-user access
   - Cross-patient access
   - Direct API access

5. Clinical workflow tests:
   - Patient registration
   - Patient search
   - Appointment creation
   - Encounter creation
   - Encounter progression
   - Clinical notes
   - Laboratory workflow
   - Prescriptions
   - Billing
   - Encounter completion
   - Historical record retrieval

6. Security regression tests:
   - SQL injection probes
   - Invalid parameter types
   - Path-like input
   - Unauthorized object access
   - CORS requests from unapproved origins
   - Missing and malformed tokens
   - Replayed WebSocket tickets
   - Cookie-security validation
   - Security-header validation

7. Run a new authenticated OWASP ZAP scan.

8. Compare the new report with the baseline report.

Do not mark the security review complete merely because the total alert count decreases.

==================================================
REQUIRED FINAL DELIVERABLE
==================================================

Produce a final report containing:

1. Executive summary

2. Baseline:
   - 28 alert categories
   - 2 High
   - 4 Medium
   - 13 Low
   - 9 Informational

3. Findings table:

| Finding | Original Severity | Validation | Root Cause | Change Applied | Retest Result | Final Status |

4. Confirmed vulnerabilities

5. False positives with evidence

6. Security hardening changes

7. Files modified

8. Configuration and environment-variable changes

9. Database or migration changes

10. Tests added

11. Test results

12. Updated ZAP comparison

13. Remaining risks

14. Deferred work

15. Production deployment considerations

16. Rollback instructions

17. Final release recommendation:

- APPROVED
- APPROVED WITH DOCUMENTED RISKS
- NOT APPROVED

Do not declare the application production-ready if:

- A confirmed SQL injection vulnerability remains
- A confirmed path traversal vulnerability remains
- Authentication or authorization tests fail
- Patient data can be accessed across unauthorized users or roles
- Sensitive tokens remain unnecessarily exposed
- Critical clinical workflows fail after remediation

Begin by producing the security findings register and investigation plan. Do not modify code until the affected routes, parameters, query paths, authentication dependencies, and configuration layers have been identified.
```

This should give the coding agent enough structure to work through the findings without creating rushed fixes. The most important part is that it forces the agent to **validate the 21 SQL Injection alerts and the low-confidence Path Traversal alert before changing application logic**, while still treating them as release blockers until investigated.
