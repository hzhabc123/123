# config/run_hash.py
# -*- coding: utf-8 -*-
"""
可复现性：计算运行哈希（P0-7）。

对配置文件内容 + 数据文件的 SHA256 拼接后再次 SHA256，
返回 16 位十六进制字符串，用于标识一次回测的输入唯一性。
"""

import hashlib


def compute_file_sha256(path: str) -> str:
    """
    计算单个文件的 SHA256 哈希值。

    Parameters
    ----------
    path : str
        文件路径

    Returns
    -------
    str
        64 位十六进制 SHA256 摘要
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_run_hash(config_path: str, data_files: list) -> str:
    """
    对配置文件内容 + 各数据文件的 SHA256 拼接后再 SHA256，
    返回 16 位十六进制字符串。

    Parameters
    ----------
    config_path : str
        配置文件路径（如 config/config.yaml）
    data_files : list[str]
        数据文件路径列表

    Returns
    -------
    str
        16 位十六进制 run_hash
    """
    parts = []

    # 配置文件内容
    parts.append(compute_file_sha256(config_path))

    # 各数据文件
    for df_path in data_files:
        parts.append(compute_file_sha256(df_path))

    # 拼接后整体哈希
    combined = "".join(parts)
    full_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    return full_hash[:16]
