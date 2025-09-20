import os
# 尝试多个可能的配置文件路径
config_paths = [
    '../local_config',
    '../config', 
    '../../local_config',
    '../../config', 
    '../configs/secrets.yaml',
    '../configs/secrets.example.yaml'
]

data = None
for path in config_paths:
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = f.readlines()
            break
        except Exception as e:
            print(f"读取配置文件 {path} 失败: {e}")
            continue

if data is None:
    # 如果所有配置文件都不存在，使用默认值
    print("警告: 未找到配置文件，使用默认值")
    data = [
        "your_access_key_here",
        "your_secret_key_here", 
        "your_passphrase_here",
        "localhost",
        "user",
        "password",
        "localhost",
        "localhost"
    ]
ACCESS_KEY  = data[0].strip()
SECRET_KEY  = data[1].strip()
PASSPHRASE = data[2].strip()
HOST_IP = data[3].strip()
HOST_USER = data[4].strip()
HOST_PASSWD = data[5].strip()
HOST_IP_1 = data[6].strip()
HOST_IP_2 = data[7].strip()
