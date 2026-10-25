from net.TcpListener import TcpListener
#from net.Connection import Connection

class Server():
    def __init__(self, hostname:str="0.0.0.0", port:int=25565, max_connectionsint=5):
        self.hostname = hostname
        self.port = port

    def run(self) -> None:
        pass