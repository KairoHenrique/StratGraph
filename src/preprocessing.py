"""Pré-processamento topológico: contração de becos sem saída com coletáveis."""

from src.models import GameGraph


def contract_dead_ends(graph: GameGraph) -> GameGraph:
    """Funde becos sem saída com coletáveis na sala adjacente preservando custos."""
    raise NotImplementedError("A ser implementado na Fase 2.")

