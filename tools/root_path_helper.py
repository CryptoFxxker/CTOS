import os
import sys

def add_project_paths(project_name="ctos", subpackages=None):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    
    :param project_name: 项目根目录标识（默认 'ctos'）
    :param subpackages: 需要暴露的子包列表（默认 ["ctos", "bpx", "okx", "backpack", "apps"]）
    """
    if subpackages is None:
        subpackages = ["ctos", "bpx", "okx", "backpack", "apps"]

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None

    # 向上回溯，找到项目根目录
    path = current_dir
    while path != os.path.dirname(path):  # 一直回溯到根目录
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)

    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")

    # 添加根目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 添加子包目录
    for pkg in subpackages:
        pkg_path = os.path.join(project_root, pkg)
        if os.path.exists(pkg_path) and pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)

    return project_root

def get_current_file_path() -> str:
    """返回当前文件的绝对路径"""
    return os.path.abspath(__file__)

def get_current_dir() -> str:
    """返回当前文件所在的目录"""
    return os.path.dirname(os.path.abspath(__file__))



# 执行路径添加
PROJECT_ROOT = add_project_paths()
print(PROJECT_ROOT)

print(get_current_file_path())
print(get_current_dir())