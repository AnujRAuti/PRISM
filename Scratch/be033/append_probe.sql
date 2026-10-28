INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, resource_type, payload, created_at)
SELECT gen_random_uuid(),
       (SELECT max(sequence_number)+1 FROM audit_ledger_events),
       'HEALTH_CHECK', 'be033_runtime_append', 'ledger_probe', '{}'::json, now();
SELECT 'rows_after='||count(*) FROM audit_ledger_events;
SELECT 'max_seq='||max(sequence_number) FROM audit_ledger_events;
