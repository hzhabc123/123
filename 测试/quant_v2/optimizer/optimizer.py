"""
Quant V2 参数优化模块
网格搜索 + Walk-Forward 验证
"""

from typing import Dict, List, Any, Callable
from itertools import product
from dataclasses import dataclass
import json


@dataclass
class OptimizationResult:
    params: Dict[str, Any]
    metrics: Dict[str, float]
    score: float

    def __repr__(self) -> str:
        return f"OptimizationResult(score={self.score:.4f}, params={self.params})"


class GridSearch:
    def __init__(self, param_grid: Dict[str, List[Any]], score_metric: str = "sharpe_ratio", maximize: bool = True):
        self.param_grid = param_grid
        self.score_metric = score_metric
        self.maximize = maximize
        self.results: List[OptimizationResult] = []
        self.best_result: OptimizationResult = None

    def optimize(self, backtest_fn: Callable) -> OptimizationResult:
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        combinations = list(product(*param_values))
        print(f"[GridSearch] 开始优化，共 {len(combinations)} 个参数组合")
        print(f"[GridSearch] 评分指标: {self.score_metric} ({'maximize' if self.maximize else 'minimize'})")
        self.results = []
        for i, combo in enumerate(combinations, 1):
            params = dict(zip(param_names, combo))
            try:
                metrics = backtest_fn(params)
                score = metrics.get(self.score_metric, 0.0)
                result = OptimizationResult(params=params, metrics=metrics, score=score)
                self.results.append(result)
                if self.best_result is None:
                    self.best_result = result
                elif self.maximize and score > self.best_result.score:
                    self.best_result = result
                elif not self.maximize and score < self.best_result.score:
                    self.best_result = result
                if i % 10 == 0 or i == len(combinations):
                    print(f"[GridSearch] 进度: {i}/{len(combinations)}, 当前最优: {self.best_result.score:.4f}")
            except Exception as e:
                print(f"[GridSearch] 参数 {params} 回测失败: {e}")
                continue
        print(f"[GridSearch] 优化完成，最优参数: {self.best_result.params}")
        print(f"[GridSearch] 最优评分: {self.best_result.score:.4f}")
        return self.best_result

    def get_top_n(self, n: int = 10) -> List[OptimizationResult]:
        sorted_results = sorted(self.results, key=lambda r: r.score, reverse=self.maximize)
        return sorted_results[:n]

    def save_results(self, filepath: str):
        data = {"best_result": {"params": self.best_result.params, "metrics": self.best_result.metrics, "score": self.best_result.score},
                "all_results": [{"params": r.params, "metrics": r.metrics, "score": r.score} for r in self.results]}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[GridSearch] 结果已保存到 {filepath}")


class WalkForward:
    def __init__(self, train_period: int = 252, test_period: int = 63, step: int = 63):
        self.train_period = train_period
        self.test_period = test_period
        self.step = step
        self.results: List[Dict[str, Any]] = []

    def validate(self, data_loader: Callable, params: Dict[str, Any], backtest_fn: Callable) -> Dict[str, float]:
        print(f"[WalkForward] 开始验证，参数: {params}")
        print(f"[WalkForward] 训练期={self.train_period}, 测试期={self.test_period}, 步长={self.step}")
        all_data = data_loader()
        total_days = len(all_data)
        if total_days < self.train_period + self.test_period:
            raise ValueError(f"数据不足: {total_days} < {self.train_period + self.test_period}")
        self.results = []
        start_idx = 0
        fold = 1
        while start_idx + self.train_period + self.test_period <= total_days:
            train_end = start_idx + self.train_period
            test_end = train_end + self.test_period
            train_data = all_data[start_idx:train_end]
            test_data = all_data[train_end:test_end]
            print(f"[WalkForward] Fold {fold}: 训练=[{start_idx}:{train_end}], 测试=[{train_end}:{test_end}]")
            try:
                test_metrics = backtest_fn(test_data, params)
                result = {"fold": fold, "train_period": (start_idx, train_end), "test_period": (train_end, test_end), "metrics": test_metrics}
                self.results.append(result)
                print(f"[WalkForward] Fold {fold} 结果: Return={test_metrics.get('total_return', 0):.2%}, Sharpe={test_metrics.get('sharpe_ratio', 0):.4f}")
            except Exception as e:
                print(f"[WalkForward] Fold {fold} 回测失败: {e}")
            start_idx += self.step
            fold += 1
        summary = self._aggregate_results()
        print(f"[WalkForward] 验证完成，共 {len(self.results)} 个Fold")
        print(f"[WalkForward] 平均收益: {summary.get('avg_return', 0):.2%}")
        print(f"[WalkForward] 平均夏普: {summary.get('avg_sharpe', 0):.4f}")
        return summary

    def _aggregate_results(self) -> Dict[str, float]:
        if not self.results:
            return {}
        returns = [r["metrics"].get("total_return", 0) for r in self.results]
        sharpes = [r["metrics"].get("sharpe_ratio", 0) for r in self.results]
        max_drawdowns = [r["metrics"].get("max_drawdown", 0) for r in self.results]
        return {"num_folds": len(self.results), "avg_return": sum(returns) / len(returns),
                "avg_sharpe": sum(sharpes) / len(sharpes), "avg_max_drawdown": sum(max_drawdowns) / len(max_drawdowns),
                "std_return": self._std(returns), "std_sharpe": self._std(sharpes)}

    def _std(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    def save_results(self, filepath: str):
        data = {"summary": self._aggregate_results(), "folds": self.results}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[WalkForward] 结果已保存到 {filepath}")
