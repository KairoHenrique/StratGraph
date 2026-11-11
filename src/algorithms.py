"""Algoritmos de busca para comparação experimental: BFS, DFS Branch-and-Bound e Dijkstra."""

from collections import deque
import heapq
import sys
import time

from src.layered_graph import LayeredGraph, compute_effective_weight
from src.models import LayeredEdge, LayeredNode, RouteResult


def _find_best_edge(
    layered_graph: LayeredGraph,
    origin: LayeredNode,
    destination: LayeredNode,
) -> LayeredEdge:
    candidates = [
        edge
        for edge in layered_graph.adjacency.get(origin, [])
        if edge.destination == destination
    ]
    if not candidates:
        raise ValueError(f"Aresta inexistente no grafo em camadas: {origin} -> {destination}")
    return min(candidates, key=lambda e: (e.effective_weight, e.real_cost))


def evaluate_path(
    layered_graph: LayeredGraph,
    path: list[LayeredNode],
    algorithm_name: str,
    visited_states: int,
    elapsed_ms: float,
    timed_out: bool = False,
) -> RouteResult:
    """Calcula custo real, custo efetivo (sem dupla contagem) e coletáveis únicos da rota."""
    if not path:
        return RouteResult(
            algorithm=algorithm_name,
            found=False,
            visited_states=visited_states,
            elapsed_ms=elapsed_ms,
            timed_out=timed_out,
        )

    base_graph = layered_graph.base_graph
    alpha = layered_graph.alpha

    real_cost = 0.0
    effective_cost = 0.0
    seen_rooms_for_discount: set[str] = {path[0].room_id}

    for idx in range(len(path) - 1):
        u_node = path[idx]
        v_node = path[idx + 1]
        edge = _find_best_edge(layered_graph, u_node, v_node)
        real_cost += edge.real_cost

        if edge.is_weapon_transition:
            step_eff = 0.0
        elif v_node.room_id in seen_rooms_for_discount:
            # Evita aplicar o desconto do coletável duas vezes se a mesma sala
            # for visitada na Camada 0 e depois na Camada 1.
            step_eff = edge.real_cost
        else:
            dest_v = base_graph.vertices[v_node.room_id]
            step_eff = compute_effective_weight(
                base_time=edge.base_time,
                difficulty=edge.difficulty,
                collectible_value=dest_v.collectible_value,
                alpha=alpha,
            )
        effective_cost += step_eff
        seen_rooms_for_discount.add(v_node.room_id)

    collected_room_ids: set[str] = set()
    for node in path:
        r_id = node.room_id
        if base_graph.original_collectibles.get(r_id, 0.0) > 0.0:
            collected_room_ids.add(r_id)
        for contracted_id in base_graph.contracted_into.get(r_id, []):
            if base_graph.original_collectibles.get(contracted_id, 0.0) > 0.0:
                collected_room_ids.add(contracted_id)

    collectibles_total_value = sum(
        base_graph.original_collectibles[r_id] for r_id in collected_room_ids
    )
    used_weapon = any(node.layer == 1 for node in path)

    return RouteResult(
        algorithm=algorithm_name,
        found=True,
        path=list(path),
        real_cost=real_cost,
        effective_cost=effective_cost,
        collectibles_count=len(collected_room_ids),
        collectibles_total_value=collectibles_total_value,
        collected_room_ids=collected_room_ids,
        used_weapon=used_weapon,
        visited_states=visited_states,
        elapsed_ms=elapsed_ms,
        timed_out=timed_out,
    )


def _reconstruct_path(
    parent: dict[LayeredNode, LayeredNode | None],
    target: LayeredNode,
) -> list[LayeredNode]:
    path: list[LayeredNode] = []
    curr: LayeredNode | None = target
    while curr is not None:
        path.append(curr)
        curr = parent.get(curr)
    path.reverse()
    return path


def run_bfs(layered_graph: LayeredGraph) -> RouteResult:
    """Baseline em largura O(V + E): minimiza número de arestas ignorando pesos e itens."""
    t0 = time.perf_counter()
    start = layered_graph.start_node
    goal_room = layered_graph.goal_room_id

    queue: deque[LayeredNode] = deque([start])
    parent: dict[LayeredNode, LayeredNode | None] = {start: None}
    visited_states = 0
    target_node: LayeredNode | None = None

    while queue:
        curr = queue.popleft()
        visited_states += 1

        if curr.room_id == goal_room:
            target_node = curr
            break

        for edge in layered_graph.adjacency.get(curr, []):
            nxt = edge.destination
            if nxt not in parent:
                parent[nxt] = curr
                queue.append(nxt)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if target_node is None:
        return RouteResult(
            algorithm="BFS",
            found=False,
            visited_states=visited_states,
            elapsed_ms=elapsed_ms,
        )

    path = _reconstruct_path(parent, target_node)
    return evaluate_path(
        layered_graph=layered_graph,
        path=path,
        algorithm_name="BFS",
        visited_states=visited_states,
        elapsed_ms=elapsed_ms,
    )


