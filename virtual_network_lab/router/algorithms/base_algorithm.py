# router/algorithms/base_algorithm.py
class BaseAlgorithm:
    """
    所有路由协议的基类
    """

    def __init__(self, core):
        self.core = core

    def handle_packet(self, pkt, iface):
        """处理控制协议包"""
        pass

    def periodic(self):
        """定时执行（如 broadcast、心跳）"""
        pass
