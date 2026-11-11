"""Simulador Visual Interativo 2D (HTML5 Canvas) para o StratGraph.

Gera uma aplicação web autocontida (`results/stratgraph_simulator.html`) usando
apenas a biblioteca padrão do Python 3.12. Extrai a geometria real das salas dos
arquivos binários oficiais de Celeste (`.bin`, incluindo matriz de colisão
`<solids>`) e das cenas binárias Unity de Cuphead (`level41` a `level46`),
executando os três algoritmos (BFS, Dijkstra `--no-contract` e StratGraph
Completo com Contração de Becos + Camadas L0->L1) para visualização animada
passo a passo no navegador (Linux Ubuntu 24.04 e Windows).

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path
import webbrowser

from scripts.extract_celeste_maps import (
    CHAPTER_FILES,
    DEFAULT_STEAM_MAPS_DIR,
    _get_solids_grid,
    parse_celeste_bin,
)
from scripts.extract_cuphead_maps import (
    CUPHEAD_RUN_AND_GUN_SCENES,
    DEFAULT_CUPHEAD_DATA_DIR,
    ENEMY_WEIGHTS,
    PLATFORM_KEYWORDS,
    parse_unity_scene_objects,
)
from src.algorithms import run_bfs, run_dfs_branch_and_bound, run_dijkstra
from src.layered_graph import build_layered_graph, compute_effective_weight
from src.loader import load_graph_from_csv
from src.models import GameGraph, RouteResult
from src.preprocessing import contract_dead_ends

DEFAULT_OUT_HTML = Path("results/stratgraph_simulator.html")


def _downsample_solids(grid: list[list[bool]], target_w: int = 20, target_h: int = 12) -> list[str]:
    """Compacta a matriz `<solids>` da sala para renderização leve no Canvas 2D."""
    if not grid or not grid[0]:
        return []
    h = len(grid)
    w = len(grid[0])
    rows_out: list[str] = []
    for r in range(target_h):
        r0 = int(r * h / target_h)
        r1 = max(r0 + 1, int((r + 1) * h / target_h))
        line_chars: list[str] = []
        for c in range(target_w):
            c0 = int(c * w / target_w)
            c1 = max(c0 + 1, int((c + 1) * w / target_w))
            solid_votes = 0
            total_votes = 0
            for rr in range(r0, min(h, r1)):
                for cc in range(c0, min(w, c1)):
                    total_votes += 1
                    # Em `_get_solids_grid`, True significa ar ('0') e False significa bloco sólido
                    if not grid[rr][cc]:
                        solid_votes += 1
            line_chars.append("1" if solid_votes * 2 >= max(1, total_votes) else "0")
        rows_out.append("".join(line_chars))
    return rows_out


def _extract_celeste_geometry(slug: str, bin_filename: str, graph: GameGraph) -> dict[str, dict[str, object]]:
    """Extrai retângulos reais `(x, y, w, h)` e tiles `<solids>` do `.bin` do Celeste."""
    bin_path = DEFAULT_STEAM_MAPS_DIR / bin_filename
    if not bin_path.is_file():
        return _fallback_layout(graph)

    _pkg, root = parse_celeste_bin(bin_path)
    levels = [c for c in root[2] if c[0] == "levels"][0][2]
    geom: dict[str, dict[str, object]] = {}

    for lvl in levels:
        at = lvl[1]
        name = str(at["name"])
        if name not in graph.vertices:
            continue
        x, y = float(at["x"]), float(at["y"])
        w, h = float(at["width"]), float(at["height"])
        wt, ht = max(1, int(w) // 8), max(1, int(h) // 8)
        grid = _get_solids_grid(lvl, wt, ht)
        compact_tiles = _downsample_solids(grid, target_w=20, target_h=12)

        strawberries = 0
        hazards = 0
        for ch in lvl[2]:
            if ch[0] == "entities":
                for e in ch[2]:
                    ename = e[0]
                    if ename in ("strawberry", "cassette", "blackGem", "reflectionHeartStatue"):
                        strawberries += 1
                    elif "spike" in ename.lower() or "spinner" in ename.lower():
                        hazards += 1

        geom[name] = {
            "x": round(x, 1),
            "y": round(y, 1),
            "w": round(w, 1),
            "h": round(h, 1),
            "cx": round(x + w / 2.0, 1),
            "cy": round(y + h / 2.0, 1),
            "tiles": compact_tiles,
            "strawberries": strawberries,
            "hazards": hazards,
        }

    return geom if len(geom) == len(graph.vertices) else _fallback_layout(graph)


def _extract_cuphead_geometry(scene_idx: int, graph: GameGraph) -> dict[str, dict[str, object]]:
    """Extrai posições 2D reais dos setores, moedas e santuário de arma do Cuphead."""
    scene_path = DEFAULT_CUPHEAD_DATA_DIR / f"level{scene_idx}"
    if not scene_path.is_file():
        return _fallback_layout(graph)

    items = parse_unity_scene_objects(scene_path)
    coins: list[tuple[str, float, float]] = []
    enemies: list[tuple[str, float, float, float]] = []
    raw_platforms: list[tuple[str, float, float]] = []

    for full_path, leaf_name, wx, wy in items:
        low_path = full_path.lower()
        low_name = leaf_name.lower()
        if leaf_name.startswith("Level_Coin"):
            coins.append((leaf_name, wx, wy))
        if not any(bad in low_path for bad in ("sfx", "audio", "sprite", "root", "topcover", "shadow")):
            for key, weight in ENEMY_WEIGHTS.items():
                if key in low_name or key in low_path:
                    enemies.append((leaf_name, wx, wy, weight))
                    break
        if not any(
            bad in low_path
            for bad in ("sfx", "audio", "sprite", "shadow", "mask", "spark", "smoke", "propeller", "bg_", "bgfar")
        ):
            if any(k in low_name for k in PLATFORM_KEYWORDS) and -500.0 <= wx <= 30000.0:
                raw_platforms.append((leaf_name, wx, wy))

    coins.sort(key=lambda t: (t[1], t[2]))
    raw_platforms.sort(key=lambda t: (t[1], t[2]))

    min_x = min((p[1] for p in raw_platforms), default=0.0)
    max_x = max(
        max((p[1] for p in raw_platforms), default=24000.0),
        max((c[1] for c in coins), default=22000.0) + 1200.0,
    )
    span_x = max(4000.0, max_x - min_x)
    num_sectors = 16
    sector_w = span_x / num_sectors

    geom: dict[str, dict[str, object]] = {}
    for s_idx in range(num_sectors):
        sx_start = min_x + s_idx * sector_w
        sx_end = sx_start + sector_w
        sec_plats = [p for p in raw_platforms if sx_start <= p[1] < sx_end]
        cx = (sx_start + sx_end) / 2.0
        cy = sum(p[2] for p in sec_plats) / len(sec_plats) if sec_plats else 0.0
        nid = f"sec_{s_idx:02d}"
        near_enemies = sum(
            1 for _en, ex, ey, _w in enemies if abs(ex - cx) <= 1400.0 and abs(ey - cy) <= 1200.0
        )
        # No Canvas Y cresce para baixo, então invertemos Y do Unity para visualização natural
        draw_y = -cy * 1.4
        w_box = sector_w * 0.72
        h_box = 220.0
        geom[nid] = {
            "x": round(cx - w_box / 2.0, 1),
            "y": round(draw_y - h_box / 2.0, 1),
            "w": round(w_box, 1),
            "h": round(h_box, 1),
            "cx": round(cx, 1),
            "cy": round(draw_y, 1),
            "tiles": ["000000000000", "000000000000", "000000000000", "111111111111"],
            "strawberries": 0,
            "hazards": near_enemies,
        }

    if "sec_02" in geom:
        sec02_cx = float(geom["sec_02"]["cx"])
        sec02_cy = float(geom["sec_02"]["cy"])
        wx = sec02_cx + 220.0
        wy = sec02_cy - 420.0
        geom["parry_shrine_arma"] = {
            "x": round(wx - 220.0, 1),
            "y": round(wy - 110.0, 1),
            "w": 440.0,
            "h": 220.0,
            "cx": round(wx, 1),
            "cy": round(wy, 1),
            "tiles": ["000011110000", "001111111100", "000011110000", "111111111111"],
            "strawberries": 0,
            "hazards": 1,
        }

    for c_idx, (_cname, cx, cy) in enumerate(coins, start=1):
        coin_id = f"coin_{c_idx:02d}"
        # Desloca verticalmente as moedas para destacá-las como alcovas/pontes claras no Canvas
        offset_y = 380.0 if c_idx in {1, 3, 5} else -360.0
        draw_y = -cy * 1.4 + offset_y
        geom[coin_id] = {
            "x": round(cx - 190.0, 1),
            "y": round(draw_y - 95.0, 1),
            "w": 380.0,
            "h": 190.0,
            "cx": round(cx, 1),
            "cy": round(draw_y, 1),
            "tiles": ["000111111000", "001111111100", "000111111000", "111111111111"],
            "strawberries": 1,
            "hazards": 1,
        }

    high_plats = [p for p in raw_platforms if p[2] > 250.0]
    for p_idx, (_pname, px, py) in enumerate(high_plats[:4], start=1):
        plat_id = f"high_plat_{p_idx:02d}"
        draw_y = -py * 1.4 - 260.0 - (p_idx % 2) * 140.0
        geom[plat_id] = {
            "x": round(px - 200.0, 1),
            "y": round(draw_y - 95.0, 1),
            "w": 400.0,
            "h": 190.0,
            "cx": round(px, 1),
            "cy": round(draw_y, 1),
            "tiles": ["000000000000", "001111111100", "000000000000", "111111111111"],
            "strawberries": 0,
            "hazards": 1,
        }

    return geom if len(geom) == len(graph.vertices) else _fallback_layout(graph)


def _iter_edges(graph: GameGraph):
    """Itera sobre todas as arestas direcionadas de `graph.adjacency`."""
    for edge_list in graph.adjacency.values():
        for e in edge_list:
            yield e


def _fallback_layout(graph: GameGraph) -> dict[str, dict[str, object]]:
    """Layout em camadas BFS caso os binários originais da Steam não estejam presentes."""
    start_id = graph.start_id
    adj: dict[str, list[str]] = {v: [] for v in graph.vertices}
    for e in _iter_edges(graph):
        adj[e.origin].append(e.destination)
        adj[e.destination].append(e.origin)

    dist: dict[str, int] = {start_id: 0}
    dq = deque([start_id])
    while dq:
        u = dq.popleft()
        for v in sorted(adj.get(u, [])):
            if v not in dist:
                dist[v] = dist[u] + 1
                dq.append(v)

    by_layer: dict[int, list[str]] = {}
    for v_id in sorted(graph.vertices):
        d = dist.get(v_id, 0)
        by_layer.setdefault(d, []).append(v_id)

    geom: dict[str, dict[str, object]] = {}
    for d, nodes in sorted(by_layer.items()):
        for idx, v_id in enumerate(nodes):
            x = d * 320.0
            y = (idx - (len(nodes) - 1) / 2.0) * 220.0
            geom[v_id] = {
                "x": round(x - 110.0, 1),
                "y": round(y - 70.0, 1),
                "w": 220.0,
                "h": 140.0,
                "cx": round(x, 1),
                "cy": round(y, 1),
                "tiles": ["0000000000", "0000000000", "1111111111"],
                "strawberries": 1 if graph.vertices[v_id].collectible_value > 0 else 0,
                "hazards": 1,
            }
    return geom


def _build_step_telemetry(
    raw_graph: GameGraph,
    working_graph: GameGraph,
    route: RouteResult,
    alpha: float,
    waypoints_data: dict[str, object],
    geom: dict[str, dict[str, object]],
    expand_contracted_excursions: bool = False,
) -> list[dict[str, object]]:
    """Constrói a sequência passo a passo detalhada com as coordenadas físicas (`waypoints`) do player."""
    edge_lookup: dict[tuple[str, str], object] = {}
    for e in _iter_edges(raw_graph):
        if (e.origin, e.destination) not in edge_lookup:
            edge_lookup[(e.origin, e.destination)] = e
    work_edge_lookup: dict[tuple[str, str], object] = {}
    for e in _iter_edges(working_graph):
        if (e.origin, e.destination) not in work_edge_lookup:
            work_edge_lookup[(e.origin, e.destination)] = e

    edge_wpts_map: dict[str, list[list[float]]] = waypoints_data.get("edges", {})  # type: ignore[assignment]
    room_wpts_map: dict[str, dict[str, object]] = waypoints_data.get("rooms", {})  # type: ignore[assignment]

    def get_anchor_xy(room_id: str) -> list[float]:
        if room_id in room_wpts_map and "anchor" in room_wpts_map[room_id]:
            return list(room_wpts_map[room_id]["anchor"])  # type: ignore[arg-type]
        g = geom.get(room_id, {"cx": 0.0, "cy": 0.0})
        return [float(g["cx"]), float(g["cy"])]

    def get_transition_waypoints(u: str, v: str) -> list[list[float]]:
        key = f"{u}->{v}"
        if key in edge_wpts_map and edge_wpts_map[key]:
            return edge_wpts_map[key]
        return [get_anchor_xy(u), get_anchor_xy(v)]

    steps: list[dict[str, object]] = []
    cum_real = 0.0
    cum_eff = 0.0
    collected: set[str] = set()
    seen_discount: set[str] = set()

    if not route.path:
        return steps

    def append_excursion_steps(host_room: str, host_layer: int, contracted_list: list[str]) -> None:
        if not (expand_contracted_excursions and contracted_list):
            return
        allowed_sub = set(contracted_list)
        visited_sub: set[str] = {host_room}
        tour_moves: list[tuple[str, str, bool]] = []

        def dfs_tour(u_sub: str) -> None:
            neighbors = sorted(
                {
                    e_sub.destination
                    for e_sub in raw_graph.adjacency.get(u_sub, [])
                    if e_sub.destination in allowed_sub
                }
            )
            for v_sub in neighbors:
                if v_sub not in visited_sub:
                    visited_sub.add(v_sub)
                    tour_moves.append((u_sub, v_sub, True))
                    dfs_tour(v_sub)
                    tour_moves.append((v_sub, u_sub, False))

        dfs_tour(host_room)
        for u_mv, v_mv, is_forward in tour_moves:
            arrow_lbl = (
                f"↳ Trajeto TAS em beco contraído: {u_mv} -> {v_mv}"
                if is_forward
                else f"↲ Retorno físico do beco: {u_mv} -> {v_mv}"
            )
            steps.append(
                {
                    "room_id": v_mv,
                    "layer": host_layer,
                    "cum_real": round(cum_real, 2),
                    "cum_eff": round(cum_eff, 2),
                    "items_count": len(collected),
                    "collected_ids": sorted(collected),
                    "event": arrow_lbl,
                    "is_excursion": True,
                    "waypoints": get_transition_waypoints(u_mv, v_mv),
                }
            )

    first_node = route.path[0]
    if raw_graph.original_collectibles.get(first_node.room_id, 0.0) > 0:
        collected.add(first_node.room_id)
    first_contracted = working_graph.contracted_into.get(first_node.room_id, [])
    for c_id in first_contracted:
        if raw_graph.original_collectibles.get(c_id, 0.0) > 0:
            collected.add(c_id)
    seen_discount.add(first_node.room_id)
    start_xy = get_anchor_xy(first_node.room_id)

    steps.append(
        {
            "room_id": first_node.room_id,
            "layer": first_node.layer,
            "cum_real": 0.0,
            "cum_eff": 0.0,
            "items_count": len(collected),
            "collected_ids": sorted(collected),
            "event": "INÍCIO DA FASE (Spawn Real do Player)",
            "is_excursion": False,
            "contracted_children": first_contracted,
            "waypoints": [start_xy],
        }
    )
    append_excursion_steps(first_node.room_id, first_node.layer, first_contracted)

    for i in range(len(route.path) - 1):
        curr = route.path[i]
        nxt = route.path[i + 1]

        # Transição interna de ativação da ARMA (L0 -> L1 na mesma sala)
        if curr.room_id == nxt.room_id and curr.layer == 0 and nxt.layer == 1:
            anchor_xy = get_anchor_xy(nxt.room_id)
            steps.append(
                {
                    "room_id": nxt.room_id,
                    "layer": 1,
                    "cum_real": round(cum_real, 2),
                    "cum_eff": round(cum_eff, 2),
                    "items_count": len(collected),
                    "collected_ids": sorted(collected),
                    "event": f"ARMA ATIVADA EM {nxt.room_id} (Camada L0 -> L1: dificuldade reduzida!)",
                    "is_excursion": False,
                    "waypoints": [anchor_xy],
                }
            )
            continue

        edge = work_edge_lookup.get((curr.room_id, nxt.room_id)) or edge_lookup.get(
            (curr.room_id, nxt.room_id)
        )
        if edge is None:
            continue

        diff = edge.difficulty_with_weapon if curr.layer == 1 else edge.difficulty_no_weapon
        step_real = edge.base_time + diff

        dest_vertex = working_graph.vertices.get(nxt.room_id) or raw_graph.vertices[nxt.room_id]
        first_visit = nxt.room_id not in seen_discount
        c_val = dest_vertex.collectible_value if first_visit else 0.0
        step_eff = compute_effective_weight(
            base_time=edge.base_time,
            difficulty=diff,
            collectible_value=c_val,
            alpha=alpha,
        )

        cum_real += step_real
        cum_eff += step_eff
        seen_discount.add(nxt.room_id)

        if raw_graph.original_collectibles.get(nxt.room_id, 0.0) > 0:
            collected.add(nxt.room_id)

        contracted_here = working_graph.contracted_into.get(nxt.room_id, [])
        for c_id in contracted_here:
            if raw_graph.original_collectibles.get(c_id, 0.0) > 0:
                collected.add(c_id)

        event_msg = f"Player percorreu {curr.room_id} -> {nxt.room_id} [L{curr.layer}]"
        if contracted_here:
            event_msg += f" + coletou beco(s) contraído(s): {', '.join(contracted_here)}"

        steps.append(
            {
                "room_id": nxt.room_id,
                "layer": nxt.layer,
                "cum_real": round(cum_real, 2),
                "cum_eff": round(cum_eff, 2),
                "items_count": len(collected),
                "collected_ids": sorted(collected),
                "event": event_msg,
                "is_excursion": False,
                "contracted_children": contracted_here,
                "waypoints": get_transition_waypoints(curr.room_id, nxt.room_id),
            }
        )

        append_excursion_steps(nxt.room_id, nxt.layer, contracted_here)

    return steps


def build_map_simulation_payload(
    map_id: str,
    title: str,
    game: str,
    dataset_dir: Path,
    geom_fn,
    alpha: float = 0.05,
) -> dict[str, object]:
    """Calcula a geometria e as 3 rotas comparativas para um mapa."""
    raw_graph = load_graph_from_csv(dataset_dir)
    contracted_graph = contract_dead_ends(raw_graph)

    layered_raw = build_layered_graph(raw_graph, alpha=alpha)
    layered_contracted = build_layered_graph(contracted_graph, alpha=alpha)

    bfs_res = run_bfs(layered_contracted)
    dfs_res = run_dfs_branch_and_bound(layered_contracted, timeout_seconds=0.15)
    dijk_no_contract = run_dijkstra(layered_raw)
    stratgraph_res = run_dijkstra(layered_contracted)

    geom = geom_fn(raw_graph)
    wpts_file = dataset_dir / "waypoints.json"
    waypoints_data: dict[str, object] = {}
    if wpts_file.is_file():
        waypoints_data = json.loads(wpts_file.read_text(encoding="utf-8"))
        # Em Cuphead invertemos Y no Canvas para coincidir com a geometria desenhada
        if game == "Cuphead" and "edges" in waypoints_data:
            for k, pts in waypoints_data["edges"].items():  # type: ignore[union-attr]
                waypoints_data["edges"][k] = [[pt[0], round(-pt[1] * 1.4, 1)] for pt in pts]  # type: ignore[index]

    # Mapear quem foi contraído em quem
    contracted_parent_of: dict[str, str] = {}
    for parent_id, children in contracted_graph.contracted_into.items():
        for ch_id in children:
            contracted_parent_of[ch_id] = parent_id

    vertices_payload: list[dict[str, object]] = []
    for v_id, v in sorted(raw_graph.vertices.items()):
        g = geom.get(
            v_id,
            {"x": 0.0, "y": 0.0, "w": 160.0, "h": 100.0, "cx": 80.0, "cy": 50.0, "tiles": []},
        )
        vertices_payload.append(
            {
                "id": v_id,
                "type": v.room_type.value,
                "val": v.collectible_value,
                "has_weapon": v.has_weapon,
                "contracted_into": contracted_parent_of.get(v_id),
                "absorbed_children": contracted_graph.contracted_into.get(v_id, []),
                "x": g["x"],
                "y": g["y"],
                "w": g["w"],
                "h": g["h"],
                "cx": g["cx"],
                "cy": g["cy"],
                "tiles": g.get("tiles", []),
                "strawberries": g.get("strawberries", 0),
                "hazards": g.get("hazards", 0),
            }
        )

    seen_pairs: set[tuple[str, str]] = set()
    edges_payload: list[dict[str, object]] = []
    raw_edges = list(_iter_edges(raw_graph))
    reverse_lookup = {(e.origin, e.destination) for e in raw_edges}
    for e in raw_edges:
        if (e.origin, e.destination) in seen_pairs:
            continue
        seen_pairs.add((e.origin, e.destination))
        edges_payload.append(
            {
                "u": e.origin,
                "v": e.destination,
                "two_way": (e.destination, e.origin) in reverse_lookup,
                "base_time": e.base_time,
                "diff_l0": e.difficulty_no_weapon,
                "diff_l1": e.difficulty_with_weapon,
            }
        )

    return {
        "id": map_id,
        "title": title,
        "game": game,
        "alpha": alpha,
        "v_orig": len(raw_graph.vertices),
        "v_contracted": len(contracted_graph.vertices),
        "e_orig": len(raw_edges),
        "vertices": vertices_payload,
        "edges": edges_payload,
        "routes": {
            "bfs": {
                "name": "BFS (Com Contração — Coleta Itens em L0)",
                "real_cost": round(bfs_res.real_cost, 2),
                "eff_cost": round(bfs_res.effective_cost, 2),
                "items": bfs_res.collectibles_count,
                "used_weapon": bfs_res.used_weapon,
                "steps": _build_step_telemetry(
                    raw_graph, contracted_graph, bfs_res, alpha, waypoints_data, geom, True
                ),
            },
            "dfs": {
                "name": "DFS Branch-and-Bound (Com Contração)",
                "real_cost": round(dfs_res.real_cost, 2),
                "eff_cost": round(dfs_res.effective_cost, 2),
                "items": dfs_res.collectibles_count,
                "used_weapon": dfs_res.used_weapon,
                "steps": _build_step_telemetry(
                    raw_graph, contracted_graph, dfs_res, alpha, waypoints_data, geom, True
                ),
            },
            "no_contract": {
                "name": "Dijkstra (--no-contract — Sem Contração)",
                "real_cost": round(dijk_no_contract.real_cost, 2),
                "eff_cost": round(dijk_no_contract.effective_cost, 2),
                "items": dijk_no_contract.collectibles_count,
                "used_weapon": dijk_no_contract.used_weapon,
                "steps": _build_step_telemetry(
                    raw_graph, raw_graph, dijk_no_contract, alpha, waypoints_data, geom, False
                ),
            },
            "stratgraph": {
                "name": "StratGraph (Dijkstra + Camadas + Contração)",
                "real_cost": round(stratgraph_res.real_cost, 2),
                "eff_cost": round(stratgraph_res.effective_cost, 2),
                "items": stratgraph_res.collectibles_count,
                "used_weapon": stratgraph_res.used_weapon,
                "steps": _build_step_telemetry(
                    raw_graph, contracted_graph, stratgraph_res, alpha, waypoints_data, geom, True
                ),
            },
        },
    }


def collect_all_maps() -> list[dict[str, object]]:
    """Reúne os payloads de todos os mapas (Celeste, Cuphead e Sample Toy)."""
    maps: list[dict[str, object]] = []

    # 1. Capítulos do Celeste
    celeste_titles = {
        "1_forsaken_city": "Cap. 1 — Forsaken City",
        "2_old_site": "Cap. 2 — Old Site",
        "3_celestial_resort": "Cap. 3 — Celestial Resort",
        "4_golden_ridge": "Cap. 4 — Golden Ridge",
        "5_mirror_temple": "Cap. 5 — Mirror Temple",
        "6_reflection": "Cap. 6 — Reflection",
        "7_summit": "Cap. 7 — The Summit",
        "9_core": "Cap. 9 — Core",
    }
    for slug, bin_name in CHAPTER_FILES:
        ds_dir = Path("datasets/celeste") / slug
        if ds_dir.is_dir():
            maps.append(
                build_map_simulation_payload(
                    map_id=f"celeste_{slug}",
                    title=f"Celeste: {celeste_titles.get(slug, slug)}",
                    game="Celeste",
                    dataset_dir=ds_dir,
                    geom_fn=lambda g, s=slug, b=bin_name: _extract_celeste_geometry(s, b, g),
                    alpha=0.05,
                )
            )

    # 2. Fases Run-and-Gun do Cuphead
    for scene_idx, slug, title in CUPHEAD_RUN_AND_GUN_SCENES:
        ds_dir = Path("datasets/cuphead") / slug
        if ds_dir.is_dir():
            maps.append(
                build_map_simulation_payload(
                    map_id=f"cuphead_{slug}",
                    title=f"Cuphead: {title}",
                    game="Cuphead",
                    dataset_dir=ds_dir,
                    geom_fn=lambda g, idx=scene_idx: _extract_cuphead_geometry(idx, g),
                    alpha=0.05,
                )
            )

    # 3. Sample Toy Didático
    toy_dir = Path("datasets/sample_toy")
    if toy_dir.is_dir():
        maps.append(
            build_map_simulation_payload(
                map_id="sample_toy",
                title="Mapa Didático (Sample Toy — α = 0.50)",
                game="Sample",
                dataset_dir=toy_dir,
                geom_fn=_fallback_layout,
                alpha=0.50,
            )
        )

    return maps


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>StratGraph — Simulador Visual Interativo 2D (Celeste & Cuphead)</title>
<style>
  :root {
    --bg-dark: #0b0f19;
    --bg-panel: #131b2e;
    --bg-card: #1b253f;
    --border: #2a395c;
    --text: #e8eefb;
    --muted: #93a4c8;
    --strat-l0: #00e5ff;
    --strat-l1: #00ff88;
    --bfs-color: #ff5c77;
    --nocontract-color: #ffb830;
    --deadend-color: #c77dff;
    --weapon-color: #00ff88;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg-dark);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  header {
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    padding: 10px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand h1 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.3px;
  }
  .badge {
    font-size: 0.75rem;
    padding: 3px 8px;
    border-radius: 6px;
    background: rgba(0, 229, 255, 0.15);
    color: var(--strat-l0);
    border: 1px solid rgba(0, 229, 255, 0.35);
    font-weight: 600;
  }
  .controls-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  select, button {
    background: var(--bg-card);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.15s;
  }
  select:hover, button:hover {
    border-color: var(--strat-l0);
    background: #233154;
  }
  button.primary {
    background: linear-gradient(135deg, #00b4d8, #0077b6);
    border-color: #00e5ff;
    font-weight: 600;
    color: #fff;
  }
  .workspace {
    display: grid;
    grid-template-columns: 1fr 410px;
    flex: 1;
    min-height: 0;
  }
  .canvas-wrap {
    position: relative;
    background: radial-gradient(circle at center, #121a2d 0%, #090d16 100%);
    overflow: hidden;
  }
  canvas {
    width: 100%;
    height: 100%;
    display: block;
    cursor: grab;
  }
  canvas:active { cursor: grabbing; }
  .legend-overlay {
    position: absolute;
    top: 12px;
    left: 12px;
    background: rgba(19, 27, 46, 0.90);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.78rem;
    display: flex;
    flex-direction: column;
    gap: 6px;
    backdrop-filter: blur(6px);
  }
  .legend-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .swatch {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    display: inline-block;
  }
  .event-banner {
    position: absolute;
    bottom: 14px;
    left: 14px;
    right: 14px;
    background: rgba(19, 27, 46, 0.94);
    border: 1px solid var(--border);
    border-left: 4px solid var(--strat-l1);
    border-radius: 8px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .event-text {
    font-size: 0.9rem;
    font-weight: 600;
  }
  .sidebar {
    background: var(--bg-panel);
    border-left: 1px solid var(--border);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
  }
  .section-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--muted);
    font-weight: 700;
  }
  .route-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .route-card.strat { border-left: 4px solid var(--strat-l1); }
  .route-card.bfs { border-left: 4px solid var(--bfs-color); }
  .route-card.nocontract { border-left: 4px solid var(--nocontract-color); }
  .route-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.86rem;
    font-weight: 700;
  }
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-top: 2px;
  }
  .metric-box {
    background: rgba(11, 15, 25, 0.55);
    padding: 6px;
    border-radius: 5px;
    text-align: center;
  }
  .metric-val {
    font-size: 0.95rem;
    font-weight: 700;
  }
  .metric-lbl {
    font-size: 0.68rem;
    color: var(--muted);
  }
  .step-list {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
    overflow-y: auto;
    min-height: 180px;
    font-size: 0.78rem;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .step-item {
    padding: 6px 8px;
    border-radius: 5px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-left: 3px solid transparent;
  }
  .step-item:hover { background: rgba(255,255,255,0.05); }
  .step-item.active {
    background: rgba(0, 229, 255, 0.14);
    border-left-color: var(--strat-l0);
    font-weight: 600;
  }
  .step-item.excursion {
    color: #e0aaff;
    padding-left: 18px;
  }
  .toggle-group {
    display: flex;
    gap: 10px;
    font-size: 0.8rem;
    flex-wrap: wrap;
  }
  .toggle-group label {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>StratGraph — Simulador 2D de Rotas em Mapas Reais</h1>
    <span class="badge" id="mapStatsBadge">Carregando...</span>
  </div>
  <div class="controls-bar">
    <label for="mapSelect" style="font-size:0.82rem;color:var(--muted);">Mapa:</label>
    <select id="mapSelect"></select>
    <button class="primary" id="btnPlayPause">⏸ Pausar</button>
    <button id="btnPrev">⏮ Passo</button>
    <button id="btnNext">Passo ⏭</button>
    <button id="btnReset">↺ Reiniciar</button>
    <button id="btnFit">⛶ Ajustar Câmera</button>
    <select id="speedSelect" title="Velocidade da simulação">
      <option value="950">0.5x</option>
      <option value="520" selected>1.0x</option>
      <option value="260">2.0x</option>
      <option value="120">4.0x</option>
    </select>
  </div>
</header>

<div class="workspace">
  <div class="canvas-wrap">
    <canvas id="simCanvas"></canvas>
    <div class="legend-overlay">
      <div style="font-weight:700;margin-bottom:2px;color:#fff;">Legenda do Mapa & Camadas</div>
      <div class="legend-row"><span class="swatch" style="background:#00e5ff;"></span> StratGraph Camada L0 (Sem Arma)</div>
      <div class="legend-row"><span class="swatch" style="background:#00ff88;"></span> StratGraph Camada L1 (Com Arma — Dificuldade Reduzida)</div>
      <div class="legend-row"><span class="swatch" style="background:#c77dff;"></span> Beco Sem Saída Contraído (Coleta Garantida)</div>
      <div class="legend-row"><span class="swatch" style="background:#ffb830;"></span> Dijkstra sem contração (--no-contract)</div>
      <div class="legend-row"><span class="swatch" style="background:#ff5c77;"></span> BFS Baseline (Menor nº de salas, ignora arma/pesos)</div>
      <div class="toggle-group" style="margin-top:4px;padding-top:6px;border-top:1px solid var(--border);">
        <label><input type="checkbox" id="chkStrat" checked /> StratGraph</label>
        <label><input type="checkbox" id="chkNoContract" checked /> --no-contract</label>
        <label><input type="checkbox" id="chkBfs" checked /> BFS</label>
      </div>
    </div>
    <div class="event-banner">
      <div>
        <div style="font-size:0.72rem;color:var(--muted);" id="stepCounterText">Passo 0 / 0</div>
        <div class="event-text" id="eventBannerText">Selecione um mapa ou pressione Play.</div>
      </div>
      <input type="range" id="stepSlider" min="0" max="10" value="0" style="width:220px;" />
    </div>
  </div>

  <aside class="sidebar">
    <div class="section-title">Comparação de Efetividade das Rotas (Total Final)</div>

    <div class="route-card strat">
      <div class="route-header">
        <span style="color:var(--strat-l1);">★ StratGraph (Camadas + Contração)</span>
        <span id="stratLayerBadge" class="badge">L0 -> L1</span>
      </div>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-val" id="stratReal">0</div><div class="metric-lbl">Custo Real</div></div>
        <div class="metric-box"><div class="metric-val" id="stratEff" style="color:var(--strat-l1);">0</div><div class="metric-lbl">Peso Efetivo</div></div>
        <div class="metric-box"><div class="metric-val" id="stratItems" style="color:#ffd166;">0</div><div class="metric-lbl">Itens</div></div>
        <div class="metric-box"><div class="metric-val" id="stratStepNow">0</div><div class="metric-lbl">Sala Atual</div></div>
      </div>
    </div>

    <div class="route-card nocontract">
      <div class="route-header">
        <span style="color:var(--nocontract-color);">Dijkstra (--no-contract)</span>
        <span id="ncLayerBadge" class="badge" style="color:var(--nocontract-color);border-color:var(--nocontract-color);">Sem Contração</span>
      </div>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-val" id="ncReal">0</div><div class="metric-lbl">Custo Real</div></div>
        <div class="metric-box"><div class="metric-val" id="ncEff">0</div><div class="metric-lbl">Peso Efetivo</div></div>
        <div class="metric-box"><div class="metric-val" id="ncItems">0</div><div class="metric-lbl">Itens</div></div>
        <div class="metric-box"><div class="metric-val" id="ncStepNow">-</div><div class="metric-lbl">Sala Atual</div></div>
      </div>
    </div>

    <div class="route-card bfs">
      <div class="route-header">
        <span style="color:var(--bfs-color);">BFS Baseline (Menor nº de saltos)</span>
        <span class="badge" style="color:var(--bfs-color);border-color:var(--bfs-color);">Apenas L0</span>
      </div>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-val" id="bfsReal">0</div><div class="metric-lbl">Custo Real</div></div>
        <div class="metric-box"><div class="metric-val" id="bfsEff">0</div><div class="metric-lbl">Peso Efetivo</div></div>
        <div class="metric-box"><div class="metric-val" id="bfsItems">0</div><div class="metric-lbl">Itens</div></div>
        <div class="metric-box"><div class="metric-val" id="bfsStepNow">-</div><div class="metric-lbl">Sala Atual</div></div>
      </div>
    </div>

    <div class="section-title">Passo a Passo da Rota StratGraph (Clique p/ focar)</div>
    <div class="step-list" id="stepListContainer"></div>
  </aside>
</div>

<script>
const MAPS_DATA = __MAPS_JSON_PAYLOAD__;

const canvas = document.getElementById('simCanvas');
const ctx = canvas.getContext('2d');
const mapSelect = document.getElementById('mapSelect');
const stepSlider = document.getElementById('stepSlider');
const stepListContainer = document.getElementById('stepListContainer');

let currentMap = MAPS_DATA[0];
let currentStepIdx = 0;
let isPlaying = true;
let playIntervalMs = 520;
let lastTick = performance.now();

// Câmera 2D (Pan & Zoom)
let cam = { x: 0, y: 0, scale: 1 };
let isDragging = false;
let dragStart = { x: 0, y: 0 };

function initMapSelect() {
  MAPS_DATA.forEach((m, idx) => {
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = m.title;
    mapSelect.appendChild(opt);
  });
  mapSelect.addEventListener('change', () => {
    loadMap(parseInt(mapSelect.value, 10));
  });
}

function fitCameraToMap() {
  if (!currentMap || !currentMap.vertices.length) return;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  currentMap.vertices.forEach(v => {
    minX = Math.min(minX, v.x);
    minY = Math.min(minY, v.y);
    maxX = Math.max(maxX, v.x + v.w);
    maxY = Math.max(maxY, v.y + v.h);
  });
  const mapW = Math.max(200, maxX - minX);
  const mapH = Math.max(200, maxY - minY);
  const pad = 90;
  const scaleX = (rect.width - pad * 2) / mapW;
  const scaleY = (rect.height - pad * 2) / mapH;
  cam.scale = Math.min(scaleX, scaleY);
  cam.x = rect.width / 2 - (minX + mapW / 2) * cam.scale;
  cam.y = rect.height / 2 - (minY + mapH / 2) * cam.scale;
}

function focusOnRoom(roomId) {
  const v = currentMap.vertices.find(r => r.id === roomId);
  if (!v) return;
  const rect = canvas.getBoundingClientRect();
  cam.x = rect.width / 2 - v.cx * cam.scale;
  cam.y = rect.height / 2 - v.cy * cam.scale;
}

function loadMap(idx) {
  currentMap = MAPS_DATA[idx];
  currentStepIdx = 0;
  const stratSteps = currentMap.routes.stratgraph.steps;
  stepSlider.max = Math.max(0, stratSteps.length - 1);
  stepSlider.value = 0;

  const reductionPct = (((currentMap.v_orig - currentMap.v_contracted) / currentMap.v_orig) * 100).toFixed(1);
  document.getElementById('mapStatsBadge').textContent =
    `|V|=${currentMap.v_orig} → |V'|=${currentMap.v_contracted} (-${reductionPct}% becos) | α=${currentMap.alpha}`;

  document.getElementById('stratReal').textContent = currentMap.routes.stratgraph.real_cost.toFixed(1);
  document.getElementById('stratEff').textContent = currentMap.routes.stratgraph.eff_cost.toFixed(1);
  document.getElementById('stratItems').textContent = currentMap.routes.stratgraph.items;
  document.getElementById('stratLayerBadge').textContent =
    currentMap.routes.stratgraph.used_weapon ? 'Ativa Arma (L0→L1)' : 'Camada L0';

  document.getElementById('ncReal').textContent = currentMap.routes.no_contract.real_cost.toFixed(1);
  document.getElementById('ncEff').textContent = currentMap.routes.no_contract.eff_cost.toFixed(1);
  document.getElementById('ncItems').textContent = currentMap.routes.no_contract.items;

  document.getElementById('bfsReal').textContent = currentMap.routes.bfs.real_cost.toFixed(1);
  document.getElementById('bfsEff').textContent = currentMap.routes.bfs.eff_cost.toFixed(1);
  document.getElementById('bfsItems').textContent = currentMap.routes.bfs.items;

  stepListContainer.innerHTML = '';
  stratSteps.forEach((st, sIdx) => {
    const div = document.createElement('div');
    div.className = 'step-item' + (st.is_excursion ? ' excursion' : '');
    div.innerHTML = `
      <span>${sIdx + 1}. <strong>${st.room_id}</strong> <small>[L${st.layer}]</small></span>
      <span>w=${st.cum_eff.toFixed(1)} | 🍓${st.items_count}</span>
    `;
    div.addEventListener('click', () => {
      isPlaying = false;
      updatePlayButton();
      setStep(sIdx);
      focusOnRoom(st.room_id);
    });
    stepListContainer.appendChild(div);
  });

  fitCameraToMap();
  setStep(0);
}

function setStep(idx) {
  const stratSteps = currentMap.routes.stratgraph.steps;
  if (!stratSteps.length) return;
  currentStepIdx = Math.max(0, Math.min(stratSteps.length - 1, idx));
  stepSlider.value = currentStepIdx;

  const st = stratSteps[currentStepIdx];
  document.getElementById('stepCounterText').textContent =
    `Passo ${currentStepIdx + 1} de ${stratSteps.length} — Camada L${st.layer} | Custo Real Acumulado: ${st.cum_real.toFixed(1)} | Peso Efetivo: ${st.cum_eff.toFixed(1)} | Itens Coletados: ${st.items_count}`;
  document.getElementById('eventBannerText').textContent = st.event;
  document.getElementById('stratStepNow').textContent = `${st.room_id} (L${st.layer})`;

  const ncSteps = currentMap.routes.no_contract.steps;
  const ncSt = ncSteps[Math.min(currentStepIdx, ncSteps.length - 1)];
  if (ncSt) document.getElementById('ncStepNow').textContent = `${ncSt.room_id} (L${ncSt.layer})`;

  const bfsSteps = currentMap.routes.bfs.steps;
  const bfsSt = bfsSteps[Math.min(currentStepIdx, bfsSteps.length - 1)];
  if (bfsSt) document.getElementById('bfsStepNow').textContent = `${bfsSt.room_id} (L${bfsSt.layer})`;

  Array.from(stepListContainer.children).forEach((el, i) => {
    el.classList.toggle('active', i === currentStepIdx);
    if (i === currentStepIdx) {
      el.scrollIntoView({ block: 'nearest' });
    }
  });
}

function updatePlayButton() {
  document.getElementById('btnPlayPause').textContent = isPlaying ? '⏸ Pausar' : '▶ Play';
}

function drawRoutePolyline(steps, upToIdx, subProgress, colorL0, colorL1, lineWidth, dashed, offsetPx) {
  if (!steps || steps.length < 2) return null;
  const vMap = {};
  currentMap.vertices.forEach(v => { vMap[v.id] = v; });

  const limit = Math.min(upToIdx, steps.length - 1);
  let currentMarkerPos = null;

  for (let i = 1; i <= limit; i++) {
    const st = steps[i];
    const prevSt = steps[i - 1];
    const pts = (st.waypoints && st.waypoints.length >= 2)
      ? st.waypoints
      : [
          [vMap[prevSt.room_id] ? vMap[prevSt.room_id].cx : 0, vMap[prevSt.room_id] ? vMap[prevSt.room_id].cy : 0],
          [vMap[st.room_id] ? vMap[st.room_id].cx : 0, vMap[st.room_id] ? vMap[st.room_id].cy : 0]
        ];

    const isLastActiveSeg = (i === limit);
    const maxPtFloat = isLastActiveSeg ? subProgress * (pts.length - 1) : (pts.length - 1);
    const fullCount = Math.floor(maxPtFloat);
    const frac = maxPtFloat - fullCount;

    ctx.save();
    ctx.beginPath();
    if (dashed) ctx.setLineDash([8 / cam.scale, 6 / cam.scale]);
    const isExcursion = st.is_excursion || prevSt.is_excursion;
    ctx.strokeStyle = isExcursion ? '#c77dff' : (prevSt.layer === 1 ? colorL1 : colorL0);
    ctx.lineWidth = lineWidth / cam.scale;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    ctx.moveTo(pts[0][0] + offsetPx, pts[0][1] + offsetPx);
    for (let k = 1; k <= fullCount && k < pts.length; k++) {
      ctx.lineTo(pts[k][0] + offsetPx, pts[k][1] + offsetPx);
    }
    if (fullCount < pts.length - 1 && frac > 0) {
      const pA = pts[fullCount];
      const pB = pts[fullCount + 1];
      const ix = pA[0] + (pB[0] - pA[0]) * frac;
      const iy = pA[1] + (pB[1] - pA[1]) * frac;
      ctx.lineTo(ix + offsetPx, iy + offsetPx);
      currentMarkerPos = [ix, iy];
    } else {
      const pEnd = pts[Math.min(pts.length - 1, fullCount)];
      currentMarkerPos = [pEnd[0], pEnd[1]];
    }
    ctx.stroke();
    ctx.restore();
  }

  if (!currentMarkerPos && steps[0]) {
    const v0 = vMap[steps[0].room_id];
    currentMarkerPos = (steps[0].waypoints && steps[0].waypoints[0])
      ? steps[0].waypoints[0]
      : (v0 ? [v0.cx, v0.cy] : [0, 0]);
  }
  return currentMarkerPos;
}

function drawAgentMarkerAt(posXY, color, label, offsetPx) {
  if (!posXY) return;
  const r = 10 / cam.scale;
  ctx.save();
  ctx.beginPath();
  ctx.arc(posXY[0] + offsetPx, posXY[1] + offsetPx, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 14;
  ctx.fill();
  ctx.lineWidth = 2.2 / cam.scale;
  ctx.strokeStyle = '#0b0f19';
  ctx.stroke();

  ctx.font = `bold ${Math.max(10, 11 / cam.scale)}px Segoe UI`;
  ctx.fillStyle = '#fff';
  ctx.textAlign = 'center';
  ctx.fillText(label, posXY[0] + offsetPx, posXY[1] + offsetPx - r - 4 / cam.scale);
  ctx.restore();
}

function render(now) {
  if (isPlaying && now - lastTick >= playIntervalMs) {
    lastTick = now;
    const stratSteps = currentMap.routes.stratgraph.steps;
    if (currentStepIdx < stratSteps.length - 1) {
      setStep(currentStepIdx + 1);
    } else {
      setStep(0);
    }
  }

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
  }

  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);

  ctx.translate(cam.x, cam.y);
  ctx.scale(cam.scale, cam.scale);

  const vMap = {};
  currentMap.vertices.forEach(v => { vMap[v.id] = v; });

  // 1. Desenhar arestas base do grafo
  currentMap.edges.forEach(e => {
    const u = vMap[e.u];
    const v = vMap[e.v];
    if (!u || !v) return;
    ctx.beginPath();
    ctx.strokeStyle = e.two_way ? 'rgba(147, 164, 200, 0.22)' : 'rgba(255, 184, 48, 0.35)';
    ctx.lineWidth = 1.5 / cam.scale;
    ctx.moveTo(u.cx, u.cy);
    ctx.lineTo(v.cx, v.cy);
    ctx.stroke();
  });

  // 2. Desenhar salas reais (com tiles <solids> do Celeste / plataformas do Cuphead)
  const stratSteps = currentMap.routes.stratgraph.steps;
  const activeSt = stratSteps[currentStepIdx] || stratSteps[0];
  const collectedSet = new Set(activeSt ? activeSt.collected_ids : []);

  currentMap.vertices.forEach(v => {
    const isContractedChild = Boolean(v.contracted_into);
    const isCollected = collectedSet.has(v.id);

    let fill = 'rgba(27, 37, 63, 0.82)';
    let stroke = '#334670';
    if (v.type === 'INICIO') { fill = 'rgba(0, 180, 216, 0.28)'; stroke = '#00e5ff'; }
    else if (v.type === 'FIM') { fill = 'rgba(255, 92, 119, 0.28)'; stroke = '#ff5c77'; }
    else if (v.type === 'ARMA' || v.has_weapon) { fill = 'rgba(0, 255, 136, 0.26)'; stroke = '#00ff88'; }
    else if (isContractedChild) { fill = 'rgba(199, 125, 255, 0.22)'; stroke = '#c77dff'; }
    else if (v.val > 0) { fill = 'rgba(255, 209, 102, 0.20)'; stroke = '#ffd166'; }

    ctx.fillStyle = fill;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = (activeSt && activeSt.room_id === v.id ? 3.2 : 1.4) / cam.scale;
    ctx.fillRect(v.x, v.y, v.w, v.h);

    // Desenhar matriz <solids> real dentro da sala
    if (v.tiles && v.tiles.length) {
      const rows = v.tiles.length;
      const cols = v.tiles[0].length;
      const cw = v.w / cols;
      const ch = v.h / rows;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
      for (let r = 0; r < rows; r++) {
        const line = v.tiles[r];
        for (let c = 0; c < cols; c++) {
          if (line[c] === '1') {
            ctx.fillRect(v.x + c * cw, v.y + r * ch, cw, ch);
          }
        }
      }
    }

    ctx.strokeRect(v.x, v.y, v.w, v.h);

    // Rótulo da sala e ícones
    const fontSize = Math.max(9, Math.min(18, v.w * 0.11));
    ctx.font = `bold ${fontSize}px Segoe UI`;
    ctx.fillStyle = '#f8f9fa';
    ctx.textAlign = 'center';
    let badge = '';
    if (v.type === 'INICIO') badge = '▶ ';
    else if (v.type === 'FIM') badge = '🏁 ';
    else if (v.has_weapon) badge = '⚡ARMA ';
    else if (v.val > 0) badge = isCollected ? '✅ ' : '🍓 ';
    ctx.fillText(`${badge}${v.id}`, v.cx, v.cy + fontSize * 0.35);
  });

  // 3. Desenhar trilhas físicas (waypoints TAS tile-a-tile) das 3 rotas até o passo atual
  const showBfs = document.getElementById('chkBfs').checked;
  const showNc = document.getElementById('chkNoContract').checked;
  const showStrat = document.getElementById('chkStrat').checked;

  const bfsSteps = currentMap.routes.bfs.steps;
  const ncSteps = currentMap.routes.no_contract.steps;
  const subProg = isPlaying ? Math.min(1.0, (now - lastTick) / Math.max(1, playIntervalMs)) : 1.0;

  if (showBfs) {
    const posBfs = drawRoutePolyline(bfsSteps, currentStepIdx, subProg, '#ff5c77', '#ff5c77', 2.8, true, -6 / cam.scale);
    drawAgentMarkerAt(posBfs, '#ff5c77', 'BFS', -6 / cam.scale);
  }
  if (showNc) {
    const posNc = drawRoutePolyline(ncSteps, currentStepIdx, subProg, '#ffb830', '#ffb830', 3.0, false, 6 / cam.scale);
    drawAgentMarkerAt(posNc, '#ffb830', 'No-Contract', 6 / cam.scale);
  }
  if (showStrat) {
    const posStrat = drawRoutePolyline(stratSteps, currentStepIdx, subProg, '#00e5ff', '#00ff88', 4.5, false, 0);
    const stNow = stratSteps[currentStepIdx];
    const stratColor = stNow && stNow.layer === 1 ? '#00ff88' : '#00e5ff';
    drawAgentMarkerAt(posStrat, stratColor, `Player TAS (L${stNow ? stNow.layer : 0})`, 0);
  }

  ctx.restore();
  requestAnimationFrame(render);
}

// Eventos de Controles
document.getElementById('btnPlayPause').addEventListener('click', () => {
  isPlaying = !isPlaying;
  updatePlayButton();
});
document.getElementById('btnPrev').addEventListener('click', () => {
  isPlaying = false;
  updatePlayButton();
  setStep(currentStepIdx - 1);
});
document.getElementById('btnNext').addEventListener('click', () => {
  isPlaying = false;
  updatePlayButton();
  setStep(currentStepIdx + 1);
});
document.getElementById('btnReset').addEventListener('click', () => {
  setStep(0);
});
document.getElementById('btnFit').addEventListener('click', fitCameraToMap);
document.getElementById('speedSelect').addEventListener('change', (e) => {
  playIntervalMs = parseInt(e.target.value, 10);
});
stepSlider.addEventListener('input', (e) => {
  isPlaying = false;
  updatePlayButton();
  setStep(parseInt(e.target.value, 10));
});

// Zoom e Pan no Canvas
canvas.addEventListener('mousedown', (e) => {
  isDragging = true;
  dragStart = { x: e.clientX - cam.x, y: e.clientY - cam.y };
});
window.addEventListener('mousemove', (e) => {
  if (!isDragging) return;
  cam.x = e.clientX - dragStart.x;
  cam.y = e.clientY - dragStart.y;
});
window.addEventListener('mouseup', () => { isDragging = false; });
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const zoom = e.deltaY < 0 ? 1.14 : 0.88;
  cam.x = mx - (mx - cam.x) * zoom;
  cam.y = my - (my - cam.y) * zoom;
  cam.scale = Math.max(0.02, Math.min(12, cam.scale * zoom));
}, { passive: false });
window.addEventListener('resize', fitCameraToMap);

initMapSelect();
loadMap(0);
requestAnimationFrame(render);
</script>
</body>
</html>
"""


def generate_simulator_html(out_path: Path = DEFAULT_OUT_HTML) -> Path:
    """Gera o arquivo HTML interativo autocontido com todos os mapas reais e rotas."""
    maps_payload = collect_all_maps()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = HTML_TEMPLATE.replace(
        "__MAPS_JSON_PAYLOAD__", json.dumps(maps_payload, ensure_ascii=False)
    )
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o Simulador Visual Interativo 2D (HTML5 Canvas) do StratGraph."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT_HTML,
        help="Caminho do arquivo HTML gerado (padrão: results/stratgraph_simulator.html).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abre automaticamente o simulador no navegador padrão após gerar.",
    )
    args = parser.parse_args()

    out_file = generate_simulator_html(args.output)
    print(f"Simulador Visual 2D gerado com sucesso: {out_file} ({out_file.stat().st_size} bytes)")
    if args.open:
        webbrowser.open(out_file.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
