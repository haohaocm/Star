# router/routing_table.py
class RoutingTable:
    """
    最简路由表格式：
    self.table = {
       "目的IP/prefix": "下一跳IP"
    }
    """

    def __init__(self):
        self.table = {}

    def update(self, dst_prefix, next_hop):
        self.table[dst_prefix] = next_hop

    def lookup(self, dst_ip):
        """非常简化：全量匹配即可，后续可扩展 LPM"""
        return self.table.get(dst_ip, None)
