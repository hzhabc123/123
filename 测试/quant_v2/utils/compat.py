"""
Quant V2 环境兼容层

Python 3.13 移除了 pkgutil.ImpImporter，而 akshare 依赖的 py_mini_racer 仍引用它，
直接 `import akshare` 会抛 AttributeError。这里在导入前注入兼容补丁。
"""

import pkgutil
import sys


def patch_imp_importer() -> None:
    if not hasattr(pkgutil, "ImpImporter"):
        class ImpImporter:
            def __init__(self, *args, **pass):
                pass
            def find_module(self, fullname, path=None):
                return None
            def find_loader(self, fullname, path=None):
                return None, []
        pkgutil.ImpImporter = ImpImporter


def is_py313_plus() -> bool:
    return sys.version_info >= (3, 13)
