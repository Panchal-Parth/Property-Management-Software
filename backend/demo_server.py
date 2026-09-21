"""Run fictional leases and payments in an isolated, temporary workspace.

Build the frontend first, then run this script and open http://127.0.0.1:8012.
Stopping the server discards the demo database; real owner data is never read.
"""
import os
import secrets
import tempfile
from datetime import date


def seed_demo(c):
    if c.execute('SELECT 1 FROM properties').fetchone():
        raise ValueError('Demo seeding requires an empty portfolio.')
    today = date.today()
    month = today.strftime('%Y-%m')
    p = c.execute("INSERT INTO properties(name,address,kind,notes) VALUES('DEMO — Sample Building','100 Example Lane','Apartment','Fictional test data only')").lastrowid
    for i, (name, paid, note) in enumerate([
        ('Demo Alex', 200000, 'Paid in full on the 5th.'),
        ('Demo Jordan', 100000, 'Half paid on the 5th. Remaining half promised on the 20th.'),
        ('Demo Taylor', 0, 'No payment received yet. Follow up on the 10th.'),
    ], 1):
        t = c.execute('INSERT INTO tenants(name,email,notes) VALUES(?,?,?)', (name,f'demo{i}@example.test','Fictional tenant')).lastrowid
        u = c.execute('INSERT INTO units(property_id,label,tenant_id,expected_rent_cents) VALUES(?,?,?,?)', (p,f'Demo {i}',t,200000)).lastrowid
        lease = c.execute('INSERT INTO leases(unit_id,start_date,end_date,rent_cents,deposit_cents,notes) VALUES(?,?,?,?,?,?)',
                          (u,f'{today.year}-01-01',f'{today.year}-12-31',200000,0,'Fictional demo lease')).lastrowid
        c.execute('INSERT INTO lease_tenants VALUES(?,?)',(lease,t))
        record = c.execute('INSERT INTO monthly_records(property_id,unit_id,month,expected_rent_cents,notes) VALUES(?,?,?,?,?)', (p,u,month,200000,note)).lastrowid
        c.executemany('INSERT INTO monthly_amounts VALUES(?,?,?)', [(record,k,paid if k == 1 else 2500 if k == 2 else 0) for k in range(1,7)])


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='havenly-demo-') as folder:
        os.environ['HAVENLY_DATA_DIR'] = folder
        os.environ['HAVENLY_ENV'] = 'development'
        os.environ['HAVENLY_ORIGIN'] = 'http://127.0.0.1:8012'
        from db import migrate, connect, BASE
        if not (BASE.parent / 'frontend/dist/index.html').is_file():
            raise SystemExit('Run npm run build in frontend first.')
        from security import password_hash
        migrate()
        password = secrets.token_urlsafe(18)
        with connect() as c:
            c.execute('INSERT INTO owners(id,email,name,password_hash) VALUES(1,?,?,?)', ('demo@example.test','DEMO — Fictional Workspace',password_hash(password)))
            seed_demo(c)
        print('\nDEMO ONLY: http://127.0.0.1:8012\nEmail: demo@example.test\nTemporary password:', password, flush=True)
        import uvicorn
        uvicorn.run('main:app',host='127.0.0.1',port=8012)
