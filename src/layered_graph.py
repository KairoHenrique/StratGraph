"""Construção do dígrafo ponderado expandido em camadas (Camada 0 e Camada 1)."""

from dataclasses import dataclass, field

from src.models import GameGraph, LayeredEdge, LayeredNode


@dataclass
class LayeredGraph:
    """Representação computacional do grafo expandido em duas camadas."""

    adjacency: dict[LayeredNode, list[LayeredEdge]] = field(default_factory=dict)
    start_node: LayeredNode = field(default_factory=lambda: LayeredNode("", 0))
    goal_room_id: str = ""
    base_graph: GameGraph = field(default_factory=GameGraph)


def compute_effective_weight(
    base_time: float,
    difficulty: float,
    collectible_value: float,
    alpha: float,
) -> float:
    """Calcula w(u, v, k) estritamente positivo para atrair coletáveis."""
    raise NotImplementedError("A ser implementado na Fase 2.")


def build_layered_graph(graph: GameGraph, alpha: float = 0.5) -> LayeredGraph:
    """Expande `GameGraph` nas camadas 0 (sem arma) e 1 (com arma)."""
    raise NotImplementedError("A ser implementado na Fase 2.")

