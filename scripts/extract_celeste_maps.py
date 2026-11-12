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
    "lightning": 3.0,
    "fireBarrier": 3.0,
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

LETHAL_HAZARDS = {
    "spikesUp",
    "spikesDown",
    "spikesLeft",
    "spikesRight",
    "triggerSpikesUp",
    "triggerSpikesDown",
    "triggerSpikesLeft",
    "triggerSpikesRight",
    "spinner",
    "rotateSpinner",
    "trackSpinner",
    "lightning",
    "fireBarrier",
    "seeker",
}

REFILL_ENTITIES = {
    "refill",
    "spring",
    "wallSpringLeft",
    "wallSpringRight",
    "booster",
}

DEFAULT_CELESTE_PHYSICS: dict[str, float] = {
    "tile_px": 8.0,
    "max_run_px_s": 90.0,
    "jump_speed_px_s": 105.0,
    "gravity_px_s2": 900.0,
    "max_fall_px_s": 160.0,
    "dash_speed_px_s": 240.0,
    "dash_time_s": 0.15,
    "max_dashes": 1.0,
    "climb_max_stamina": 110.0,
    "max_jump_tiles": 6.0,
    "single_dash_tiles": 6.0,
    "climb_reach_tiles": 8.0,
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
) -> dict[str, object]:
    """Constrói mapas físicos calibrados da sala (colisão, apoios, recargas e perigos letais)."""
    jumpthru = [[False] * wt for _ in range(ht)]
    assist = [[False] * wt for _ in range(ht)]
    refill_map = [[False] * wt for _ in range(ht)]
    lethal_map = [[False] * wt for _ in range(ht)]
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
            # Player sprite tem origem nos pés; normaliza no tile livre
            sr = r0 if grid[r0][c0] else max(0, r0 - 1)
            spawn_tiles.append((sr, c0))
        elif ename in COLLECTIBLE_ENTITIES:
            cr = r0
            if not grid[cr][c0]:
                for dr in (-1, 1, -2, 2):
                    if 0 <= cr + dr < ht and grid[cr + dr][c0]:
                        cr = cr + dr
                        break
            collectible_tiles.append((cr, c0))
        elif ename == "jumpThru":
            for cc in range(c0, c1 + 1):
                jumpthru[r0][cc] = True
        elif ename in ASSIST_ENTITIES:
            is_refill = ename in REFILL_ENTITIES
            for rr in range(max(0, r0 - 2), min(ht, r1 + 3)):
                for cc in range(max(0, c0 - 2), min(wt, c1 + 3)):
                    assist[rr][cc] = True
                    if is_refill and abs(rr - r0) <= 1 and abs(cc - c0) <= 1:
                        refill_map[rr][cc] = True

        if ename in LETHAL_HAZARDS:
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    lethal_map[rr][cc] = True

        if ename in HAZARD_WEIGHTS:
            hw = HAZARD_WEIGHTS[ename]
            for rr in range(max(0, r0 - 1), min(ht, r1 + 2)):
                for cc in range(max(0, c0 - 1), min(wt, c1 + 2)):
                    dist = abs(rr - r0) + abs(cc - c0)
                    hazard_map[rr][cc] += hw * (1.0 if dist == 0 else 0.45)

    ground_map = [[False] * wt for _ in range(ht)]
    wall_map = [[False] * wt for _ in range(ht)]
    step_cost = [[1.0] * wt for _ in range(ht)]
    for r in range(ht):
        for c in range(wt):
            if not grid[r][c]:
                step_cost[r][c] = 999.0
                continue

            on_ground = (
                r == ht - 1
                or (r + 1 < ht and (not grid[r + 1][c] or jumpthru[r + 1][c]))
            )
            ground_map[r][c] = on_ground

            near_wall = (c > 0 and not grid[r][c - 1]) or (c + 1 < wt and not grid[r][c + 1])
            wall_map[r][c] = near_wall

            near_floor = False
            for dr in range(1, 5):
                rr = r + dr
                if rr >= ht or not grid[rr][c] or jumpthru[rr][c]:
                    near_floor = True
                    break

            if assist[r][c]:
                step_cost[r][c] = 0.75
            elif on_ground or near_floor or jumpthru[r][c]:
                step_cost[r][c] = 1.0
            elif near_wall:
                step_cost[r][c] = 1.3  # escalada / walljump
            else:
                step_cost[r][c] = 1.65  # arco aéreo / dash

    return {
        "step_cost": step_cost,
        "hazard_map": hazard_map,
        "lethal_map": lethal_map,
        "refill_map": refill_map,
        "ground_map": ground_map,
        "wall_map": wall_map,
        "coll_tiles": collectible_tiles,
        "spawn_tiles": spawn_tiles,
    }


