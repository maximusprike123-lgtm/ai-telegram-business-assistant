# Phase 6 consent, qualification, and handoff runbook

## Northstar workflow

Northstar Auto Care is fictional. `Request service` or `/qualify` starts the published
`service_request` schema. The customer must accept consent version `northstar-demo-v1` for the
stated fictional request purpose before an answer is stored. Decline terminates the session and
creates no lead. The flow asks one missing required field at a time, validates immediately, then
shows a review with individual edit controls and a masked phone value.

The seeded score rules are deterministic. Urgency and whether the vehicle is movable contribute to
a 0–100 score and A/B/C grade. Accident, fire, fuel-leak, or not-drivable answers create an urgent
handoff. This is routing policy, not a diagnosis or safety determination.

## Handoff behavior

`Human help` creates or reuses an open explicit-request case. Unstructured unsupported input also
routes to a person because no general chatbot is enabled. Response due time counts only effective
business intervals from the Northstar schedule. Queued, claimed, and reopened cases pause booking,
qualification, navigation, and free-form bot replies; Privacy, Help, and handoff status remain
available.

Authenticated agents, managers, and owners can list open cases and apply `claim`, `resolve`,
`reopen`, or `return_to_bot` through `/api/v1/handoffs`. Every action is audited. Only a resolved
case can return bot control. Qualification schema versions can be listed by read roles and created
or published by managers/owners through `/api/v1/qualification-schemas`.

## Delivery and recovery boundary

Lead completion and handoff creation enqueue PII-minimized, deterministic outbox events in the
same transaction. No notification is claimed as sent: subscriptions, Telegram admin delivery,
retry, dead-letter handling, and workers are Phase 10. Operators may inspect PostgreSQL records and
outbox state through controlled database access; there is no manual delivery command in Phase 6.

Expired sessions are rejected and marked on the next read. Scheduled cleanup, retention,
anonymization, transcript summaries, AI extraction, and automatic repeated-failure/provider-outage
triggers are deferred. Never use the fictional consent or safety wording unchanged in production;
the owner must approve lawful basis, retention, escalation recipients, and emergency language.
