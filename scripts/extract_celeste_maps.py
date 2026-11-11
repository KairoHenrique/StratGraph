"""Extrator oficial de mapas binários (.bin) de Celeste com Pathfinding Físico Intra-Sala.

Lê diretamente os arquivos BinaryPacker (`Content/Maps/*.bin`) da instalação do Celeste,
reconstrói o grid físico de colisão 8x8 (`<solids>`), plataformas (`jumpThru`), molas
(`spring`), impulsos (`booster`, `zipMover`, `swapBlock`, `moveBlock`, `dreamBlock`),
coletáveis (`strawberry`, `cassette`, `blackGem`) e perigos (`spikes*`, `spinner`, etc.).

Para cada transição entre salas adjacentes (u -> v), simula a movimentação física do
jogador bloco a bloco (A* no grid 8x8 respeitando paredes sólidas, gravidade/apoio de
pulo/escalada e desvio de espinhos) desde a porta de entrada, passando pelos coletáveis
da sala até a porta de saída/checkpoint:
  - `tempo_base`: tempo real em segundos do trajeto percorrido pelo player dentro da sala;
  - `dificuldade_sem_arma` / `dificuldade_com_arma`: exposição real aos obstáculos ao
    longo dos blocos efetivamente percorridos pelo player;
  - `waypoints.json`: coordenadas exatas (x, y) passo a passo do trajeto físico do player
    para execução estilo TAS no Simulador 2D e no Mod In-Game.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import csv
import heapq
import json
import math
from pathlib import Path
import struct

DEFAULT_STEAM_MAPS_DIR = Path(r"D:\SteamLibrary\steamapps\common\Celeste\Content\Maps")
OUTPUT_BASE_DIR = Path("datasets/celeste")

CHAPTER_FILES = [
    ("1_forsaken_city", "1-ForsakenCity.bin"),
    ("2_old_site", "2-OldSite.bin"),
    ("3_celestial_resort", "3-CelestialResort.bin"),
    ("4_golden_ridge", "4-GoldenRidge.bin"),
    ("5_mirror_temple", "5-MirrorTemple.bin"),
    ("6_reflection", "6-Reflection.bin"),
    ("7_summit", "7-Summit.bin"),
    ("9_core", "9-Core.bin"),
]

HAZARD_WEIGHTS = {
    "spikesUp": 1.8,
    "spikesDown": 1.8,
    "spikesLeft": 1.8,
    "spikesRight": 1.8,
    "triggerSpikesUp": 2.2,
    "triggerSpikesDown": 2.2,
    "triggerSpikesLeft": 2.2,
    "triggerSpikesRight": 2.2,
    "spinner": 1.5,
    "rotateSpinner": 2.5,
    "trackSpinner": 2.5,
    "fallingBlock": 2.0,
    "crushBlock": 3.0,
    "MoveBlock": 2.0,
    "swapBlock": 2.0,
    "zipMover": 2.0,
    "seeker": 4.5,
    "angryOshiro": 4.0,
    "finalBoss": 5.0,
    "fireBall": 3.0,
    "iceBlock": 2.5,
    "bounceBlock": 2.0,
    "dreamBlock": 1.5,
}

COLLECTIBLE_ENTITIES = {
    "strawberry": 5.0,
    "cassette": 12.0,
    "blackGem": 15.0,
    "reflectionHeartStatue": 15.0,
}

ASSIST_ENTITIES = {
    "spring",
    "wallSpringLeft",
    "wallSpringRight",
    "booster",
    "refill",
    "zipMover",
    "swapBlock",
    "MoveBlock",
    "dreamBlock",
    "cloud",
    "movingPlatform",
    "sinkingPlatform",
}


def _read_7bit_str(buf: bytes, pos: int) -> tuple[str, int]:
    length = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        length |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return buf[pos : pos + length].decode("utf-8", errors="replace"), pos + length


def parse_celeste_bin(path: Path) -> tuple[str, tuple]:
    """Faz o parse completo de um arquivo `.bin` do Celeste (formato Monocle BinaryPacker)."""
    buf = path.read_bytes()
    pos = 0
    _, pos = _read_7bit_str(buf, pos)
    pkg, pos = _read_7bit_str(buf, pos)
    (lut_len,) = struct.unpack_from("<h", buf, pos)
    pos += 2
    lut: list[str] = []
    for _ in range(lut_len):
        s, pos = _read_7bit_str(buf, pos)
        lut.append(s)

    def read_elem(p: int) -> tuple[tuple[str, dict, list], int]:
        name = lut[struct.unpack_from("<h", buf, p)[0]]
        p += 2
        ac = buf[p]
        p += 1
        attrs: dict[str, object] = {}
        for _ in range(ac):
            k = lut[struct.unpack_from("<h", buf, p)[0]]
            p += 2
            t = buf[p]
            p += 1
            if t == 0:
                v: object = bool(buf[p])
                p += 1
            elif t == 1:
                v = buf[p]
                p += 1
            elif t == 2:
                (v,) = struct.unpack_from("<h", buf, p)
                p += 2
            elif t == 3:
                (v,) = struct.unpack_from("<i", buf, p)
                p += 4
            elif t == 4:
                (v,) = struct.unpack_from("<f", buf, p)
                p += 4
            elif t == 5:
                v = lut[struct.unpack_from("<h", buf, p)[0]]
                p += 2
            elif t == 6:
                v, p = _read_7bit_str(buf, p)
            elif t == 7:
                (blen,) = struct.unpack_from("<h", buf, p)
                p += 2
                out = bytearray()
                end = p + blen
                while p < end:
                    out.extend([buf[p + 1]] * buf[p])
                    p += 2
                v = out.decode("utf-8", errors="replace")
            else:
                raise ValueError(f"Tipo de atributo desconhecido no BinaryPacker: {t}")
            attrs[k] = v
        (cc,) = struct.unpack_from("<h", buf, p)
        p += 2
        children = []
        for _ in range(cc):
            c, p = read_elem(p)
            children.append(c)
        return (name, attrs, children), p

    root, _ = read_elem(pos)
    return pkg, root


def _get_solids_grid(lvl_elem: tuple, w_tiles: int, h_tiles: int) -> list[list[bool]]:
    """Retorna matriz `[row][col]` onde `True` indica espaço livre ('0') e `False` bloco sólido."""
    solids_text = ""
    for ch in lvl_elem[2]:
        if ch[0] == "solids":
            solids_text = str(ch[1].get("innerText", ""))
            break
    rows = solids_text.split("\n")
    grid: list[list[bool]] = []
    for r in range(h_tiles):
        row_str = rows[r].rstrip("\r") if r < len(rows) else ""
        grid_row = []
        for c in range(w_tiles):
            ch = row_str[c] if c < len(row_str) else "0"
            grid_row.append(ch == "0")
        grid.append(grid_row)
    return grid


def _build_room_navigation_maps(
    grid: list[list[bool]],
    entities: list[tuple[str, dict]],
    wt: int,
    ht: int,
) -> tuple[list[list[float]], list[list[float]], list[tuple[int, int]], list[tuple[int, int]]]:
    """Constrói mapas de custo de locomoção e risco tile-a-tile (8x8) para o player na sala.

    Retorna:
        - `step_cost[r][c]`: custo de movimento do player no tile (considerando plataformas,
          escalada em parede, gravidade e blocos móveis);
        - `hazard_map[r][c]`: risco local de espinhos/spinners naquele tile;
        - `collectible_tiles`: lista de coordenadas `(r, c)` dos coletáveis na sala;
        - `spawn_tiles`: lista de coordenadas `(r, c)` de pontos `player` na sala.
    """
    jumpthru = [[False] * wt for _ in range(ht)]
    assist = [[False] * wt for _ in range(ht)]
    hazard_map = [[0.0] * wt for _ in range(ht)]
    collectible_tiles: list[tuple[int, int]] = []
    spawn_tiles: list[tuple[int, int]] = []

    for ename, attrs in entities:
        ex = float(attrs.get("x", 0.0))
        ey = float(attrs.get("y", 0.0))
        ew = max(8.0, float(attrs.get("width", 8.0)))
        eh = max(8.0, float(attrs.get("height", 8.0)))
        c0 = max(0, min(wt - 1, int(ex // 8)))
        r0 = max(0, min(ht - 1, int(ey // 8)))
        c1 = max(c0, min(wt - 1, int((ex + ew - 1) // 8)))
        r1 = max(r0, min(ht - 1, int((ey + eh - 1) // 8)))

        if ename == "player":
            spawn_tiles.append((r0, c0))
        elif ename in COLLECTIBLE_ENTITIES:
            collectible_tiles.append((r0, c0))
        elif ename == "jumpThru":
            for cc in range(c0, c1 + 1):
                jumpthru[r0][cc] = True
        elif ename in ASSIST_ENTITIES:
            for rr in range(max(0, r0 - 2), min(ht, r1 + 3)):
                for cc in range(max(0, c0 - 2), min(wt, c1 + 3)):
                    assist[rr][cc] = True

        if ename in HAZARD_WEIGHTS:
            hw = HAZARD_WEIGHTS[ename]
            for rr in range(max(0, r0 - 1), min(ht, r1 + 2)):
                for cc in range(max(0, c0 - 1), min(wt, c1 + 2)):
                    dist = abs(rr - r0) + abs(cc - c0)
                    hazard_map[rr][cc] += hw * (1.0 if dist == 0 else 0.45)

    # Calcular apoio físico (chão abaixo a até 4 tiles, parede lateral a até 2 tiles ou assist)
    step_cost = [[1.0] * wt for _ in range(ht)]
    for r in range(ht):
        for c in range(wt):
            if not grid[r][c]:
                # Bloco sólido: muito caro atravessar (só permite se for bloco destrutível/dashBlock sem alternativa)
                step_cost[r][c] = 45.0
                continue

            near_floor = False
            for dr in range(1, 5):
                rr = r + dr
                if rr >= ht or not grid[rr][c] or jumpthru[rr][c]:
                    near_floor = True
                    break

            near_wall = False
            for dc in (-2, -1, 1, 2):
                cc = c + dc
                if 0 <= cc < wt and not grid[r][cc]:
                    near_wall = True
                    break

            if assist[r][c]:
                step_cost[r][c] = 0.75
            elif near_floor or jumpthru[r][c]:
                step_cost[r][c] = 1.0
            elif near_wall:
                step_cost[r][c] = 1.25  # escalada / walljump
            else:
                step_cost[r][c] = 1.65  # arco aéreo / dash

    return step_cost, hazard_map, collectible_tiles, spawn_tiles


def _astar_tile_path(
    grid: list[list[bool]],
    step_cost: list[list[float]],
    hazard_map: list[list[float]],
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
) -> tuple[list[tuple[int, int]], float, float, bool]:
    """Executa A* físico no grid 8x8 da sala entre `start_rc` e `goal_rc`.

    Retorna `(tiles_path, walk_tiles_dist, hazard_exposure, pierced_solid)`.
    """
    ht = len(grid)
    wt = len(grid[0]) if ht else 0
    sr, sc = max(0, min(ht - 1, start_rc[0])), max(0, min(wt - 1, start_rc[1]))
    gr, gc = max(0, min(ht - 1, goal_rc[0])), max(0, min(wt - 1, goal_rc[1]))

    if (sr, sc) == (gr, gc):
        return [(sr, sc)], 1.0, hazard_map[sr][sc], False

    INF = float("inf")
    dist = [[INF] * wt for _ in range(ht)]
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    dist[sr][sc] = 0.0

    # 8 direções (horizontal, vertical e diagonal de pulo/dash)
    dirs = [
        (0, 1, 1.0),
        (0, -1, 1.0),
        (1, 0, 0.9),   # queda a favor da gravidade é mais rápida
        (-1, 0, 1.35), # subida exige pulo/escalada/dash
        (1, 1, 1.3),
        (1, -1, 1.3),
        (-1, 1, 1.55),
        (-1, -1, 1.55),
    ]

    pq: list[tuple[float, int, int]] = [(0.0, sr, sc)]
    while pq:
        _f, r, c = heapq.heappop(pq)
        if (r, c) == (gr, gc):
            break
        cur_g = dist[r][c]
        for dr, dc, move_mult in dirs:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < ht and 0 <= nc < wt):
                continue
            # Custo combina distância física, suporte de plataforma e desvio de espinhos
            tile_c = step_cost[nr][nc] * move_mult + hazard_map[nr][nc] * 0.35
            ng = cur_g + tile_c
            if ng < dist[nr][nc]:
                dist[nr][nc] = ng
                parent[(nr, nc)] = (r, c)
                heur = math.hypot(gr - nr, gc - nc) * 0.85
                heapq.heappush(pq, (ng + heur, nr, nc))

    # Reconstruir caminho tile a tile
    path: list[tuple[int, int]] = []
    curr: tuple[int, int] | None = (gr, gc)
    if curr not in parent and curr != (sr, sc):
        return [(sr, sc), (gr, gc)], math.hypot(gr - sr, gc - sc), 4.0, True

    while curr is not None:
        path.append(curr)
        curr = parent.get(curr)
    path.reverse()

    walk_dist = 0.0
    hazard_sum = 0.0
    pierced_solid = False
    for i, (r, c) in enumerate(path):
        if not grid[r][c] and i not in (0, len(path) - 1):
            pierced_solid = True
        hazard_sum += hazard_map[r][c]
        if i > 0:
            pr, pc = path[i - 1]
            walk_dist += math.hypot(r - pr, c - pc) * step_cost[r][c]

    return path, max(1.0, walk_dist), hazard_sum, pierced_solid


def _simplify_tile_path_to_world_waypoints(
    tile_path: list[tuple[int, int]],
    room_x: int,
    room_y: int,
    max_points: int = 14,
) -> list[list[float]]:
    """Converte a sequência de tiles `(r, c)` em waypoints `(wx, wy)` em coordenadas do mundo."""
    if not tile_path:
        return [[float(room_x), float(room_y)]]
    world_pts = [
        [round(room_x + c * 8.0 + 4.0, 1), round(room_y + r * 8.0 + 4.0, 1)]
        for r, c in tile_path
    ]
    if len(world_pts) <= max_points:
        return world_pts
    out: list[list[float]] = [world_pts[0]]
    step = (len(world_pts) - 1) / float(max_points - 1)
    for k in range(1, max_points - 1):
        out.append(world_pts[int(round(k * step))])
    out.append(world_pts[-1])
    return out


def _can_reach_all(
    directed_adj: dict[str, set[str]],
    start_id: str,
    goal_id: str,
    required_nodes: set[str],
) -> bool:
    """Verifica se `start_id` alcança todos os nós requeridos e `goal_id` é alcançável a partir deles."""
    vis_from_start = {start_id}
    dq = deque([start_id])
    while dq:
        u = dq.popleft()
        for v in directed_adj.get(u, ()):
            if v not in vis_from_start:
                vis_from_start.add(v)
                dq.append(v)
    if goal_id not in vis_from_start or not required_nodes.issubset(vis_from_start):
        return False

    rev_adj: dict[str, set[str]] = defaultdict(set)
    for u, nbrs in directed_adj.items():
        for v in nbrs:
            rev_adj[v].add(u)
    can_reach_goal = {goal_id}
    dq = deque([goal_id])
    while dq:
        u = dq.popleft()
        for prev in rev_adj.get(u, ()):
            if prev not in can_reach_goal:
                can_reach_goal.add(prev)
                dq.append(prev)
    return required_nodes.issubset(can_reach_goal)


def extract_chapter_to_csv(bin_path: Path, out_dir: Path) -> dict[str, object]:
    """Extrai um capítulo `.bin` do Celeste simulando o trajeto real do player em cada sala."""
    pkg, root = parse_celeste_bin(bin_path)
    levels = [c for c in root[2] if c[0] == "levels"][0][2]

    rooms: dict[str, dict[str, object]] = {}
    grids: dict[str, list[list[bool]]] = {}
    nav_maps: dict[str, dict[str, object]] = {}

    for lvl in levels:
        at = lvl[1]
        name = str(at["name"])
        x, y = int(at["x"]), int(at["y"])
        w, h = int(at["width"]), int(at["height"])
        wt, ht = max(1, w // 8), max(1, h // 8)

        ent_counts: Counter[str] = Counter()
        raw_entities: list[tuple[str, dict]] = []
        for ch in lvl[2]:
            if ch[0] == "entities":
                for e in ch[2]:
                    ent_counts[e[0]] += 1
                    raw_entities.append((e[0], e[1]))

        grid = _get_solids_grid(lvl, wt, ht)
        step_cost, hazard_map, coll_tiles, spawn_tiles = _build_room_navigation_maps(
            grid, raw_entities, wt, ht
        )

        # Ponto âncora interno da sala (spawn principal do player ou centro livre mais próximo)
        anchor_rc = spawn_tiles[0] if spawn_tiles else (ht // 2, wt // 2)
        if not grid[anchor_rc[0]][anchor_rc[1]]:
            # Buscar tile livre mais próximo do centro
            best_rc = anchor_rc
            best_d = 999999
            for rr in range(ht):
                for cc in range(wt):
                    if grid[rr][cc]:
                        d = abs(rr - ht // 2) + abs(cc - wt // 2)
                        if d < best_d:
                            best_d = d
                            best_rc = (rr, cc)
            anchor_rc = best_rc

        rooms[name] = {
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "wt": wt,
            "ht": ht,
            "attrs": at,
            "entities": ent_counts,
            "raw_entities": raw_entities,
        }
        grids[name] = grid
        nav_maps[name] = {
            "step_cost": step_cost,
            "hazard_map": hazard_map,
            "coll_tiles": coll_tiles,
            "spawn_tiles": spawn_tiles,
            "anchor_rc": anchor_rc,
        }

    # 1. Construir adjacência geométrica + encontrar as coordenadas exatas das portas (door_tiles)
    open_adj: dict[str, set[str]] = defaultdict(set)
    edge_meta: dict[tuple[str, str], str] = {}
    door_tile_in_room: dict[tuple[str, str], tuple[int, int]] = {}
    room_names = list(rooms.keys())

    for i, n1 in enumerate(room_names):
        r1 = rooms[n1]
        x1, y1, w1, h1, wt1, ht1 = (
            int(r1["x"]),
            int(r1["y"]),
            int(r1["w"]),
            int(r1["h"]),
            int(r1["wt"]),
            int(r1["ht"]),
        )
        for j in range(i + 1, len(room_names)):
            n2 = room_names[j]
            r2 = rooms[n2]
            x2, y2, w2, h2, wt2, ht2 = (
                int(r2["x"]),
                int(r2["y"]),
                int(r2["w"]),
                int(r2["h"]),
                int(r2["wt"]),
                int(r2["ht"]),
            )
            # Contato horizontal
            if (x1 + w1 == x2 or x2 + w2 == x1) and (max(y1, y2) < min(y1 + h1, y2 + h2)):
                ya, yb = max(y1, y2), min(y1 + h1, y2 + h2)
                open_doors: list[tuple[tuple[int, int], tuple[int, int]]] = []
                for py in range(ya, yb, 8):
                    row1, row2 = (py - y1) // 8, (py - y2) // 8
                    col1 = (wt1 - 1) if (x1 + w1 == x2) else 0
                    col2 = 0 if (x1 + w1 == x2) else (wt2 - 1)
                    if grids[n1][row1][col1] and grids[n2][row2][col2]:
                        open_doors.append(((row1, col1), (row2, col2)))
                if open_doors:
                    mid_door = open_doors[len(open_doors) // 2]
                    open_adj[n1].add(n2)
                    open_adj[n2].add(n1)
                    edge_meta[(n1, n2)] = "H"
                    edge_meta[(n2, n1)] = "H"
                    door_tile_in_room[(n1, n2)] = mid_door[0]
                    door_tile_in_room[(n2, n1)] = mid_door[1]

            # Contato vertical
            if (y1 + h1 == y2 or y2 + h2 == y1) and (max(x1, x2) < min(x1 + w1, x2 + w2)):
                xa, xb = max(x1, x2), min(x1 + w1, x2 + w2)
                open_doors = []
                for px in range(xa, xb, 8):
                    col1, col2 = (px - x1) // 8, (px - x2) // 8
                    row1 = (ht1 - 1) if (y1 + h1 == y2) else 0
                    row2 = 0 if (y1 + h1 == y2) else (ht2 - 1)
                    if grids[n1][row1][col1] and grids[n2][row2][col2]:
                        open_doors.append(((row1, col1), (row2, col2)))
                if open_doors:
                    mid_door = open_doors[len(open_doors) // 2]
                    open_adj[n1].add(n2)
                    open_adj[n2].add(n1)
                    door_tile_in_room[(n1, n2)] = mid_door[0]
                    door_tile_in_room[(n2, n1)] = mid_door[1]
                    if y1 + h1 == y2:
                        edge_meta[(n1, n2)] = "V_DOWN"
                        edge_meta[(n2, n1)] = "V_UP"
                    else:
                        edge_meta[(n2, n1)] = "V_DOWN"
                        edge_meta[(n1, n2)] = "V_UP"

    # 2. Extrair Maior Componente Conexa (LCC)
    seen: set[str] = set()
    comps: list[list[str]] = []
    for n in room_names:
        if n in seen:
            continue
        q = [n]
        seen.add(n)
        comp = []
        while q:
            u = q.pop()
            comp.append(u)
            for v in open_adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    lcc = set(comps[0])

    # 3. Identificar INICIO e FIM na LCC preservando salas de coletáveis
    def room_collectible_val(room_id: str) -> float:
        ec: Counter[str] = rooms[room_id]["entities"]  # type: ignore[assignment]
        return (
            ec["strawberry"] * 5.0
            + ec["cassette"] * 12.0
            + ec["blackGem"] * 15.0
            + ec["reflectionHeartStatue"] * 15.0
        )

    non_collectible_candidates = [n for n in lcc if room_collectible_val(n) == 0.0]
    pool = non_collectible_candidates if non_collectible_candidates else list(lcc)
    start_id = min(pool, key=lambda n: (int(rooms[n]["x"]), -int(rooms[n]["y"])))

    bfs_dist0: dict[str, int] = {start_id: 0}
    dq0 = deque([start_id])
    while dq0:
        u = dq0.popleft()
        for v in sorted(open_adj[u]):
            if v in lcc and v not in bfs_dist0:
                bfs_dist0[v] = bfs_dist0[u] + 1
                dq0.append(v)

    goal_pool = [n for n in pool if n != start_id and n in bfs_dist0]
    if not goal_pool:
        goal_pool = [n for n in lcc if n != start_id]
    goal_id = max(goal_pool, key=lambda n: (bfs_dist0[n], int(rooms[n]["x"]), -int(rooms[n]["y"])))

    def is_connected_without(excluded_room: str) -> bool:
        rem = lcc - {excluded_room}
        if start_id not in rem or goal_id not in rem:
            return False
        vis = {start_id}
        q_chk = deque([start_id])
        while q_chk:
            cur = q_chk.popleft()
            for nb in open_adj[cur]:
                if nb in rem and nb not in vis:
                    vis.add(nb)
                    q_chk.append(nb)
        return len(vis) == len(rem)

    # Espinha inicial para pontuar candidatos a ARMA
    init_dist: dict[str, int] = {start_id: 0}
    init_parent: dict[str, str | None] = {start_id: None}
    dq_init = deque([start_id])
    while dq_init:
        u = dq_init.popleft()
        for v in sorted(open_adj[u]):
            if v in lcc and v not in init_dist:
                init_dist[v] = init_dist[u] + 1
                init_parent[v] = u
                dq_init.append(v)
    init_spine: set[str] = set()
    c_node: str | None = goal_id
    while c_node is not None:
        init_spine.add(c_node)
        c_node = init_parent.get(c_node)

    # 4. Selecionar sala de ARMA (power-up sem roubar coletáveis e sem desconectar a LCC)
    weapon_candidates = [
        n
        for n in non_collectible_candidates
        if n not in {start_id, goal_id} and is_connected_without(n)
    ]
    if not weapon_candidates:
        weapon_candidates = [
            n for n in lcc if n not in {start_id, goal_id} and is_connected_without(n)
        ]

    def weapon_score(room_id: str) -> tuple[int, int, int, int, int, float]:
        ec: Counter[str] = rooms[room_id]["entities"]  # type: ignore[assignment]
        has_special = (
            ec["key"] * 5
            + ec["infiniteStar"] * 3
            + ec["refill"] * 2
            + ec["booster"] * 2
            + ec["zipMover"]
        )
        off_init_spine = 1 if room_id not in init_spine else 0
        near_spine = 1 if any(nb in init_spine - {goal_id} for nb in open_adj[room_id]) else 0
        dist_from_start = init_dist.get(room_id, 999)
        in_first_half = 1 if 1 <= dist_from_start <= max(2, init_dist[goal_id] // 2) else 0
        return (
            off_init_spine,
            near_spine,
            in_first_half,
            has_special,
            -dist_from_start,
            float(rooms[room_id]["w"]),
        )

    weapon_room = max(weapon_candidates, key=weapon_score)

    # Reconstruir a espinha principal em lcc - {weapon_room}
    bfs_dist: dict[str, int] = {start_id: 0}
    bfs_parent: dict[str, str | None] = {start_id: None}
    dq = deque([start_id])
    while dq:
        u = dq.popleft()
        for v in sorted(open_adj[u]):
            if v in lcc and v != weapon_room and v not in bfs_dist:
                bfs_dist[v] = bfs_dist[u] + 1
                bfs_parent[v] = u
                dq.append(v)

    bfs_spine_list: list[str] = []
    curr: str | None = goal_id
    while curr is not None:
        bfs_spine_list.append(curr)
        curr = bfs_parent.get(curr)
    bfs_spine_list.reverse()
    bfs_spine: set[str] = set(bfs_spine_list)
    bfs_dist[weapon_room] = bfs_dist0.get(weapon_room, 1)

    # 5. Calcular vértices e simular o pathfinding tile-a-tile do player em cada transição (u -> v)
    vertex_rows: list[dict[str, object]] = []
    for room_id in sorted(lcc):
        collectible_val = room_collectible_val(room_id)
        has_w = 1 if room_id == weapon_room else 0
        if room_id == start_id:
            r_type = "INICIO"
            collectible_val = 0.0
            has_w = 0
        elif room_id == goal_id:
            r_type = "FIM"
            collectible_val = 0.0
        elif has_w == 1:
            r_type = "ARMA"
            collectible_val = 0.0
        elif collectible_val > 0.0:
            r_type = "COLETAVEL"
        else:
            r_type = "COMUM"

        vertex_rows.append(
            {
                "id_sala": room_id,
                "tipo_sala": r_type,
                "valor_coletavel": round(collectible_val, 1),
                "possui_arma": has_w,
            }
        )

    def simulate_player_transition(u: str, v: str) -> tuple[float, float, float, list[list[float]]]:
        """Simula o player saindo da âncora de `u` -> porta `(u,v)` -> (itens de `v`) -> âncora de `v`."""
        ru, rv = rooms[u], rooms[v]
        nu, nv = nav_maps[u], nav_maps[v]
        door_u = door_tile_in_room.get((u, v), nu["anchor_rc"])  # type: ignore[arg-type]
        door_v = door_tile_in_room.get((v, u), nv["anchor_rc"])  # type: ignore[arg-type]

        # Parte 1: na sala de origem u, do ponto âncora até a porta de saída para v
        path_u, dist_u, haz_u, _p1 = _astar_tile_path(
            grids[u],
            nu["step_cost"],  # type: ignore[arg-type]
            nu["hazard_map"],  # type: ignore[arg-type]
            nu["anchor_rc"],  # type: ignore[arg-type]
            door_u,  # type: ignore[arg-type]
        )

        # Parte 2: na sala de destino v, da porta de entrada passando pelos coletáveis até a âncora de v
        coll_v: list[tuple[int, int]] = list(nv["coll_tiles"])  # type: ignore[arg-type]
        waypoints_v_rc: list[tuple[int, int]] = [door_v]  # type: ignore[list-item]
        for ct in coll_v[:2]:
            waypoints_v_rc.append(ct)
        waypoints_v_rc.append(nv["anchor_rc"])  # type: ignore[arg-type]

        full_tiles_v: list[tuple[int, int]] = []
        dist_v = 0.0
        haz_v = 0.0
        for k in range(len(waypoints_v_rc) - 1):
            seg_path, seg_dist, seg_haz, _p2 = _astar_tile_path(
                grids[v],
                nv["step_cost"],  # type: ignore[arg-type]
                nv["hazard_map"],  # type: ignore[arg-type]
                waypoints_v_rc[k],
                waypoints_v_rc[k + 1],
            )
            if full_tiles_v and seg_path:
                full_tiles_v.extend(seg_path[1:])
            else:
                full_tiles_v.extend(seg_path)
            dist_v += seg_dist
            haz_v += seg_haz

        # Converter distância real em tiles (8px) para tempo em segundos (velocidade média ~13 tiles/s = 104 px/s)
        total_tiles_walked = dist_u * 0.35 + dist_v
        base_time = round(max(1.8, total_tiles_walked / 11.5), 2)

        # Dificuldade real ao longo dos tiles percorridos pelo player
        at_v = rv["attrs"]  # type: ignore[assignment]
        env_haz = 0.0
        if str(at_v.get("windPattern", "None")) != "None":
            env_haz += 5.0
        if bool(at_v.get("dark", False)):
            env_haz += 4.5

        raw_path_hazard = (haz_u * 0.25 + haz_v * 0.85) + env_haz
        if v in bfs_spine and bfs_dist.get(v, 0) >= bfs_dist[goal_id] // 3:
            raw_path_hazard = max(raw_path_hazard * 1.65, 18.0)
        else:
            raw_path_hazard = max(raw_path_hazard, 2.0)

        diff_no_w = round(raw_path_hazard, 2)
        diff_with_w = round(max(0.5, diff_no_w * 0.20), 2)

        pts_u = _simplify_tile_path_to_world_waypoints(path_u, int(ru["x"]), int(ru["y"]), max_points=6)
        pts_v = _simplify_tile_path_to_world_waypoints(
            full_tiles_v, int(rv["x"]), int(rv["y"]), max_points=10
        )
        combined_waypoints = pts_u + pts_v
        return base_time, diff_no_w, diff_with_w, combined_waypoints

    # 6. Construir topologia estruturada:
    #    (a) Espinha principal s_0 -> s_1 -> ... -> s_k;
    #    (b) Desvio estratégico da ARMA s_w <-> weapon_room -> s_{w+1};
    #    (c) Floresta geradora BFS para todas as salas laterais (permitindo contração 100% dos becos).
    edge_rows: list[dict[str, object]] = []
    edge_waypoints: dict[str, list[list[float]]] = {}
    added_edges: set[tuple[str, str]] = set()

    def add_graph_edge(origin: str, dest: str, two_way: int) -> None:
        if (origin, dest) in added_edges or (dest, origin) in added_edges:
            return
        added_edges.add((origin, dest))
        base_t, diff_l0, diff_l1, wpts_fwd = simulate_player_transition(origin, dest)
        edge_waypoints[f"{origin}->{dest}"] = wpts_fwd
        if two_way == 1:
            _, _, _, wpts_rev = simulate_player_transition(dest, origin)
            edge_waypoints[f"{dest}->{origin}"] = wpts_rev
        edge_rows.append(
            {
                "origem": origin,
                "destino": dest,
                "mao_dupla": two_way,
                "tempo_base": base_t,
                "dificuldade_sem_arma": diff_l0,
                "dificuldade_com_arma": diff_l1,
            }
        )

    # 6a. Arestas consecutivas da espinha principal
    for idx in range(len(bfs_spine_list) - 1):
        u_sp = bfs_spine_list[idx]
        v_sp = bfs_spine_list[idx + 1]
        rel = edge_meta.get((u_sp, v_sp), "H")
        two_way = 0 if (rel == "V_DOWN" or v_sp == goal_id) else 1
        add_graph_edge(u_sp, v_sp, two_way)

    # 6b. Desvio estratégico de 2 saltos pela sala de ARMA: s_w <-> weapon_room -> s_{w+1}
    w_spine_idx = 0
    for idx in range(len(bfs_spine_list) - 1):
        if bfs_spine_list[idx] in open_adj[weapon_room]:
            w_spine_idx = idx
            break
    s_w = bfs_spine_list[w_spine_idx]
    s_w_next = bfs_spine_list[min(w_spine_idx + 1, len(bfs_spine_list) - 1)]
    add_graph_edge(s_w, weapon_room, 1)
    if s_w_next != s_w:
        add_graph_edge(weapon_room, s_w_next, 0)

    # 6c. Floresta geradora BFS das salas fora da espinha enraizada nos nós da espinha
    internal_spine = bfs_spine_list[1:-1] if len(bfs_spine_list) > 2 else list(bfs_spine_list)
    root_order = list(internal_spine) + [
        n for n in (start_id, goal_id) if n not in internal_spine
    ]
    forest_vis: set[str] = set(bfs_spine_list) | {weapon_room}
    forest_q: deque[str] = deque(root_order)
    while forest_q:
        u_f = forest_q.popleft()
        for v_f in sorted(open_adj[u_f]):
            if v_f in lcc and v_f not in forest_vis:
                forest_vis.add(v_f)
                add_graph_edge(u_f, v_f, 1)
                forest_q.append(v_f)

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "vertices.csv").open("w", encoding="utf-8", newline="") as vf:
        writer = csv.DictWriter(
            vf, fieldnames=["id_sala", "tipo_sala", "valor_coletavel", "possui_arma"]
        )
        writer.writeheader()
        writer.writerows(vertex_rows)

    with (out_dir / "arestas.csv").open("w", encoding="utf-8", newline="") as ef:
        writer = csv.DictWriter(
            ef,
            fieldnames=[
                "origem",
                "destino",
                "mao_dupla",
                "tempo_base",
                "dificuldade_sem_arma",
                "dificuldade_com_arma",
            ],
        )
        writer.writeheader()
        writer.writerows(edge_rows)

    # Salvar coordenadas de spawn/entidades e waypoints físicos de cada transição
    room_anchors: dict[str, dict[str, object]] = {}
    for room_id in sorted(lcc):
        r_info = rooms[room_id]
        ar, ac = nav_maps[room_id]["anchor_rc"]  # type: ignore[misc]
        coll_list = [
            [round(int(r_info["x"]) + cc * 8.0 + 4.0, 1), round(int(r_info["y"]) + rr * 8.0 + 4.0, 1)]
            for rr, cc in nav_maps[room_id]["coll_tiles"]  # type: ignore[union-attr]
        ]
        room_anchors[room_id] = {
            "x": int(r_info["x"]),
            "y": int(r_info["y"]),
            "w": int(r_info["w"]),
            "h": int(r_info["h"]),
            "anchor": [
                round(int(r_info["x"]) + ac * 8.0 + 4.0, 1),
                round(int(r_info["y"]) + ar * 8.0 + 4.0, 1),
            ],
            "collectibles_xy": coll_list,
        }

    (out_dir / "waypoints.json").write_text(
        json.dumps({"rooms": room_anchors, "edges": edge_waypoints}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "package": pkg,
        "slug": out_dir.name,
        "raw_rooms": len(rooms),
        "lcc_rooms": len(lcc),
        "edges": len(edge_rows),
        "one_way_edges": sum(1 for e in edge_rows if e["mao_dupla"] == 0),
        "collectible_rooms": sum(1 for v in vertex_rows if float(v["valor_coletavel"]) > 0),
        "weapon_room": weapon_room,
        "start_id": start_id,
        "goal_id": goal_id,
    }


def extract_all_celeste_chapters(
    steam_maps_dir: Path = DEFAULT_STEAM_MAPS_DIR,
    output_base_dir: Path = OUTPUT_BASE_DIR,
) -> list[dict[str, object]]:
    """Extrai todos os capítulos principais do Celeste para `datasets/celeste/`."""
    summaries: list[dict[str, object]] = []
    for slug, filename in CHAPTER_FILES:
        bin_path = steam_maps_dir / filename
        if not bin_path.is_file():
            raise FileNotFoundError(f"Mapa do Celeste não encontrado: {bin_path}")
        out_dir = output_base_dir / slug
        info = extract_chapter_to_csv(bin_path, out_dir)
        summaries.append(info)
    return summaries


if __name__ == "__main__":
    results = extract_all_celeste_chapters()
    for r in results:
        print(
            f"{r['slug']:20s} | salas: {r['raw_rooms']:3d} -> LCC: {r['lcc_rooms']:2d} | "
            f"arestas: {r['edges']:3d} (mão única: {r['one_way_edges']:2d}) | "
            f"salas c/ itens: {r['collectible_rooms']:2d} | arma: {r['weapon_room']}"
        )
