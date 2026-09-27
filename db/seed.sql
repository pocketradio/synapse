INSERT INTO sources (id, name, source_type, uri)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'Architecture', 'file', 'corpus/northstar/architecture.md'),
    ('00000000-0000-0000-0000-000000000002', 'Payment service', 'file', 'corpus/northstar/payment_service.py'),
    ('00000000-0000-0000-0000-000000000003', 'Service configuration', 'file', 'corpus/northstar/service_config.json'),
    ('00000000-0000-0000-0000-000000000004', 'Checkout runbook', 'file', 'corpus/northstar/checkout.html'),
    ('00000000-0000-0000-0000-000000000005', 'Operations PDF', 'file', 'corpus/northstar/operations.pdf')
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_revisions (id, source_id, content_hash, mime_type, revision_number)
VALUES
    ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'northstar-architecture-v1', 'text/markdown', 1),
    ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'northstar-payment-v1', 'text/x-python', 1),
    ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000003', 'northstar-config-v1', 'application/json', 1),
    ('10000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000004', 'northstar-checkout-v1', 'text/html', 1),
    ('10000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000005', 'northstar-operations-v1', 'application/pdf', 1)
ON CONFLICT (id) DO NOTHING;

INSERT INTO chunks (id, revision_id, ordinal, content, locator)
VALUES
    ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 1,
     'CheckoutService uses Redis for short-lived cart lookup. Redis is a performance cache, not the source of truth for orders.',
     '{"kind":"heading","heading":"Caching","line_start":11,"line_end":13}'),
    ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 2,
     'When payment fails, CheckoutService records the failed attempt in PostgreSQL and schedules a retry through PaymentRetryQueue.',
     '{"kind":"heading","heading":"Payment failure recovery","line_start":7,"line_end":9}'),
    ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', 1,
     'def processPayment(self, order_id: str, amount_cents: int) -> str:',
     '{"kind":"code_symbol","symbol":"PaymentService.processPayment","line_start":4,"line_end":8}'),
    ('20000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000003', 1,
     'The payment retry configuration sets max_attempts to 3 and backoff to exponential.',
     '{"kind":"json_path","path":"$.payment.retry","line_start":7,"line_end":10}'),
    ('20000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000005', 1,
     'The operations procedure permits up to five payment attempts before escalation.',
     '{"kind":"pdf","page":1,"paragraph":2}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO entities (id, name, entity_type)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'CheckoutService', 'service'),
    ('30000000-0000-0000-0000-000000000002', 'Redis', 'technology'),
    ('30000000-0000-0000-0000-000000000003', 'PaymentRetryQueue', 'queue'),
    ('30000000-0000-0000-0000-000000000004', 'PostgreSQL', 'technology')
ON CONFLICT (id) DO NOTHING;

INSERT INTO relationships (id, subject_id, predicate, object_id, evidence_chunk_id, confidence)
VALUES
    ('40000000-0000-0000-0000-000000000002',
     '30000000-0000-0000-0000-000000000001', 'uses', '30000000-0000-0000-0000-000000000002',
     '20000000-0000-0000-0000-000000000001', 1.0),
    ('40000000-0000-0000-0000-000000000001',
     '30000000-0000-0000-0000-000000000001', 'schedules', '30000000-0000-0000-0000-000000000003',
     '20000000-0000-0000-0000-000000000002', 1.0)
ON CONFLICT (id) DO NOTHING;
