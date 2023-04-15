class Account:

    def __init__(self, account_name, private_keys, public_keys):
        self.private_keys = private_keys
        self.public_keys = public_keys
        self.account_name = account_name
        self.key = None
        self.miner_info = None
        self.claiming_time = None
