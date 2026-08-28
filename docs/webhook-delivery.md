# Webhook alert delivery

OilSignal includes a vendor-neutral HTTP webhook adapter for durable alert outbox rows. It sits after policy evaluation, edge-trigger state, transactional enqueue, leasing, backoff, and dead-letter handling.

The adapter does **not** change alert semantics. It transports the serialized `PolicyEvaluation` already stored in the outbox.

## Delivery guarantee

OilSignal remains **at least once** across the local database and an external HTTP receiver.

A worker can crash after the receiver accepts a request but before OilSignal records the local acknowledgement. When the lease expires, that outbox row can be retried. The webhook contract therefore gives every attempt for one row the same durable identity:

```text
Idempotency-Key: <outbox_id>
X-OilSignal-Outbox-ID: <outbox_id>
```

A receiver that wants effectively-once processing should persist the `outbox_id` in the same transaction as its side effect. If the same ID is received again, return the same successful 2xx outcome without performing the side effect again.

OilSignal cannot make an arbitrary network call exactly once by itself.

## Transport and authentication

Webhook URLs must use HTTPS by default. Plain HTTP is rejected unless `OILSIGNAL_ALERT_WEBHOOK_ALLOW_INSECURE_HTTP=true` is explicitly configured.

Do not place credentials in the webhook URL. User-info credentials such as `https://user:password@example.test/hook` are rejected.

Optional bearer authentication is configured only through the environment:

```bash
export OILSIGNAL_ALERT_WEBHOOK_BEARER_TOKEN='...'
```

When configured, OilSignal sends:

```text
Authorization: Bearer <token>
```

Optional HMAC authentication is also environment-only:

```bash
export OILSIGNAL_ALERT_WEBHOOK_SIGNING_SECRET='...'
```

The signature is deterministic across retries for the same raw body and outbox ID:

```text
message = "<outbox_id>.<raw_request_body>"
signature = HMAC-SHA256(signing_secret, message)
X-OilSignal-Signature: sha256=<lowercase hex digest>
```

Receivers should verify the signature with a constant-time comparison against the **raw request body** before parsing JSON.

## Configuration

```bash
export OILSIGNAL_ALERT_WEBHOOK_URL='https://alerts.example.test/oilsignal'
export OILSIGNAL_ALERT_WEBHOOK_BEARER_TOKEN='optional-bearer-token'
export OILSIGNAL_ALERT_WEBHOOK_SIGNING_SECRET='optional-hmac-secret'
export OILSIGNAL_ALERT_WEBHOOK_TIMEOUT_SECONDS=10
```

The endpoint itself may be overridden on the CLI because it is not treated as a secret:

```bash
oilsignal alerts-deliver \
  --adapter webhook \
  --webhook-url https://alerts.example.test/oilsignal \
  --data-dir ./data
```

Bearer and signing secrets intentionally have no CLI flags so they are not exposed in shell history or process arguments.

For intentional local HTTP testing only:

```bash
export OILSIGNAL_ALERT_WEBHOOK_URL='http://localhost:9000/oilsignal'
export OILSIGNAL_ALERT_WEBHOOK_ALLOW_INSECURE_HTTP=true
```

## Receiver response contract

Any 2xx response acknowledges delivery. Redirects are not followed automatically. Non-2xx responses and transport failures enter the existing retry/backoff/dead-letter path.

A receiver should:

1. require HTTPS in production;
2. verify bearer and/or HMAC authentication before acting;
3. read `Idempotency-Key` / `X-OilSignal-Outbox-ID`;
4. atomically deduplicate the outbox ID with the receiver-side effect;
5. return 2xx for both first processing and recognized duplicates;
6. return a non-2xx status for retryable or permanent processing failures according to its own policy.

OilSignal stores bounded delivery errors, but authentication secrets are never inserted into the request URL and are not included in normal HTTP error messages.

## Example receiver pseudocode

```text
raw_body = request.raw_body
outbox_id = request.header["Idempotency-Key"]
verify_hmac(outbox_id + "." + raw_body)

begin transaction
  if processed_outbox_ids contains outbox_id:
    commit
    return 204

  perform_side_effect(raw_body)
  insert processed_outbox_ids(outbox_id)
commit
return 204
```

The receiver-side atomic transaction is what prevents a duplicate retry from becoming a duplicate notification. The sender-side header alone is only the stable identity needed to implement that behavior.
