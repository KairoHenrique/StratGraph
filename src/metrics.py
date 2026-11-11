"""Cálculo de métricas (custo real, coletáveis únicos, gap) e exportação de resultados."""

from pathlib import Path

from src.models import RouteResult


def summarize_results(results: list[RouteResult]) -> list[dict[str, object]]:
    """Formata métricas comparativas entre algoritmos para tabela/CSV."""
    raise NotImplementedError("A ser implementado na Fase 3.")


def export_results_csv(results: list[RouteResult], output_path: Path) -> None:
    """Exporta resultados comparativos para arquivo CSV."""
    raise NotImplementedError("A ser implementado na Fase 3.")

