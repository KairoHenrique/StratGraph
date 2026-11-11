"""Construção do dígrafo ponderado expandido em camadas (Camada 0 e Camada 1)."""

from dataclasses import dataclass, field

from src.models import GameGraph, LayeredEdge, LayeredNode


@dataclass
class LayeredGraph:
    """Representação computacional do grafo expandido em duas camadas."""

    adjacency: dict[LayeredNode, list[LayeredEdge]] = field(default_factory=dict)
    start_node: LayeredNode = field(default_factory=lambda: LayeredNode("", 0))
    goal_room_id: str = ""
    alpha: float = 0.5
    base_graph: GameGraph = field(default_factory=GameGraph)


def compute_effective_weight(
    base_time: float,
    difficulty: float,
    collectible_value: float,
    alpha: float,
) -> float:
    """Calcula w(u, v, k) estritamente positivo para atrair coletáveis.

    Equação:
        w(u, v, k) = (TempoBase(u, v) + Dificuldade(u, v, k)) / (1 + alpha * ValorColetavel(v))
    """
    if alpha < 0.0:
        raise ValueError("O parâmetro alpha não pode ser negativo.")
    if base_time <= 0.0:
        raise ValueError("base_time deve ser estritamente positivo (> 0).")
    if difficulty < 0.0 or collectible_value < 0.0:
        raise ValueError("difficulty e collectible_value devem ser não-negativos (>= 0).")

    numerator = base_time + difficulty
    denominator = 1.0 + (alpha * collectible_value)
    return numerator / denominator


def build_layered_graph(graph: GameGraph, alpha: float = 0.5) -> LayeredGraph:
    """Expande `GameGraph` nas camadas 0 (sem arma) e 1 (com arma)."""
    if alpha < 0.0:
        raise ValueError("O parâmetro alpha não pode ser negativo.")

    adjacency: dict[LayeredNode, list[LayeredEdge]] = {}
    for room_id in graph.vertices:
        adjacency[LayeredNode(room_id, 0)] = []
        adjacency[LayeredNode(room_id, 1)] = []

    for origin_id, edges in graph.adjacency.items():
        for edge in edges:
            dest_vertex = graph.vertices[edge.destination]

            # Camada 0: Desarmado
            real_0 = edge.base_time + edge.difficulty_no_weapon
            eff_0 = compute_effective_weight(
                base_time=edge.base_time,
                difficulty=edge.difficulty_no_weapon,
                collectible_value=dest_vertex.collectible_value,
                alpha=alpha,
            )
            adjacency[LayeredNode(origin_id, 0)].append(
                LayeredEdge(
                    origin=LayeredNode(origin_id, 0),
                    destination=LayeredNode(edge.destination, 0),
                    effective_weight=eff_0,
                    real_cost=real_0,
                    base_time=edge.base_time,
                    difficulty=edge.difficulty_no_weapon,
                    is_weapon_transition=False,
                )
            )

            # Camada 1: Armado
            real_1 = edge.base_time + edge.difficulty_with_weapon
            eff_1 = compute_effective_weight(
                base_time=edge.base_time,
                difficulty=edge.difficulty_with_weapon,
                collectible_value=dest_vertex.collectible_value,
                alpha=alpha,
            )
            adjacency[LayeredNode(origin_id, 1)].append(
                LayeredEdge(
                    origin=LayeredNode(origin_id, 1),
                    destination=LayeredNode(edge.destination, 1),
                    effective_weight=eff_1,
                    real_cost=real_1,
                    base_time=edge.base_time,
                    difficulty=edge.difficulty_with_weapon,
                    is_weapon_transition=False,
                )
            )

    # Aresta de transição de custo zero (u_arma, 0) -> (u_arma, 1)
    for room_id, vertex in graph.vertices.items():
        if vertex.has_weapon:
            node_0 = LayeredNode(room_id, 0)
            node_1 = LayeredNode(room_id, 1)
            adjacency[node_0].append(
                LayeredEdge(
                    origin=node_0,
                    destination=node_1,
                    effective_weight=0.0,
                    real_cost=0.0,
                    base_time=0.0,
                    difficulty=0.0,
                    is_weapon_transition=True,
                )
            )

    return LayeredGraph(
        adjacency=adjacency,
        start_node=LayeredNode(graph.start_id, 0),
        goal_room_id=graph.goal_id,
        alpha=alpha,
        base_graph=graph,
    )
