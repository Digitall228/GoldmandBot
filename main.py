import datetime
import time
from typing import List
import requests
import pytz
import eospy.cleos
import eospy.keys
from colorama import Fore, Back, Style, init
from account import Account
import json
import traceback
import threading
import requests

init(autoreset=True)

accounts = [
            # You accounts
            ]

ce = eospy.cleos.Cleos(url='https://wax.pink.gg') # or https://wax.cryptolions.io

def log_add(text, color):
    print(f'{datetime.datetime.utcnow()}: {color}{text}')

def send_request(action, max_times, *args):
    times = 0
    try:
        if len(args) <= 1:
            r = action(args[0])
        elif len(args) == 2:
            r = action(args[0], json=args[1])
        js = json.loads(r.text)
        return js
    except Exception as ex:
        times += 1
        if times >= max_times:
            return None
        time.sleep(3)

def build_transaction(account, contract, action_name, data):
    payload = {
        "account": contract,
        "name": action_name,
        "authorization": [{
            "actor": account,
            "permission": "active",
        }],
    }

    data = ce.abi_json_to_bin(payload['account'], payload['name'], data)
    # Inserting payload binary form as "data" field in original payload
    payload['data'] = data['binargs']
    # final transaction formed
    trx = {"actions": [payload]}
    trx['expiration'] = str(
        (datetime.datetime.utcnow() + datetime.timedelta(seconds=60)).replace(tzinfo=pytz.UTC))

    return trx

def push_transaction(trx, key):
    try:
        resp = ce.push_transaction(trx, key, broadcast=True)
    except:
        log_add(f'Push transaction failed: {traceback.format_exc()}', Fore.RED)
        return False

    if resp['processed']['receipt']['status'] == 'executed':
        return True
    else:
        return False

def parse_miner_info(account):
    result = ce.get_table(code='goldmandgame', key_type='i64', limit=1,
                          lower_bound=account.account_name, scope='goldmandgame', table='miners',
                          upper_bound=account.account_name)
    account.miner_info = result['rows'][0]
    parse_inventory(account)
    log_add(f'[{account.account_name}] \n'
            f'GMD: {float(account.miner_info["goldmand"])/10000}\n'
            f'GMM: {float(account.miner_info["minerals"])/10000}\n'
            f'GME: {float(account.miner_info["energy"])/10000}\n'
            f'GMF: {float(account.miner_info["food"])/10000}', Fore.LIGHTYELLOW_EX)

def parse_inventory(account):
    result = ce.get_table(code='goldmandgame', key_type='i64', limit=100,
                          lower_bound="", scope=account.account_name, table='inventory',
                          upper_bound="", index_position=1)

    account.miner_info['inventory'] = []
    for tool in result['rows']:
        account.miner_info['inventory'].append(tool["tool_asset_id"])

def parse_asset_info(asset_id):
    js = send_request(requests.get, 3, f'https://wax.api.atomicassets.io/atomicassets/v1/assets/{asset_id}')
    return js

def parse_template_id(asset_id):
    js = parse_asset_info(asset_id)
    return js['data']['template']['template_id']

def find_account(account_name):
    for account in accounts:
        if account.account_name == account_name:
            return account
    return None

def calculate(hero, land, tools):
    data = {"hero": hero, "land": land, "tools": tools, "stakedGmd": None,
            "stakedPlanetResource": None, "supplyCenterResource": None, "chance": None}
    js = send_request(requests.post, 3, 'https://goldmand.tools/api/calculate', data)
    return js

def calculate_mining_time(account):
    hero = parse_template_id(account.miner_info['hero'])
    land = parse_template_id(account.miner_info['land'])
    tools = []
    for tool in account.miner_info['inventory']:
        if tool != 0:
            tools.append(parse_template_id(tool))
    calculate_info = calculate(hero, land, tools)
    return account.miner_info['last_mine'] + calculate_info['delay']

def check_claiming_time(account):
    estimated_time = datetime.datetime.utcfromtimestamp(int(account.claiming_time))
    if datetime.datetime.utcnow() >= estimated_time:
        return True
    else:
        return False

def clear_quantity(quantity):
    quantity_string = str(quantity)
    if ',' in quantity_string:
        quantity_string.replace(',', '.')
    if '.' in quantity_string:
        number = quantity_string.split('.')
        first = number[0]
        second = number[1]
        while len(second) < 4:
            second += "0"
    else:
        first = quantity
        second = "0000"
    return f"{first}.{second}"

