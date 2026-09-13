from sqlalchemy import inspect
from backend.db.session import get_engine

eng = get_engine()
insp = inspect(eng)
print('tables:', insp.get_table_names())
for t in insp.get_table_names():
    print('indexes for', t, insp.get_indexes(t))
