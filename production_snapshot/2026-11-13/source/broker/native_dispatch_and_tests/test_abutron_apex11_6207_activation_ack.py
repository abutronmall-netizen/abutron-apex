#!/usr/bin/python3
import importlib.util,sqlite3,tempfile,unittest
from pathlib import Path
P='/var/lib/abutron-mcp/abutron-apex11-6207-activation-ack.py'
s=importlib.util.spec_from_file_location('activation',P)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
CID=m.CID

class ActivationQA(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='apex11-activation-qa-')
  m.DB=str(Path(self.tmp.name)/'sandbox.sqlite3')
  self.real_inspect=m.inspect
  m.inspect=lambda:(True,'APEX11_NATIVE_DEMO_PROVEN')
  c=sqlite3.connect(m.DB)
  c.executescript('''
    CREATE TABLE accounts(id TEXT PRIMARY KEY,status TEXT);
    CREATE TABLE apex_mt5_connections(id TEXT PRIMARY KEY,account_id TEXT,broker TEXT,
      environment TEXT,account_reference TEXT,broker_server TEXT,status TEXT);
    CREATE TABLE apex_trade_controls(connection_id TEXT PRIMARY KEY,desired_enabled INTEGER,
      effective_enabled INTEGER,updated_at INTEGER,last_error TEXT);
    CREATE TABLE abutron_v4_6207_activation_revision(connection_id TEXT PRIMARY KEY,
      revision INTEGER,desired_enabled INTEGER,effective_enabled INTEGER,connection_status TEXT,
      ack_revision INTEGER,ack_expires_utc INTEGER,updated_utc TEXT,last_event TEXT);
    CREATE TABLE apex_trade_control_audit(account_id TEXT,connection_id TEXT,
      requested_enabled INTEGER,outcome TEXT,occurred_at INTEGER);
    CREATE TRIGGER fence AFTER UPDATE ON apex_trade_controls
    WHEN NEW.desired_enabled!=OLD.desired_enabled OR NEW.effective_enabled!=OLD.effective_enabled
    BEGIN
      UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,
      desired_enabled=NEW.desired_enabled,effective_enabled=NEW.effective_enabled,
      ack_revision=NULL,ack_expires_utc=NULL
      WHERE connection_id=NEW.connection_id;
    END;
    INSERT INTO accounts VALUES('owner','approved');
    INSERT INTO apex_mt5_connections VALUES('d6fc2524ec373b8d1bc278a8be3ec635',
      'owner','Deriv','DEMO','32456207','Deriv-Demo','CONNECTED');
    INSERT INTO apex_trade_controls VALUES('d6fc2524ec373b8d1bc278a8be3ec635',1,0,10,NULL);
    INSERT INTO abutron_v4_6207_activation_revision VALUES('d6fc2524ec373b8d1bc278a8be3ec635',
      71,1,0,'CONNECTED',NULL,NULL,'before','OFF');
  ''')
  c.commit();c.close()
 def tearDown(self):
  m.inspect=self.real_inspect
  self.tmp.cleanup()
 def query(self,sql):
  with sqlite3.connect(m.DB) as c:return c.execute(sql).fetchone()
 def test_first_activation_revision_ack_but_no_broker_ack(self):
  x=m.activate()
  self.assertEqual(x['state'],'ACTIVATED_DEMO')
  self.assertTrue(x['activation_revision_ack'])
  self.assertFalse(x['broker_execution_ack'])
  self.assertEqual(self.query('SELECT desired_enabled,effective_enabled FROM apex_trade_controls'),(1,1))
  self.assertEqual(self.query('SELECT revision,ack_revision FROM abutron_v4_6207_activation_revision'),(72,72))
 def test_ack_refresh_does_not_bump_revision(self):
  m.activate();m.activate()
  self.assertEqual(self.query('SELECT revision,ack_revision FROM abutron_v4_6207_activation_revision'),(72,72))
 def test_risk_unverified_revokes_on_and_fences(self):
  m.activate();m.inspect=lambda:(False,'NATIVE_OWNER_RISK_UNVERIFIED')
  x=m.activate()
  self.assertEqual(x['state'],'DEACTIVATED_DEMO')
  self.assertEqual(self.query('SELECT desired_enabled,effective_enabled FROM apex_trade_controls'),(1,0))
  self.assertEqual(self.query('SELECT revision,ack_revision FROM abutron_v4_6207_activation_revision'),(73,None))
 def test_desired_off_is_not_overridden(self):
  with sqlite3.connect(m.DB) as c:
   c.execute('UPDATE apex_trade_controls SET desired_enabled=0')
  x=m.activate();self.assertFalse(x['effective_demo_on'])
  self.assertEqual(self.query('SELECT desired_enabled,effective_enabled FROM apex_trade_controls'),(0,0))
 def test_live_mode_refused(self):
  with sqlite3.connect(m.DB) as c:
   c.execute("UPDATE apex_mt5_connections SET environment='LIVE'")
  x=m.activate();self.assertFalse(x['effective_demo_on'])
 def test_no_revoke_on_effective_off(self):
  m.inspect=lambda:(False,'SOURCE_UNVERIFIED')
  x=m.activate();self.assertEqual(x['state'],'UNCHANGED')
  self.assertEqual(self.query('SELECT revision,ack_revision FROM abutron_v4_6207_activation_revision'),(71,None))
if __name__=='__main__':unittest.main(verbosity=2)
