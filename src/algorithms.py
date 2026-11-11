"""Algoritmos de busca para comparação experimental: BFS, DFS Branch-and-Bound e Dijkstra."""

from src.layered_graph import LayeredGraph
from src.models import RouteResult


def run_bfs(layered_graph: LayeredGraph) -> RouteResult:
    """Baseline em largura O(V + E): minimiza saltos ignorando pesos e coletáveis."""
    raise NotImplementedError("A ser implementado na Fase 3.")


def run_dfs_branch_and_bound(
    layered_graph: LayeredGraph,
    alpha: float = 0.5,
    timeout_seconds: float = 10.0,
) -> RouteResult:
    """Busca exata com poda e rastreamento único de coletáveis visitados."""
    raise NotImplementedError("A ser implementado na Fase 3.")


def run_dijkstra(layered_graph: LayeredGraph) -> RouteResult:
    """Solução principal O((V + E) log V) com Min-Heap sobre o grafo em camadas."""
    raise NotImplementedError("A ser implementado na Fase 3.")

