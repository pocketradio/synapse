# Northstar Commerce Architecture

## Checkout flow

`CheckoutService` validates the cart, creates an order, and calls `PaymentService.processPayment()`.

## Payment failure recovery

When payment fails, `CheckoutService` records the failed attempt in PostgreSQL and schedules a retry through `PaymentRetryQueue`. Retries use exponential backoff and stop after three attempts.

## Caching

`CheckoutService` uses Redis for short-lived cart lookup. Redis is a performance cache, not the source of truth for orders.

## Conflict note

The operations runbook says payment retries stop after five attempts. The service design says three attempts. This conflict must be surfaced rather than silently resolved.