def withdraw(account, quantity, token):
    if quantity == 'all':
        if token == 'GMD':
            quantity = float(account.miner_info["goldmand"])/10000
        elif token == 'GMM':
            quantity = float(account.miner_info["minerals"])/10000
        elif token == 'GME':
            quantity = float(account.miner_info["energy"])/10000
        elif token == 'GMF':
            quantity = float(account.miner_info["food"])/10000

    new_quantity = clear_quantity(quantity)
    data = {'miner': account.account_name, "quantity": f"{new_quantity} {token.upper()}"}
    trx = build_transaction(account.account_name, 'goldmandgame', 'withdraw', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully withdrew {new_quantity} {token.upper()}', Fore.LIGHTMAGENTA_EX)
    else:
        log_add(f'[{account.account_name}] Withdrawal {new_quantity} {token.upper()} failed', Fore.LIGHTRED_EX)

def deposit(account, quantity, token : str):
    new_quantity = clear_quantity(quantity)
    memo = f'Transfer {new_quantity} {token.upper()} to supply center'
    data = {'from': account.account_name, "to": "goldmandgame", "quantity": f"{new_quantity} {token.upper()}", "memo": memo}
    trx = build_transaction(account.account_name, 'goldmandiotk', 'transfer', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully deposited {new_quantity} {token.upper()} to supply center', Fore.LIGHTMAGENTA_EX)
    else:
        log_add(f'[{account.account_name}] Deposit {new_quantity} {token.upper()} to supply center failed', Fore.LIGHTRED_EX)

def transfer(account, to, quantity, token):
    new_quantity = clear_quantity(quantity)
    data = {'from': account.account_name, "to": to, "quantity": f"{new_quantity} {token.upper()}",
            "memo": ''}
    trx = build_transaction(account.account_name, 'goldmandiotk', 'transfer', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully deposited {new_quantity} {token.upper()} to supply center',
                Fore.LIGHTMAGENTA_EX)
    else:
        log_add(f'[{account.account_name}] Deposit {new_quantity} {token.upper()} to supply center failed',
                Fore.LIGHTRED_EX)

def claim(account):
    data = {'miner': account.account_name}
    trx = build_transaction(account.account_name, 'goldmandgame', 'mine', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Claiming has been done successfully', Fore.GREEN)
    else:
        log_add(f'[{account.account_name}] Claiming failed', Fore.RED)

def update():
    for account in accounts:
        account.key = eospy.keys.EOSKey(account.private_keys[1])
        parse_miner_info(account)
        account.claiming_time = calculate_mining_time(account)
    log_add('Accounts successfully updated', Fore.LIGHTYELLOW_EX)

def monitoring():
    update()
    log_add('Monitoring started', Fore.LIGHTYELLOW_EX)
    while True:
        try:
            for account in accounts:
                if check_claiming_time(account):
                    claim(account)
                    time.sleep(3)
                    parse_miner_info(account)
                    account.claiming_time = calculate_mining_time(account)
        except:
            log_add(f'HANDLED ERROR: {traceback.format_exc()}', Fore.LIGHTRED_EX)

        time.sleep(5)

init(autoreset=True)

print('/update - to update data\n')
print('/deposit {account_name} {quantity} {token} - to deposit token\n')
print('/withdraw {account_name} {quantity}/all {token} - to withdraw token\n')

threading.Thread(target=monitoring).start()

while True:
    try:
        command = input('')
        if '/update' in command:
            update()
        elif '/deposit' in command:
            data = command.split()
            account = find_account(data[1])
            if account is None:
                log_add(f'Cannot find account with account_name={data[1]}', Fore.RED)
                continue
            deposit(account, data[2], data[3])
        elif '/withdraw' in command:
            data = command.split()
            account = find_account(data[1])
            if account is None:
                log_add(f'Cannot find account with account_name={data[1]}', Fore.RED)
                continue
            withdraw(account, data[2], data[3])
        elif '/list' in command:
            for account in accounts:
                parse_miner_info(account)

    except:
        log_add(f'HANDLED ERROR: {traceback.format_exc()}', Fore.LIGHTRED_EX)

