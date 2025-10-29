import socket
def get_host_ip():
    """
    查询本机ip地址
    :return: ip
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('114.114.114.114', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
        return ip




import os
ip = get_host_ip()
if ip.find('66.187') != -1:
    if os.path.exists('/root/Quantify/local_config'):
        with open('/root/Quantify/local_config', 'r') as f:
            data = f.readlines()
    else:
        with open('/root/Quantify/config', 'r') as f:
            data = f.readlines()
else:
    if os.path.exists('/home/zzb/Quantify/local_config'):
        with open('/home/zzb/Quantify/local_config', 'r') as f:
            data = f.readlines()
    elif os.path.exists('/home/zzb/Quantify/config'):
        with open('/home/zzb/Quantify/config', 'r') as f:
            data = f.readlines()
    elif os.path.exists('D:\\Quantify\config'):
        with open('D:\\Quantify\config', 'r') as f:
            data = f.readlines()
    elif os.path.exists('D:\\Quantify\local_config'):
        with open('D:\\Quantify\local_config', 'r') as f:
            data = f.readlines()

            
ACCESS_KEY  = data[0].strip()
SECRET_KEY  = data[1].strip()
PASSPHRASE = data[2].strip()
HOST_IP = data[3].strip()
HOST_USER = data[4].strip()
HOST_PASSWD = data[5].strip()
HOST_IP_1 = data[6].strip()
HOST_IP_2 = data[7].strip()
