"""Local server-owner recovery; passwords are entered without echo."""
import argparse
import getpass
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.security import auth_store as store

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('username')
args=parser.parse_args()
row=store.account_for_username(args.username)
if not row:
    raise SystemExit('Account not found')
password=getpass.getpass('New password (12+ characters): ')
if password!=getpass.getpass('Confirm new password: '):
    raise SystemExit('Passwords did not match')
store.save_account(row['profile_id'],row['username'],password)
print('Password updated. Existing sessions were revoked.')