def run_dijkstra(layered_graph: LayeredGraph) -> RouteResult:
    """Solução principal O((V + E) log V) com Min-Heap sobre o grafo em camadas."""
    t0 = time.perf_counter()
    start = layered_graph.start_node
    goal_room = layered_graph.goal_room_id

    dist: dict[LayeredNode, float] = {start: 0.0}
    parent: dict[LayeredNode, LayeredNode | None] = {start: None}
    pq: list[tuple[float, LayeredNode]] = [(0.0, start)]
    settled: set[LayeredNode] = set()
    visited_states = 0
    target_node: LayeredNode | None = None

    while pq:
        curr_d, curr = heapq.heappop(pq)
        if curr in settled:
            continue
        settled.add(curr)
        visited_states += 1

        if curr.room_id == goal_room:
            target_node = curr
            break

        for edge in layered_graph.adjacency.get(curr, []):
            nxt = edge.destination
            if nxt in settled:
                continue
            cand_d = curr_d + edge.effective_weight
            if cand_d < dist.get(nxt, float("inf")) - 1e-12:
                dist[nxt] = cand_d
                parent[nxt] = curr
                heapq.heappush(pq, (cand_d, nxt))

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if target_node is None:
        return RouteResult(
            algorithm="Dijkstra",
            found=False,
            visited_states=visited_states,
            elapsed_ms=elapsed_ms,
        )

    path = _reconstruct_path(parent, target_node)
    return evaluate_path(
        layered_graph=layered_graph,
        path=path,
        algorithm_name="Dijkstra",
        visited_states=visited_states,
        elapsed_ms=elapsed_ms,
    )


def run_dfs_branch_and_bound(
    layered_graph: LayeredGraph,
    alpha: float | None = None,
    timeout_seconds: float = 10.0,
) -> RouteResult:
    """Busca exata por backtracking com poda Branch-and-Bound e controle de coletáveis."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 25000))
    t0 = time.perf_counter()
    start = layered_graph.start_node
    goal_room = layered_graph.goal_room_id
    eff_alpha = layered_graph.alpha if alpha is None else alpha
    base_graph = layered_graph.base_graph

    best_eff_cost = float("inf")
    best_path: list[LayeredNode] = []
    visited_states = 0
    timed_out = False

    path_stack: list[LayeredNode] = [start]
    in_stack: set[LayeredNode] = {start}
    seen_rooms: dict[str, int] = {start.room_id: 1}

    def dfs(curr: LayeredNode, acc_eff: float) -> None:
        nonlocal best_eff_cost, best_path, visited_states, timed_out

        if timed_out:
            return
        visited_states += 1
        if (visited_states & 63) == 0 and (time.perf_counter() - t0) >= timeout_seconds:
            timed_out = True
            return

        if curr.room_id == goal_room:
            if acc_eff < best_eff_cost - 1e-12:
                best_eff_cost = acc_eff
                best_path = list(path_stack)
            return

        # Ordena arestas por menor peso efetivo para acelerar obtenção de bons limites
        edges = sorted(
            layered_graph.adjacency.get(curr, []),
            key=lambda e: (e.effective_weight, e.real_cost),
        )
        for edge in edges:
            nxt = edge.destination
            if nxt in in_stack:
                continue

            if edge.is_weapon_transition:
                step_eff = 0.0
            elif seen_rooms.get(nxt.room_id, 0) > 0:
                step_eff = edge.real_cost
            else:
                dest_v = base_graph.vertices[nxt.room_id]
                step_eff = compute_effective_weight(
                    base_time=edge.base_time,
                    difficulty=edge.difficulty,
                    collectible_value=dest_v.collectible_value,
                    alpha=eff_alpha,
                )

            next_eff = acc_eff + step_eff
            # Poda Branch-and-Bound
            if next_eff >= best_eff_cost - 1e-12:
                continue

            path_stack.append(nxt)
            in_stack.add(nxt)
            seen_rooms[nxt.room_id] = seen_rooms.get(nxt.room_id, 0) + 1

            dfs(nxt, next_eff)

            seen_rooms[nxt.room_id] -= 1
            in_stack.remove(nxt)
            path_stack.pop()
            if timed_out:
                return

    dfs(start, 0.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if not best_path:
        return RouteResult(
            algorithm="DFS Branch-and-Bound",
            found=False,
            visited_states=visited_states,
            elapsed_ms=elapsed_ms,
            timed_out=timed_out,
        )

    return evaluate_path(
        layered_graph=layered_graph,
        path=best_path,
        algorithm_name="DFS Branch-and-Bound",
        visited_states=visited_states,
        elapsed_ms=elapsed_ms,
        timed_out=timed_out,
    )
