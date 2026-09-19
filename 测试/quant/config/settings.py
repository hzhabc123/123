"""Configuration settings for quant project."""

SETTINGS = {
    "START_CASH": 100000,
    "COMMISSION": 0.0005,
    # P0-7: 随机种子，保证可复现
    "SEED": 42,
}


def load_config(path: str = "config.yaml") -> dict:
    """
    读取 YAML 格式的配置文件，返回 dict。

    采用轻量级手工解析（仅支持本项目的简单 YAML 子集：
    标量值、列表），避免引入 PyYAML 等外部依赖。

    支持的格式：
      - key: value          # 标量（字符串、数字）
      - key:                # 列表
        - item1
        - item2
      # 开头的行为注释

    Parameters
    ----------
    path : str
        配置文件路径

    Returns
    -------
    dict
        解析后的配置字典
    """
    result = {}
    current_key = None
    current_list = None

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n\r")

            # 跳过空行和注释
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 列表项（以 "- " 开头，前面有缩进）
            if stripped.startswith("- "):
                if current_key is not None:
                    value = stripped[2:].strip().strip('"').strip("'")
                    current_list.append(_cast_value(value))
                continue

            # key: value 行
            if ":" in stripped:
                colon_idx = stripped.index(":")
                key = stripped[:colon_idx].strip()
                value_part = stripped[colon_idx + 1:].strip()

                # 先把上一个列表写入 result
                if current_key is not None and current_list is not None:
                    result[current_key] = current_list

                if value_part:
                    # 标量值
                    result[key] = _cast_value(value_part)
                    current_key = None
                    current_list = None
                else:
                    # 后续跟列表
                    current_key = key
                    current_list = []

    # 尾部列表
    if current_key is not None and current_list is not None:
        result[current_key] = current_list

    return result


def _cast_value(s: str):
    """将字符串值转为合适的 Python 类型。"""
    # 去引号
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # 整数
    try:
        return int(s)
    except ValueError:
        pass

    # 浮点数
    try:
        return float(s)
    except ValueError:
        pass

    # 布尔
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False

    # 字符串
    return s
