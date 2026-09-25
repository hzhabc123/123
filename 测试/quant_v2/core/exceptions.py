"""
Quant V2 异常体系
定义所有可能的异常类型
"""


class QuantError(Exception):
    pass


class DataError(QuantError):
    pass


class DataNotFoundError(DataError):
    pass


class DataFormatError(DataError):
    pass


class BrokerError(QuantError):
    pass


class InsufficientFunds(BrokerError):
    pass


class OrderRejected(BrokerError):
    pass


class RiskRejected(QuantError):
    pass


class PositionError(QuantError):
    pass


class InsufficientPosition(PositionError):
    pass


class StrategyError(QuantError):
    pass


class ConfigError(QuantError):
    pass


class PersistenceError(QuantError):
    pass
