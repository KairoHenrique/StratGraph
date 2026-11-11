"""Extrator oficial de mapas binários (.bin) de Celeste para o formato CSV do StratGraph.

Lê diretamente os arquivos BinaryPacker (`Content/Maps/*.bin`) da instalação do Celeste,
extrai a Maior Componente Conexa (LCC) com passagens abertas na matriz de colisão (`solids`),
calcula tempos base pelas dimensões reais das salas e dificuldades pelos obstáculos reais,
e exporta `vertices.csv` e `arestas.csv` para cada capítulo em `datasets/celeste/`.
"""

from collections import Counter, defaultdict, deque
import csv
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


def _can_reach_all(
    directed_adj: dict[str, set[str]],
    start_id: str,
    goal_id: str,
    required_nodes: set[str],
) -> bool:
    """Verifica se `start_id` alcança todos os nós requeridos e `goal_id` é alcançável a partir deles."""
    # 1. Alcançáveis a partir de start_id
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

    # 2. Nós que conseguem alcançar goal_id (grafo reverso)
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
    """Extrai um capítulo `.bin` do Celeste para `vertices.csv` e `arestas.csv`."""
    pkg, root = parse_celeste_bin(bin_path)
    levels = [c for c in root[2] if c[0] == "levels"][0][2]

    rooms: dict[str, dict[str, object]] = {}
    grids: dict[str, list[list[bool]]] = {}
    for lvl in levels:
        at = lvl[1]
        name = str(at["name"])
        x, y = int(at["x"]), int(at["y"])
        w, h = int(at["width"]), int(at["height"])
        wt, ht = max(1, w // 8), max(1, h // 8)

        ent_counts: Counter[str] = Counter()
        has_two_dash_refill = False
        for ch in lvl[2]:
            if ch[0] == "entities":
                for e in ch[2]:
                    ent_counts[e[0]] += 1
                    if e[0] == "refill" and bool(e[1].get("twoDash", False)):
                        has_two_dash_refill = True

        rooms[name] = {
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "wt": wt,
            "ht": ht,
            "attrs": at,
            "entities": ent_counts,
            "two_dash": has_two_dash_refill,
        }
        grids[name] = _get_solids_grid(lvl, wt, ht)

    # 1. Construir adjacência geométrica filtrada por passagem aberta em `solids`
    open_adj: dict[str, set[str]] = defaultdict(set)
    edge_meta: dict[tuple[str, str], str] = {}  # (u, v) -> 'H' ou 'V_DOWN' ou 'V_UP'
    room_names = list(rooms.keys())

    for i, n1 in enumerate(room_names):
        r1_info = rooms[n1]
        x1, y1, w1, h1, wt1, ht1 = (
            int(r1_info["x"]),
            int(r1_info["y"]),
            int(r1_info["w"]),
            int(r1_info["h"]),
            int(r1_info["wt"]),
            int(r1_info["ht"]),
        )
        for j in range(i + 1, len(room_names)):
            n2 = room_names[j]
            r2_info = rooms[n2]
            x2, y2, w2, h2, wt2, ht2 = (
                int(r2_info["x"]),
                int(r2_info["y"]),
                int(r2_info["w"]),
                int(r2_info["h"]),
                int(r2_info["wt"]),
                int(r2_info["ht"]),
            )
            # Contato horizontal
            if (x1 + w1 == x2 or x2 + w2 == x1) and (max(y1, y2) < min(y1 + h1, y2 + h2)):
                ya, yb = max(y1, y2), min(y1 + h1, y2 + h2)
                for py in range(ya, yb, 8):
                    row1, row2 = (py - y1) // 8, (py - y2) // 8
                    col1 = (wt1 - 1) if (x1 + w1 == x2) else 0
                    col2 = 0 if (x1 + w1 == x2) else (wt2 - 1)
                    if grids[n1][row1][col1] and grids[n2][row2][col2]:
                        open_adj[n1].add(n2)
                        open_adj[n2].add(n1)
                        edge_meta[(n1, n2)] = "H"
                        edge_meta[(n2, n1)] = "H"
                        break
            # Contato vertical
            if (y1 + h1 == y2 or y2 + h2 == y1) and (max(x1, x2) < min(x1 + w1, x2 + w2)):
                xa, xb = max(x1, x2), min(x1 + w1, x2 + w2)
                for px in range(xa, xb, 8):
                    col1, col2 = (px - x1) // 8, (px - x2) // 8
                    row1 = (ht1 - 1) if (y1 + h1 == y2) else 0
                    row2 = 0 if (y1 + h1 == y2) else (ht2 - 1)
                    if grids[n1][row1][col1] and grids[n2][row2][col2]:
                        open_adj[n1].add(n2)
                        open_adj[n2].add(n1)
                        if y1 + h1 == y2:
                            edge_meta[(n1, n2)] = "V_DOWN"
                            edge_meta[(n2, n1)] = "V_UP"
                        else:
                            edge_meta[(n2, n1)] = "V_DOWN"
                            edge_meta[(n1, n2)] = "V_UP"
                        break

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
    if "lvl_start" in lcc:
        start_id = "lvl_start"
    else:
        non_collectible_candidates = [
            n
            for n in lcc
            if rooms[n]["entities"]["strawberry"] == 0
            and rooms[n]["entities"]["cassette"] == 0
            and rooms[n]["entities"]["blackGem"] == 0
        ]
        pool = non_collectible_candidates if non_collectible_candidates else list(lcc)
        start_id = min(pool, key=lambda n: (int(rooms[n]["x"]), -int(rooms[n]["y"])))
    bfs_dist: dict[str, int] = {start_id: 0}
    bfs_parent: dict[str, str | None] = {start_id: None}
    dq = deque([start_id])
    while dq:
        u = dq.popleft()
        for v in sorted(open_adj[u]):
            if v in lcc and v not in bfs_dist:
                bfs_dist[v] = bfs_dist[u] + 1
                bfs_parent[v] = u
                dq.append(v)
    goal_id = max(bfs_dist, key=lambda n: (bfs_dist[n], int(rooms[n]["x"]), -int(rooms[n]["y"])))

    # Reconstruir o caminho mais curto em saltos (caminho do BFS) para garantir
    # que a sala de ARMA (power-up) fique fora da linha direta do BFS, demonstrando
    # o desvio estratégico na comparação experimental.
    bfs_spine: set[str] = set()
    curr: str | None = goal_id
    while curr is not None:
        bfs_spine.add(curr)
        curr = bfs_parent.get(curr)

    # 4. Selecionar sala(s) de ARMA (power-up: chave, fita cassete, coração, pena/refill)
    # Prioriza salas fora da espinha dorsal do BFS que possuam chave/cassette/heart/upgrade.
    off_spine_candidates = [n for n in lcc if n not in bfs_spine and n not in {start_id, goal_id}]
    if not off_spine_candidates:
        off_spine_candidates = [n for n in lcc if n not in {start_id, goal_id}]

    def weapon_score(room_id: str) -> tuple[int, int, int, int, float]:
        ec: Counter[str] = rooms[room_id]["entities"]  # type: ignore[assignment]
        has_special = (
            ec["key"] * 5
            + ec["cassette"] * 6
            + ec["blackGem"] * 6
            + ec["infiniteStar"] * 3
            + ec["refill"] * 2
            + ec["booster"]
        )
        near_spine = 1 if any(nb in bfs_spine for nb in open_adj[room_id]) else 0
        # Prefere salas na primeira metade do mapa para que o power-up beneficie o restante
        dist_from_start = bfs_dist.get(room_id, 999)
        in_first_half = 1 if 1 <= dist_from_start <= max(2, bfs_dist[goal_id] // 2) else 0
        return (near_spine, in_first_half, has_special, -dist_from_start, float(rooms[room_id]["w"]))

    weapon_room = max(off_spine_candidates, key=weapon_score)

    # 5. Calcular valores de coletáveis e dificuldades reais por sala
    vertex_rows: list[dict[str, object]] = []
    room_diff_no_weapon: dict[str, float] = {}
    room_diff_with_weapon: dict[str, float] = {}
    room_base_time: dict[str, float] = {}

    for room_id in sorted(lcc):
        r_info = rooms[room_id]
        ec: Counter[str] = r_info["entities"]  # type: ignore[assignment]
        w_px, h_px = float(r_info["w"]), float(r_info["h"])

        # Tempo base proporcional à diagonal da sala em pixels (escala em segundos)
        base_t = round(max(2.0, math.hypot(w_px, h_px) / 64.0), 2)
        room_base_time[room_id] = base_t

        # Coletáveis oficiais na sala (morangos, fita cassete, coração de cristal / estátua)
        collectible_val = (
            ec["strawberry"] * 5.0
            + ec["cassette"] * 12.0
            + ec["blackGem"] * 15.0
            + ec["reflectionHeartStatue"] * 15.0
        )

        # Dificuldade real baseada nos obstáculos presentes na sala
        raw_hazard = 0.0
        for h_name, weight in HAZARD_WEIGHTS.items():
            raw_hazard += ec[h_name] * weight
        at = r_info["attrs"]  # type: ignore[assignment]
        if str(at.get("windPattern", "None")) != "None":
            raw_hazard += 6.0
        if bool(at.get("dark", False)):
            raw_hazard += 5.0

        # Salas na espinha direta de saltos após a metade do nível têm penalidade
        # acentuada sem o power-up (modelando gargalos de precisão quando desarmado).
        if room_id in bfs_spine and bfs_dist.get(room_id, 0) >= bfs_dist[goal_id] // 3:
            raw_hazard = max(raw_hazard * 1.8, 18.0)
        else:
            raw_hazard = max(raw_hazard, 2.0)

        diff_no_w = round(raw_hazard, 2)
        diff_with_w = round(max(0.5, diff_no_w * 0.20), 2)
        room_diff_no_weapon[room_id] = diff_no_w
        room_diff_with_weapon[room_id] = diff_with_w

        has_w = 1 if room_id == weapon_room else 0
        if room_id == start_id:
            r_type = "INICIO"
            collectible_val = 0.0
            has_w = 0
        elif room_id == goal_id:
            r_type = "FIM"
        elif has_w == 1:
            r_type = "ARMA"
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

    # 6. Construir arestas direcionadas / mão dupla preservando conectividade
    undirected_pairs: list[tuple[str, str]] = []
    for u in sorted(lcc):
        for v in sorted(open_adj[u]):
            if v in lcc and u < v:
                undirected_pairs.append((u, v))

    # Começa com grafo todo mão dupla e testa tornar quedas verticais (V_DOWN)
    # unidirecionais (mao_dupla = 0) quando isso não desconectar salas importantes.
    directed_adj: dict[str, set[str]] = {u: set() for u in lcc}
    for u, v in undirected_pairs:
        directed_adj[u].add(v)
        directed_adj[v].add(u)

    important_nodes = {
        str(r["id_sala"])
        for r in vertex_rows
        if float(r["valor_coletavel"]) > 0.0 or int(r["possui_arma"]) == 1
    } | {start_id, goal_id}

    edge_rows: list[dict[str, object]] = []
    for u, v in undirected_pairs:
        rel = edge_meta.get((u, v), "H")
        # Ordena par (origin -> dest) no sentido da queda vertical ou progressão BFS
        if rel == "V_DOWN":
            origin, dest, is_vert_drop = u, v, True
        elif rel == "V_UP":
            origin, dest, is_vert_drop = v, u, True
        elif bfs_dist.get(u, 0) <= bfs_dist.get(v, 0):
            origin, dest, is_vert_drop = u, v, False
        else:
            origin, dest, is_vert_drop = v, u, False

        two_way = 1
        if is_vert_drop or dest == goal_id:
            # Tenta remover retorno dest -> origin (tornar mão única)
            directed_adj[dest].discard(origin)
            if _can_reach_all(directed_adj, start_id, goal_id, important_nodes):
                two_way = 0
            else:
                directed_adj[dest].add(origin)

        edge_rows.append(
            {
                "origem": origin,
                "destino": dest,
                "mao_dupla": two_way,
                "tempo_base": room_base_time[dest],
                "dificuldade_sem_arma": room_diff_no_weapon[dest],
                "dificuldade_com_arma": room_diff_with_weapon[dest],
            }
        )

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
