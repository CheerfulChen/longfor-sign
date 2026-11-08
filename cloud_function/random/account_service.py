"""Random scheduling adapter; account execution uses the common core."""
from core.accounts import load_accounts
from core.service import execute_persisted


def account_ids():
    return [account['id'] for account in load_accounts()]


def app_settings(accounts):
    configured=load_accounts()
    if len(configured)!=len(accounts):raise ValueError('账号配置数量不匹配')
    return ([a['id'] for a in configured],[a['id'] for a in configured if a['app_enabled']],
            [a['app_risk'] for a in configured])


def execute_account(store, accounts, index):
    account=load_accounts()[index]
    if (account['token'],account['risk'],account['name'])!=tuple(accounts[index]):
        raise ValueError('执行期间账号配置已变更')
    return execute_persisted(store,account)
