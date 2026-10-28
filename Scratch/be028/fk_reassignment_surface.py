"""BE-028 §11/§25 evidence for the B-1 remediation plan (read-only).

Two things BE-029 needs and BE-028 must not guess at:

1. every foreign key that points at users(id), with its ON DELETE rule -- this
   is the reassignment surface;
2. for each of those, how many rows actually reference one of the duplicate
   user ids, i.e. how much data a merge would have to move.

Runs SELECTs only. Safe against any database; intended for pofa_test / pofa_dev.
"""
import sys

from sqlalchemy import create_engine, text

engine = create_engine(sys.argv[1])
DUP = "testuser"

with engine.connect() as c:
    fks = c.execute(text("""
        SELECT conname,
               conrelid::regclass AS child_table,
               (SELECT string_agg(att.attname, ',' ORDER BY k.ord)
                  FROM unnest(conkey) WITH ORDINALITY AS k(attnum, ord)
                  JOIN pg_attribute att
                    ON att.attrelid = conrelid AND att.attnum = k.attnum) AS child_cols,
               confdeltype
        FROM pg_constraint
        WHERE contype='f' AND confrelid = 'users'::regclass
        ORDER BY 2
    """)).mappings().all()

    dup_ids = [r[0] for r in c.execute(
        text("SELECT id FROM users WHERE username = :u ORDER BY created_at"), {"u": DUP}
    )]
    print(f"DATABASE {sys.argv[1].rsplit('/', 1)[-1]}")
    print(f"duplicate user rows for username={DUP!r}: {len(dup_ids)}")
    print(f"foreign keys referencing users(id): {len(fks)}\n")
    print(f"{'child table':<34} {'cols':<12} {'on delete':<10} rows referencing a duplicate")
    del_rule = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE",
                "n": "SET NULL", "d": "SET DEFAULT"}
    total = 0
    for fk in fks:
        rule = del_rule.get(fk["confdeltype"], fk["confdeltype"])
        cols = fk["child_cols"]
        try:
            n = c.execute(text(
                f'SELECT count(*) FROM {fk["child_table"]} '
                f'WHERE "{cols}" = ANY(:ids)'
            ), {"ids": dup_ids}).scalar()
        except Exception as exc:  # composite FK keys: count all component columns
            c.rollback()
            first = cols.split(",")[0]
            n = c.execute(text(
                f'SELECT count(*) FROM {fk["child_table"]} '
                f'WHERE "{first}" = ANY(:ids)'
            ), {"ids": dup_ids}).scalar()
            n = f"{n} (composite on {cols}, counted on {first})"
        print(f"{str(fk['child_table']):<34} {cols:<12} {rule:<10} {n}")
        if isinstance(n, int):
            total += n
    print(f"\nTOTAL single-column referencing rows: {total}")
engine.dispose()