def _astar_tile_path(
    grid: list[list[bool]],
    step_cost: list[list[float]],
    hazard_map: list[list[float]],
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    *,
    lethal_map: list[list[bool]] | None = None,
    ground_map: list[list[bool]] | None = None,
    wall_map: list[list[bool]] | None = None,
    refill_map: list[list[bool]] | None = None,
    physics: dict[str, float] | None = None,
) -> tuple[list[tuple[int, int]], float, float, bool]:
    """Executa A* no espaço de estados físico `(r, c, air_budget, dash_avail)` estilo TAS.

    Respeita:
    1. Blocos sólidos (`<solids>`) são intransponíveis (nunca atravessa parede nem quinas).
    2. Espinhos e spinners (`lethal_map`) são evitados estritamente (passo 1 não-letal;
       passo 2 apenas se não existir caminho seguro algum).
    3. Gravidade, arco de pulo (`max_jump_tiles`) e regra estrita de 1 dash (`dash_avail`),
       que só recarrega ao pisar em chão firme, plataforma ou cristal/mola/booster.
    """
    ht = len(grid)
    wt = len(grid[0]) if ht else 0
    sr = max(0, min(ht - 1, start_rc[0]))
    sc = max(0, min(wt - 1, start_rc[1]))
    gr = max(0, min(ht - 1, goal_rc[0]))
    gc = max(0, min(wt - 1, goal_rc[1]))

    if (sr, sc) == (gr, gc):
        return [(sr, sc)], 1.0, hazard_map[sr][sc], False

    phys = physics or DEFAULT_CELESTE_PHYSICS
    max_air = int(round(phys.get("max_jump_tiles", 6.0)))
    dash_boost = int(round(phys.get("single_dash_tiles", 6.0)))

    def is_lethal(rr: int, cc: int) -> bool:
        return bool(lethal_map is not None and lethal_map[rr][cc])

    def is_grounded(rr: int, cc: int) -> bool:
        return bool(ground_map is not None and ground_map[rr][cc])

    def is_wall(rr: int, cc: int) -> bool:
        return bool(wall_map is not None and wall_map[rr][cc])

    def is_refill(rr: int, cc: int) -> bool:
        return bool(refill_map is not None and refill_map[rr][cc])

    dirs = [
        (0, 1, 1.0),
        (0, -1, 1.0),
        (1, 0, 0.9),
        (-1, 0, 1.35),
        (1, 1, 1.3),
        (1, -1, 1.3),
        (-1, 1, 1.55),
        (-1, -1, 1.55),
    ]

    def run_search(allow_lethal: bool) -> list[tuple[int, int]] | None:
        init_air = max_air
        init_state = (sr, sc, init_air, 1)
        dist: dict[tuple[int, int, int, int], float] = {init_state: 0.0}
        parent: dict[tuple[int, int, int, int], tuple[int, int, int, int]] = {}
        pq: list[tuple[float, float, int, int, int, int]] = [
            (math.hypot(gr - sr, gc - sc), 0.0, sr, sc, init_air, 1)
        ]
        goal_state: tuple[int, int, int, int] | None = None
        expansions = 0
        max_expansions = max(12000, wt * ht * 10)

        while pq and expansions < max_expansions:
            _f, cur_g, r, c, air, dash = heapq.heappop(pq)
            st = (r, c, air, dash)
            if cur_g > dist.get(st, float("inf")) + 1e-9:
                continue
            if (r, c) == (gr, gc):
                goal_state = st
                break
            expansions += 1

            for dr, dc, move_mult in dirs:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < ht and 0 <= nc < wt):
                    continue
                if not grid[nr][nc] and (nr, nc) != (gr, gc):
                    continue
                if dr != 0 and dc != 0 and (not grid[r + dr][c] or not grid[r][c + dc]):
                    continue
                lethal_hit = is_lethal(nr, nc) and (nr, nc) != (gr, gc)
                if lethal_hit and not allow_lethal:
                    continue

                grounded_next = is_grounded(nr, nc)
                wall_next = is_wall(nr, nc)
                refill_next = is_refill(nr, nc)

                next_air = air
                next_dash = dash
                dash_used_penalty = 0.0

                if grounded_next or refill_next:
                    next_air = max_air
                    next_dash = 1
                elif wall_next:
                    next_air = max(air - (1 if dr < 0 else 0), 3)
                else:
                    # Movimento aéreo sem chão/parede consome altura de pulo ou o único dash
                    air_cost = 1 if dr <= 0 else 0
                    if next_air >= air_cost:
                        next_air -= air_cost
                    elif next_dash == 1:
                        next_dash = 0
                        next_air = max(0, dash_boost - 1)
                        dash_used_penalty = 0.8
                    elif dr < 0:
                        # Sem pulo nem dash disponíveis: gravidade impede subir no ar
                        continue
                    else:
                        next_air = 0

                lethal_pen = 5000.0 if lethal_hit else 0.0
                tile_c = (
                    step_cost[nr][nc] * move_mult
                    + hazard_map[nr][nc] * 0.45
                    + dash_used_penalty
                    + lethal_pen
                )
                ng = cur_g + tile_c
                nxt_st = (nr, nc, next_air, next_dash)
                if ng < dist.get(nxt_st, float("inf")) - 1e-9:
                    dist[nxt_st] = ng
                    parent[nxt_st] = st
                    heur = math.hypot(gr - nr, gc - nc) * 0.85
                    heapq.heappush(pq, (ng + heur, ng, nr, nc, next_air, next_dash))

        if goal_state is None:
            return None
        raw_path: list[tuple[int, int]] = []
        cur: tuple[int, int, int, int] | None = goal_state
        while cur is not None:
            raw_path.append((cur[0], cur[1]))
            cur = parent.get(cur)
        raw_path.reverse()
        return raw_path

    # Tentativa 1: 100% não-letal respeitando gravidade e regra de 1 dash
    path = run_search(allow_lethal=False)
    # Tentativa 2 (fallback caso coletável/porta encoste em hitbox): penalidade letal máxima
    if path is None:
        path = run_search(allow_lethal=True)
    if path is None:
        return [(sr, sc), (gr, gc)], math.hypot(gr - sr, gc - sc), 10.0, True

    walk_dist = 0.0
    hazard_sum = 0.0
    lethal_hit = False
    for i, (r, c) in enumerate(path):
        if not grid[r][c] and i not in (0, len(path) - 1):
            lethal_hit = True
        if is_lethal(r, c) and i not in (0, len(path) - 1):
            lethal_hit = True
        hazard_sum += hazard_map[r][c]
        if i > 0:
            pr, pc = path[i - 1]
            walk_dist += math.hypot(r - pr, c - pc) * step_cost[r][c]

    return path, max(1.0, walk_dist), hazard_sum, lethal_hit


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


