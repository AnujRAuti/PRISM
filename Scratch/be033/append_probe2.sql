INSERT INTO audit_ledger_events
  (id, sequence_number, event_type, action, resource_type, payload, metadata,
   previous_hash, event_hash, hash_algorithm, ledger_version, created_at)
SELECT gen_random_uuid(),
       (SELECT max(sequence_number)+1 FROM audit_ledger_events),
       'USER_LOGIN', 'login', 'user', '{}'::json, '{}'::json,
       '0000000000000000000000000000000000000000000000000000000000000000',
       '1111111111111111111111111111111111111111111111111111111111111111',
       'SHA-256', 'audit-v1', now();
SELECT 'append_ok rows='||count(*)||' max_seq='||max(sequence_number) FROM audit_ledger_events;
