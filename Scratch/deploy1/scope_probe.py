import sys
sys.path.insert(0, r"D:\CODING\Scratch\deploy1")

import psycopg2
from armfull import arm_env

url = arm_env()["TEST_DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
conn = psycopg2.connect(url)
conn.set_session(readonly=True)
cur = conn.cursor()

cur.execute("select count(*) from retention_holds")
h = cur.fetchone()[0]
cur.execute("select count(*) from retention_holds "
            "where project_id is null and organization_id is null")
hn = cur.fetchone()[0]
cur.execute("select scope, count(*) from retention_holds group by scope order by 1")
hs = cur.fetchall()
cur.execute("select scope_type, count(*) from retention_policies group by scope_type order by 1")
ps = cur.fetchall()
cur.execute("select count(*) from api_clients")
ac = cur.fetchone()[0]
cur.execute("select count(*) from api_clients where project_id is null")
acn = cur.fetchone()[0]
cur.execute("select count(*) from external_systems")
es = cur.fetchone()[0]
cur.execute("select count(*) from external_systems where organization_id is null")
esn = cur.fetchone()[0]

print("holds total=%d  both-scope-NULL=%d  by_scope=%s" % (h, hn, hs))
print("policies by_scope_type=%s" % (ps,))
print("api_clients total=%d project_id_NULL=%d | external_systems total=%d org_NULL=%d"
      % (ac, acn, es, esn))
cur.close()
conn.close()
