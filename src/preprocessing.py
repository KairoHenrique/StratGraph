"""Pré-processamento topológico: contração de becos sem saída com coletáveis."""

from src.models import Edge, GameGraph, Vertex


def contract_dead_ends(graph: GameGraph) -> GameGraph:
    """Funde becos sem saída com coletáveis na sala adjacente preservando custos.

    Uma sala C é considerada um beco sem saída elegível para contração na sala B se:
    1. C não é INICIO nem FIM, não possui arma e possui valor_coletavel > 0;
    2. B não é INICIO nem FIM;
    3. Todas as arestas que entram em C vêm exclusivamente de B e todas as arestas
       que saem de C vão exclusivamente para B (garantindo ida e volta B <-> C).

    Ao contrair C em B:
    - O valor_coletavel de C é somado ao de B;
    - O custo de ida e volta (B -> C -> B) é somado às arestas que entram em B;
    - O histórico de contração é registrado em `contracted_into[B]` para auditoria.
    """
    vertices: dict[str, Vertex] = dict(graph.vertices)
    adjacency: dict[str, list[Edge]] = {u: list(edges) for u, edges in graph.adjacency.items()}
    contracted_into: dict[str, list[str]] = {
        u: list(rooms) for u, rooms in graph.contracted_into.items()
    }

    # Identifica os becos sem saída originais da topologia (grau 1 bidirecional)
    initial_incoming: dict[str, list[Edge]] = {u: [] for u in vertices}
    for u, edges in adjacency.items():
        for edge in edges:
            if edge.destination in initial_incoming:
                initial_incoming[edge.destination].append(edge)

    original_dead_ends: list[str] = []
    for cand_id in sorted(vertices.keys()):
        cand = vertices[cand_id]
        if cand_id in {graph.start_id, graph.goal_id} or cand.has_weapon or cand.collectible_value <= 0.0:
            continue
        out_edges = adjacency.get(cand_id, [])
        in_edges = initial_incoming.get(cand_id, [])
        if not out_edges or not in_edges:
            continue
        neighbors_out = {e.destination for e in out_edges}
        neighbors_in = {e.origin for e in in_edges}
        if len(neighbors_out) == 1 and neighbors_out == neighbors_in:
            parent_id = next(iter(neighbors_out))
            parent_v = vertices.get(parent_id)
            if (
                parent_v is not None
                and parent_id not in {cand_id, graph.start_id, graph.goal_id}
                and not parent_v.has_weapon
            ):
                original_dead_ends.append(cand_id)

    for cand_id in original_dead_ends:
        if cand_id not in vertices:
            continue
        cand = vertices[cand_id]
        incoming_map: dict[str, list[Edge]] = {u: [] for u in vertices}
        for u, edges in adjacency.items():
            for edge in edges:
                if edge.destination in incoming_map:
                    incoming_map[edge.destination].append(edge)

        out_edges = adjacency.get(cand_id, [])
        in_edges = incoming_map.get(cand_id, [])
        if not out_edges or not in_edges:
            continue

        neighbors_out = {e.destination for e in out_edges}
        neighbors_in = {e.origin for e in in_edges}
        if len(neighbors_out) != 1 or neighbors_out != neighbors_in:
            continue

        parent_id = next(iter(neighbors_out))
        parent_v = vertices[parent_id]
        if parent_id in {cand_id, graph.start_id, graph.goal_id} or parent_v.has_weapon:
            continue

        # Escolhe a menor aresta de entrada (B -> C) e de saída (C -> B)
        best_in = min(in_edges, key=lambda e: e.base_time + e.difficulty_no_weapon)
        best_out = min(out_edges, key=lambda e: e.base_time + e.difficulty_no_weapon)

        rt_time = best_in.base_time + best_out.base_time
        rt_diff0 = best_in.difficulty_no_weapon + best_out.difficulty_no_weapon
        rt_diff1 = best_in.difficulty_with_weapon + best_out.difficulty_with_weapon

        vertices[parent_id] = Vertex(
            room_id=parent_v.room_id,
            room_type=parent_v.room_type,
            collectible_value=parent_v.collectible_value + cand.collectible_value,
            has_weapon=parent_v.has_weapon,
        )

        merged_list = contracted_into.setdefault(parent_id, [])
        merged_list.append(cand_id)
        if cand_id in contracted_into:
            merged_list.extend(contracted_into.pop(cand_id))

        # Remove arestas incidentes a cand_id e soma o custo de ida e volta
        # às arestas que entram em parent_id vindas de outros vértices.
        del vertices[cand_id]
        del adjacency[cand_id]

        for u, u_edges in adjacency.items():
            new_u_edges: list[Edge] = []
            for edge in u_edges:
                if edge.destination == cand_id:
                    continue
                if edge.destination == parent_id:
                    new_u_edges.append(
                        Edge(
                            origin=edge.origin,
                            destination=edge.destination,
                            base_time=edge.base_time + rt_time,
                            difficulty_no_weapon=edge.difficulty_no_weapon + rt_diff0,
                            difficulty_with_weapon=edge.difficulty_with_weapon + rt_diff1,
                            two_way=edge.two_way,
                        )
                    )
                else:
                    new_u_edges.append(edge)
            adjacency[u] = new_u_edges

    return GameGraph(
        vertices=vertices,
        adjacency=adjacency,
        start_id=graph.start_id,
        goal_id=graph.goal_id,
        contracted_into=contracted_into,
        original_collectibles=dict(graph.original_collectibles),
    )
