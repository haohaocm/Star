class Scheduler:
    def __init__(self, servers):
        self.servers = servers

    def assign(self, router_id):
        """简单调度器：按服务器数量轮询"""
        return self.servers[router_id % len(self.servers)]
