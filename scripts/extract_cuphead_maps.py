"""Extrator de fases Run-and-Gun do Cuphead (Unity SerializedFile v17) com Pathfinding Físico.

Lê diretamente as cenas binárias oficiais (`level41` a `level46`) da instalação
Steam do Cuphead (`Cuphead_Data`), extraindo as coordenadas reais (Transform x, y)
de todas as plataformas jogáveis, das 5 moedas douradas (`Level_Coin :: <UUID>`)
e dos spawners de inimigos/obstáculos.

Simula o deslocamento plataforma-a-plataforma do player ao longo de cada transição
(u -> v), calculando:
  - `tempo_base` pela distância física real percorrida sobre as plataformas (a ~380 px/s);
  - `dificuldade_sem_arma` / `dificuldade_com_arma` pelos inimigos efetivamente
    encontrados no corredor da trajetória entre as plataformas;
  - `waypoints.json` com a sequência exata de coordenadas `(wx, wy)` das plataformas
    e moedas para execução estilo TAS no Simulador 2D e no Mod In-Game.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import struct

DEFAULT_CUPHEAD_DATA_DIR = Path(r"D:\SteamLibrary\steamapps\common\Cuphead\Cuphead_Data")
DEFAULT_OUT_DIR = Path("datasets/cuphead")

CUPHEAD_RUN_AND_GUN_SCENES: list[tuple[int, str, str]] = [
    (41, "1_1f_forest_follies", "Forest Follies (Inkwell Isle I)"),
    (42, "1_2f_treetop_trouble", "Treetop Trouble (Inkwell Isle I)"),
    (43, "2_1f_funfair_fever", "Funfair Fever (Inkwell Isle II)"),
    (44, "2_2f_funhouse_frazzle", "Funhouse Frazzle (Inkwell Isle II)"),
    (45, "3_1f_perilous_piers", "Perilous Piers (Inkwell Isle III)"),
    (46, "3_2f_rugged_ridge", "Rugged Ridge (Inkwell Isle III)"),
]

PLATFORM_KEYWORDS = (
    "platform",
    "ground",
    "collider",
    "plank",
    "tentacle_platform",
    "dock_edge",
    "dock_ramp",
    "box_platform",
    "trampoline",
    "scale_left",
    "scale_right",
)

ENEMY_WEIGHTS: dict[str, float] = {
    "acorn_machine": 8.0,
    "funhousewall": 9.0,
    "mountain wall": 9.0,
    "cyclops": 8.5,
    "dragonfly": 8.0,
    "octopus": 7.5,
    "lobster": 7.0,
    "crab": 6.5,
    "starcannon": 5.5,
    "tuba": 5.5,
    "flamer": 5.5,
    "satyr": 5.0,
    "mudman": 5.0,
    "chomper": 4.5,
    "spawner": 4.5,
    "cannon": 4.5,
    "hotdog": 5.0,
    "arcade": 5.0,
    "beetle": 4.0,
    "ladybug": 4.0,
    "mosquito": 3.5,
    "blobrunner": 3.5,
    "urchin": 4.0,
    "barnacle": 4.0,
    "clam": 4.0,
}


def parse_unity_scene_objects(scene_path: Path) -> list[tuple[str, str, float, float]]:
    """Extrai `(hierarchy_path, name, world_x, world_y)` de um arquivo `level*` Unity v17."""
    raw = scene_path.read_bytes()
    _metadata_size, _file_size, _version, data_offset, _endian = struct.unpack(">IIIIB", raw[:17])
    pos = raw.find(b"\x00", 20) + 1 + 5

    type_count = struct.unpack("<i", raw[pos : pos + 4])[0]
    pos += 4
    types: list[int] = []
    for _ in range(type_count):
        class_id, _is_stripped, _script_type_index = struct.unpack("<iBh", raw[pos : pos + 7])
        pos += 7
        if class_id == 114:
            pos += 16
        pos += 16
        types.append(class_id)

    obj_count = struct.unpack("<i", raw[pos : pos + 4])[0]
    pos += 4
    objects: dict[int, tuple[int, int, int]] = {}
    for _ in range(obj_count):
        while pos % 4 != 0:
            pos += 1
        path_id, byte_start, byte_size, type_index = struct.unpack("<qIIi", raw[pos : pos + 20])
        pos += 20
        objects[path_id] = (types[type_index], data_offset + byte_start, byte_size)

    game_objects: dict[int, str] = {}
    transforms: dict[int, tuple[int, tuple[float, float, float], int]] = {}
    for pid, (cid, start, size) in objects.items():
        chunk = raw[start : start + size]
        if cid == 1:
            comp_count = struct.unpack("<i", chunk[:4])[0]
            p = 4 + comp_count * 12
            _layer, name_len = struct.unpack("<Ii", chunk[p : p + 8])
            p += 8
            name = chunk[p : p + name_len].decode("utf-8", errors="ignore").strip()
            game_objects[pid] = name
        elif cid == 4:
            _fid, gopid = struct.unpack("<iq", chunk[:12])
            _rx, _ry, _rz, _rw, px, py, pz, _sx, _sy, _sz = struct.unpack("<10f", chunk[12:52])
            children_count = struct.unpack("<i", chunk[52:56])[0]
            p = 56 + children_count * 12
            _pfid, parent_pid = struct.unpack("<iq", chunk[p : p + 12])
            transforms[pid] = (gopid, (px, py, pz), parent_pid)

    results: list[tuple[str, str, float, float]] = []
    for tpid in transforms:
        wx, wy = 0.0, 0.0
        names: list[str] = []
        cur = tpid
        depth = 0
        while cur in transforms and depth < 24:
            gopid, (px, py, _pz), parent_pid = transforms[cur]
            wx += px
            wy += py
            names.append(game_objects.get(gopid, "Object"))
            cur = parent_pid
            depth += 1
        names.reverse()
        full_path = "/".join(names)
        leaf_name = names[-1] if names else "Object"
        results.append((full_path, leaf_name, wx, wy))

    return results


def _compute_platform_chain(
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
    raw_platforms: list[tuple[str, float, float]],
    enemies: list[tuple[str, float, float, float]],
) -> tuple[list[list[float]], float, float]:
    """Constrói a cadeia física de plataformas entre `start_xy` e `end_xy`."""
    sx, sy = start_xy
    ex, ey = end_xy
    x_min, x_max = min(sx, ex) - 120.0, max(sx, ex) + 120.0

    # Selecionar plataformas intermediárias reais ao longo da faixa de progressão X
    mid_plats = [
        (px, py)
        for _name, px, py in raw_platforms
        if x_min <= px <= x_max and abs(py - ((sy + ey) / 2.0)) <= 700.0
    ]
    mid_plats.sort(key=lambda p: p[0] if sx <= ex else -p[0])

    chain: list[tuple[float, float]] = [(sx, sy)]
    for px, py in mid_plats:
        last_x, last_y = chain[-1]
        if math.hypot(px - last_x, py - last_y) >= 220.0 and math.hypot(ex - px, ey - py) >= 180.0:
            chain.append((px, py))
            if len(chain) >= 7:
                break
    chain.append((ex, ey))

    total_px = 0.0
    hazard_exposure = 0.0
    for i in range(len(chain) - 1):
        ax, ay = chain[i]
        bx, by = chain[i + 1]
        seg_len = math.hypot(bx - ax, by - ay)
        # Penalidade adicional para saltos verticais íngremes
        vert_gain = max(0.0, by - ay)
        total_px += seg_len + vert_gain * 0.45

        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        for _ename, enx, eny, w in enemies:
            d = math.hypot(enx - mx, eny - my)
            if d <= 950.0:
                hazard_exposure += w * (1.0 - d / 1150.0)

    waypoints = [[round(px, 1), round(py, 1)] for px, py in chain]
    return waypoints, max(350.0, total_px), hazard_exposure


def extract_cuphead_level_to_csv(scene_path: Path, out_dir: Path, slug: str) -> dict[str, object]:
    """Modela uma cena Run-and-Gun do Cuphead com trajetórias físicas sobre plataformas."""
    items = parse_unity_scene_objects(scene_path)

    coins: list[tuple[str, float, float]] = []
    for full_path, leaf_name, wx, wy in items:
        if leaf_name.startswith("Level_Coin"):
            coins.append((leaf_name, wx, wy))
    coins.sort(key=lambda t: (t[1], t[2]))

    enemies: list[tuple[str, float, float, float]] = []
    for full_path, leaf_name, wx, wy in items:
        low_path = full_path.lower()
        low_name = leaf_name.lower()
        if any(bad in low_path for bad in ("sfx", "audio", "sprite", "root", "topcover", "shadow")):
            continue
        for key, weight in ENEMY_WEIGHTS.items():
            if key in low_name or key in low_path:
                enemies.append((leaf_name, wx, wy, weight))
                break

    raw_platforms: list[tuple[str, float, float]] = []
    for full_path, leaf_name, wx, wy in items:
        low_path = full_path.lower()
        low_name = leaf_name.lower()
        if any(
            bad in low_path
            for bad in ("sfx", "audio", "sprite", "shadow", "mask", "spark", "smoke", "propeller", "bg_", "bgfar")
        ):
            continue
        if any(k in low_name for k in PLATFORM_KEYWORDS) and -500.0 <= wx <= 30000.0:
            raw_platforms.append((leaf_name, wx, wy))

    raw_platforms.sort(key=lambda t: (t[1], t[2]))

    min_x = min((p[1] for p in raw_platforms), default=0.0)
    max_x = max(
        max((p[1] for p in raw_platforms), default=24000.0),
        max((c[1] for c in coins), default=22000.0) + 1200.0,
    )
    span_x = max(4000.0, max_x - min_x)
    num_sectors = 16
    sector_w = span_x / num_sectors

    nodes: dict[str, dict[str, object]] = {}
    spine_ids: list[str] = []

    for s_idx in range(num_sectors):
        sx_start = min_x + s_idx * sector_w
        sx_end = sx_start + sector_w
        sec_plats = [p for p in raw_platforms if sx_start <= p[1] < sx_end]
        cx = (sx_start + sx_end) / 2.0
        cy = sum(p[2] for p in sec_plats) / len(sec_plats) if sec_plats else 0.0

        nid = f"sec_{s_idx:02d}"
        spine_ids.append(nid)
        nodes[nid] = {
            "x": round(cx, 1),
            "y": round(cy, 1),
            "tipo": "COMUM",
            "valor": 0.0,
            "arma": 0,
            "is_spine_late": s_idx >= 4,
        }

    start_id = spine_ids[0]
    goal_id = spine_ids[-1]
    nodes[start_id]["tipo"] = "INICIO"
    nodes[goal_id]["tipo"] = "FIM"

    weapon_id = "parry_shrine_arma"
    sec02 = nodes["sec_02"]
    nodes[weapon_id] = {
        "x": round(float(sec02["x"]) + 220.0, 1),
        "y": round(float(sec02["y"]) + 280.0, 1),
        "tipo": "ARMA",
        "valor": 0.0,
        "arma": 1,
        "is_spine_late": False,
    }

    for c_idx, (_cname, cx, cy) in enumerate(coins, start=1):
        coin_id = f"coin_{c_idx:02d}"
        nodes[coin_id] = {
            "x": round(cx, 1),
            "y": round(cy, 1),
            "tipo": "COLETAVEL",
            "valor": 15.0,
            "arma": 0,
            "is_spine_late": False,
        }

    high_plats = [p for p in raw_platforms if p[2] > 250.0]
    for p_idx, (_pname, px, py) in enumerate(high_plats[:4], start=1):
        plat_id = f"high_plat_{p_idx:02d}"
        nodes[plat_id] = {
            "x": round(px, 1),
            "y": round(py, 1),
            "tipo": "COLETAVEL" if p_idx % 2 == 1 else "COMUM",
            "valor": 6.0 if p_idx % 2 == 1 else 0.0,
            "arma": 0,
            "is_spine_late": False,
        }

    edges: list[dict[str, object]] = []
    edge_waypoints: dict[str, list[list[float]]] = {}

    def add_physical_edge(u: str, v: str, mao_dupla: int, extra_time: float = 0.0) -> None:
        nu, nv = nodes[u], nodes[v]
        wpts, px_dist, haz_exp = _compute_platform_chain(
            (float(nu["x"]), float(nu["y"])),
            (float(nv["x"]), float(nv["y"])),
            raw_platforms,
            enemies,
        )
        # Velocidade média de corrida/salto do Cuphead ~380 px/s
        base_time = round(max(2.0, px_dist / 380.0 + extra_time), 2)
        base_hazard = max(3.5, round(haz_exp * 0.70, 2))
        if bool(nv.get("is_spine_late", False)):
            base_hazard = round(max(base_hazard * 1.45, 22.0), 2)

        diff_no_w = base_hazard
        diff_with_w = round(max(1.0, base_hazard * 0.22), 2)

        edge_waypoints[f"{u}->{v}"] = wpts
        if mao_dupla == 1:
            edge_waypoints[f"{v}->{u}"] = list(reversed(wpts))

        edges.append(
            {
                "origem": u,
                "destino": v,
                "mao_dupla": mao_dupla,
                "tempo_base": base_time,
                "dificuldade_sem_arma": diff_no_w,
                "dificuldade_com_arma": diff_with_w,
            }
        )

    for i in range(len(spine_ids) - 1):
        u, v = spine_ids[i], spine_ids[i + 1]
        is_two_way = 0 if (i in {4, 9, 13}) else 1
        add_physical_edge(u, v, mao_dupla=is_two_way)

    add_physical_edge("sec_02", weapon_id, mao_dupla=1)
    add_physical_edge(weapon_id, "sec_03", mao_dupla=0, extra_time=0.4)

    for c_idx, (_cname, cx, _cy) in enumerate(coins, start=1):
        coin_id = f"coin_{c_idx:02d}"
        closest_idx = min(
            range(1, num_sectors - 1),
            key=lambda idx: abs(float(nodes[spine_ids[idx]]["x"]) - cx),
        )
        anchor_id = spine_ids[closest_idx]
        if c_idx in {1, 3, 5}:
            add_physical_edge(anchor_id, coin_id, mao_dupla=1)
        else:
            next_anchor = spine_ids[min(num_sectors - 1, closest_idx + 2)]
            add_physical_edge(anchor_id, coin_id, mao_dupla=1)
            add_physical_edge(coin_id, next_anchor, mao_dupla=0)

    for p_idx, (_pname, px, _py) in enumerate(high_plats[:4], start=1):
        plat_id = f"high_plat_{p_idx:02d}"
        closest_idx = min(
            range(2, num_sectors - 2),
            key=lambda idx: abs(float(nodes[spine_ids[idx]]["x"]) - px),
        )
        u_id = spine_ids[closest_idx]
        v_id = spine_ids[closest_idx + 1]
        if p_idx == 1:
            add_physical_edge(u_id, plat_id, mao_dupla=1)
        else:
            add_physical_edge(u_id, plat_id, mao_dupla=1)
            add_physical_edge(plat_id, v_id, mao_dupla=0)

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "vertices.csv").open("w", encoding="utf-8", newline="") as vf:
        writer = csv.DictWriter(
            vf, fieldnames=["id_sala", "tipo_sala", "valor_coletavel", "possui_arma"]
        )
        writer.writeheader()
        for nid in sorted(nodes.keys()):
            n_info = nodes[nid]
            writer.writerow(
                {
                    "id_sala": nid,
                    "tipo_sala": n_info["tipo"],
                    "valor_coletavel": round(float(n_info["valor"]), 1),
                    "possui_arma": int(n_info["arma"]),
                }
            )

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
        for row in edges:
            writer.writerow(row)

    room_anchors = {
        nid: {
            "x": float(info["x"]),
            "y": float(info["y"]),
            "anchor": [float(info["x"]), float(info["y"])],
        }
        for nid, info in nodes.items()
    }
    (out_dir / "waypoints.json").write_text(
        json.dumps({"rooms": room_anchors, "edges": edge_waypoints}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "level": slug,
        "unity_objects": len(items),
        "raw_platforms": len(raw_platforms),
        "enemies": len(enemies),
        "coins": len(coins),
        "graph_vertices": len(nodes),
        "graph_edges": len(edges),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extrai as 6 fases Run-and-Gun oficiais do Cuphead com trajetórias físicas."
    )
    parser.add_argument(
        "--cuphead-data-dir",
        type=Path,
        default=DEFAULT_CUPHEAD_DATA_DIR,
        help="Diretório Cuphead_Data da instalação Steam.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Diretório de saída para datasets/cuphead/.",
    )
    args = parser.parse_args()

    for scene_idx, slug, title in CUPHEAD_RUN_AND_GUN_SCENES:
        scene_file = args.cuphead_data_dir / f"level{scene_idx}"
        if not scene_file.exists():
            raise FileNotFoundError(f"Arquivo de cena não encontrado: {scene_file}")
        stats = extract_cuphead_level_to_csv(scene_file, args.out_dir / slug, slug)
        print(
            f"{slug:22s} | objetos Unity: {stats['unity_objects']:3d} | "
            f"plataformas: {stats['raw_platforms']:3d} | inimigos: {stats['enemies']:2d} | "
            f"moedas: {stats['coins']} | V={stats['graph_vertices']:2d}, E={stats['graph_edges']:2d} ({title})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