def extract_chapter_to_csv(
    bin_path: Path,
    out_dir: Path,
    physics: dict[str, float] | None = None,
) -> dict[str, object]:
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
        nav_info = _build_room_navigation_maps(grid, raw_entities, wt, ht)
        spawn_tiles: list[tuple[int, int]] = nav_info["spawn_tiles"]  # type: ignore[assignment]
        ground_map: list[list[bool]] = nav_info["ground_map"]  # type: ignore[assignment]
        lethal_map: list[list[bool]] = nav_info["lethal_map"]  # type: ignore[assignment]

        # Ponto âncora interno da sala: pousar spawn sobre o chão firme mais próximo (não no meio do ar!)
        anchor_rc = spawn_tiles[0] if spawn_tiles else (ht // 2, wt // 2)
        if grid[anchor_rc[0]][anchor_rc[1]]:
            ar, ac = anchor_rc
            while ar + 1 < ht and grid[ar + 1][ac] and not ground_map[ar][ac]:
                ar += 1
            if ground_map[ar][ac] and not lethal_map[ar][ac]:
                anchor_rc = (ar, ac)

        if not grid[anchor_rc[0]][anchor_rc[1]] or lethal_map[anchor_rc[0]][anchor_rc[1]]:
            best_rc = anchor_rc
            best_d = 999999
            for rr in range(ht):
                for cc in range(wt):
                    if grid[rr][cc] and not lethal_map[rr][cc]:
                        bonus = 0 if ground_map[rr][cc] else 20
                        d = abs(rr - ht // 2) + abs(cc - wt // 2) + bonus
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
        nav_info["anchor_rc"] = anchor_rc
        nav_maps[name] = nav_info

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

    phys_cfg = physics or DEFAULT_CELESTE_PHYSICS
    segment_audit = {"total": 0, "safe": 0, "lethal_fallback": 0}

    def simulate_player_transition(u: str, v: str) -> tuple[float, float, float, list[list[float]]]:
        """Simula o player saindo da âncora de `u` -> porta `(u,v)` -> (itens de `v`) -> âncora de `v`."""
        ru, rv = rooms[u], rooms[v]
        nu, nv = nav_maps[u], nav_maps[v]
        door_u = door_tile_in_room.get((u, v), nu["anchor_rc"])  # type: ignore[arg-type]
        door_v = door_tile_in_room.get((v, u), nv["anchor_rc"])  # type: ignore[arg-type]

        # Parte 1: na sala de origem u, do ponto âncora até a porta de saída para v (A* físico com estado)
        path_u, dist_u, haz_u, p1_lethal = _astar_tile_path(
            grids[u],
            nu["step_cost"],  # type: ignore[arg-type]
            nu["hazard_map"],  # type: ignore[arg-type]
            nu["anchor_rc"],  # type: ignore[arg-type]
            door_u,  # type: ignore[arg-type]
            lethal_map=nu["lethal_map"],  # type: ignore[arg-type]
            ground_map=nu["ground_map"],  # type: ignore[arg-type]
            wall_map=nu["wall_map"],  # type: ignore[arg-type]
            refill_map=nu["refill_map"],  # type: ignore[arg-type]
            physics=phys_cfg,
        )
        segment_audit["total"] += 1
        if p1_lethal:
            segment_audit["lethal_fallback"] += 1
        else:
            segment_audit["safe"] += 1

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
            seg_path, seg_dist, seg_haz, p2_lethal = _astar_tile_path(
                grids[v],
                nv["step_cost"],  # type: ignore[arg-type]
                nv["hazard_map"],  # type: ignore[arg-type]
                waypoints_v_rc[k],
                waypoints_v_rc[k + 1],
                lethal_map=nv["lethal_map"],  # type: ignore[arg-type]
                ground_map=nv["ground_map"],  # type: ignore[arg-type]
                wall_map=nv["wall_map"],  # type: ignore[arg-type]
                refill_map=nv["refill_map"],  # type: ignore[arg-type]
                physics=phys_cfg,
            )
            segment_audit["total"] += 1
            if p2_lethal:
                segment_audit["lethal_fallback"] += 1
            else:
                segment_audit["safe"] += 1
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
        json.dumps(
            {
                "calibrated": True,
                "physics": phys_cfg,
                "segment_audit": segment_audit,
                "rooms": room_anchors,
                "edges": edge_waypoints,
            },
            ensure_ascii=False,
            indent=2,
        ),
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
        "segment_audit": segment_audit,
    }


def extract_all_celeste_chapters(
    steam_maps_dir: Path = DEFAULT_STEAM_MAPS_DIR,
    output_base_dir: Path = OUTPUT_BASE_DIR,
    physics: dict[str, float] | None = None,
) -> list[dict[str, object]]:
    """Extrai todos os capítulos principais do Celeste para `datasets/celeste/`."""
    summaries: list[dict[str, object]] = []
    for slug, filename in CHAPTER_FILES:
        bin_path = steam_maps_dir / filename
        if not bin_path.is_file():
            raise FileNotFoundError(f"Mapa do Celeste não encontrado: {bin_path}")
        out_dir = output_base_dir / slug
        info = extract_chapter_to_csv(bin_path, out_dir, physics=physics)
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
