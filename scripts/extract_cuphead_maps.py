"""Extrator de fases Run-and-Gun do Cuphead (Unity SerializedFile v17) para CSV.

Lê diretamente as cenas binárias oficiais (`level41` a `level46`) da instalação
Steam do Cuphead (`Cuphead_Data`), extraindo as coordenadas reais (Transform x, y)
de todas as plataformas jogáveis, das 5 moedas douradas (`Level_Coin :: <UUID>`)
e dos spawners de inimigos/obstáculos para construir os dígrafos ponderados em
`datasets/cuphead/`.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
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


def extract_cuphead_level_to_csv(scene_path: Path, out_dir: Path, slug: str) -> dict[str, object]:
    """Modela uma cena Run-and-Gun do Cuphead como dígrafo ponderado em CSV."""
    items = parse_unity_scene_objects(scene_path)

    # 1. Identificar as 5 moedas oficiais (Level_Coin :: <UUID>)
    coins: list[tuple[str, float, float]] = []
    for full_path, leaf_name, wx, wy in items:
        if leaf_name.startswith("Level_Coin"):
            coins.append((leaf_name, wx, wy))
    coins.sort(key=lambda t: (t[1], t[2]))

    # 2. Identificar inimigos e spawners reais na cena com seus pesos de ameaça
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

    # 3. Identificar plataformas jogáveis e agrupar em setores espaciais (~850 px)
    raw_platforms: list[tuple[str, float, float]] = []
    for full_path, leaf_name, wx, wy in items:
        low_path = full_path.lower()
        low_name = leaf_name.lower()
        if any(bad in low_path for bad in ("sfx", "audio", "sprite", "shadow", "mask", "spark", "smoke", "propeller", "bg_", "bgfar")):
            continue
        if any(k in low_name for k in PLATFORM_KEYWORDS) and -500.0 <= wx <= 30000.0:
            raw_platforms.append((leaf_name, wx, wy))

    raw_platforms.sort(key=lambda t: (t[1], t[2]))

    # Agrupar plataformas ao longo da progressão da fase em setores principais + rotas superiores/inferiores
    min_x = min((p[1] for p in raw_platforms), default=0.0)
    max_x = max(max((p[1] for p in raw_platforms), default=24000.0), max((c[1] for c in coins), default=22000.0) + 1200.0)
    span_x = max(4000.0, max_x - min_x)
    num_sectors = 16
    sector_w = span_x / num_sectors

    # Construir nós da espinha principal (sec_00 a sec_15) e plataformas elevadas/alternativas
    nodes: dict[str, dict[str, object]] = {}
    spine_ids: list[str] = []

    for s_idx in range(num_sectors):
        sx_start = min_x + s_idx * sector_w
        sx_end = sx_start + sector_w
        sec_plats = [p for p in raw_platforms if sx_start <= p[1] < sx_end]
        cx = (sx_start + sx_end) / 2.0
        cy = sum(p[2] for p in sec_plats) / len(sec_plats) if sec_plats else 0.0

        # Calcular ameaça de inimigos próximos a este setor (raio de 1500 px)
        near_threat = sum(
            w for _en, ex, ey, w in enemies if abs(ex - cx) <= 1400.0 and abs(ey - cy) <= 1200.0
        )
        # Setores a partir do terço intermediário têm mais pressão de projéteis desarmado
        base_hazard = max(4.0, round(near_threat * 0.65, 2))
        if s_idx >= 4:
            base_hazard = round(max(base_hazard * 1.45, 22.0), 2)

        nid = f"sec_{s_idx:02d}"
        spine_ids.append(nid)
        nodes[nid] = {
            "x": cx,
            "y": cy,
            "tipo": "COMUM",
            "valor": 0.0,
            "arma": 0,
            "base_time": round(max(2.5, sector_w / 420.0), 2),
            "diff_no_w": base_hazard,
            "diff_with_w": round(max(1.0, base_hazard * 0.22), 2),
        }

    # Marcar início e fim da fase
    start_id = spine_ids[0]
    goal_id = spine_ids[-1]
    nodes[start_id]["tipo"] = "INICIO"
    nodes[goal_id]["tipo"] = "FIM"

    edges: list[dict[str, object]] = []

    def add_edge(u: str, v: str, mao_dupla: int, extra_time: float = 0.0) -> None:
        t_info = nodes[v]
        edges.append(
            {
                "origem": u,
                "destino": v,
                "mao_dupla": mao_dupla,
                "tempo_base": round(float(t_info["base_time"]) + extra_time, 2),
                "dificuldade_sem_arma": round(float(t_info["diff_no_w"]), 2),
                "dificuldade_com_arma": round(float(t_info["diff_with_w"]), 2),
            }
        )

    # Conectar espinha dorsal da fase (com transições unidirecionais em quedas de plataforma)
    for i in range(len(spine_ids) - 1):
        u, v = spine_ids[i], spine_ids[i + 1]
        # Quedas/avanços de câmera típicos de Run-and-Gun a cada 4 setores são mão única
        is_two_way = 0 if (i in {4, 9, 13}) else 1
        add_edge(u, v, mao_dupla=is_two_way)

    # 4. Adicionar o Santuário/Totem de Parry & Super Art (ARMA) fora da rota direta (no setor 02)
    weapon_id = "parry_shrine_arma"
    sec02 = nodes["sec_02"]
    nodes[weapon_id] = {
        "x": float(sec02["x"]) + 220.0,
        "y": float(sec02["y"]) + 280.0,
        "tipo": "ARMA",
        "valor": 0.0,
        "arma": 1,
        "base_time": 2.8,
        "diff_no_w": 4.5,
        "diff_with_w": 1.2,
    }
    # Desvio estratégico: sec_02 <-> parry_shrine_arma -> sec_03
    add_edge("sec_02", weapon_id, mao_dupla=1)
    add_edge(weapon_id, "sec_03", mao_dupla=0, extra_time=0.5)

    # 5. Adicionar as 5 moedas oficiais (`Level_Coin`) extraídas da cena Unity:
    #    - 3 moedas em alcovas sem saída (becos sem saída com `mao_dupla=1` que serão contraídos no pré-processamento)
    #    - 2 moedas em plataformas elevadas alternativas (pontes superiores `sec_k -> coin_m -> sec_{k+1}`)
    for c_idx, (_cname, cx, cy) in enumerate(coins, start=1):
        coin_id = f"coin_{c_idx:02d}"
        # Encontrar setor mais próximo em X (entre sec_01 e sec_14)
        closest_idx = min(
            range(1, num_sectors - 1),
            key=lambda idx: abs(float(nodes[spine_ids[idx]]["x"]) - cx),
        )
        anchor_id = spine_ids[closest_idx]
        near_threat = sum(
            w for _en, ex, ey, w in enemies if abs(ex - cx) <= 1000.0 and abs(ey - cy) <= 900.0
        )
        c_hazard = round(max(3.5, near_threat * 0.45), 2)
        nodes[coin_id] = {
            "x": cx,
            "y": cy,
            "tipo": "COLETAVEL",
            "valor": 15.0,
            "arma": 0,
            "base_time": 2.4,
            "diff_no_w": c_hazard,
            "diff_with_w": round(max(1.0, c_hazard * 0.25), 2),
        }
        if c_idx in {1, 3, 5}:
            # Beco sem saída (alcova lateral/inferior de moeda): grau 1 bidirecional -> contração de beco
            add_edge(anchor_id, coin_id, mao_dupla=1)
        else:
            # Rota aérea alternativa passando pela moeda (saltando o setor intermediário inferior)
            next_anchor = spine_ids[min(num_sectors - 1, closest_idx + 2)]
            add_edge(anchor_id, coin_id, mao_dupla=1)
            add_edge(coin_id, next_anchor, mao_dupla=0)

    # 6. Adicionar sub-plataformas reais extras (parry/atalhos elevados) a partir dos clusters verticais
    high_plats = [p for p in raw_platforms if p[2] > 250.0]
    for p_idx, (_pname, px, py) in enumerate(high_plats[:4], start=1):
        plat_id = f"high_plat_{p_idx:02d}"
        closest_idx = min(
            range(2, num_sectors - 2),
            key=lambda idx: abs(float(nodes[spine_ids[idx]]["x"]) - px),
        )
        u_id = spine_ids[closest_idx]
        v_id = spine_ids[closest_idx + 1]
        nodes[plat_id] = {
            "x": px,
            "y": py,
            "tipo": "COLETAVEL" if p_idx % 2 == 1 else "COMUM",
            "valor": 6.0 if p_idx % 2 == 1 else 0.0,
            "arma": 0,
            "base_time": 2.6,
            "diff_no_w": 9.0,
            "diff_with_w": 2.0,
        }
        if p_idx == 1:
            # Alcova sem saída com bônus de parry (testa contração adicional)
            add_edge(u_id, plat_id, mao_dupla=1)
        else:
            add_edge(u_id, plat_id, mao_dupla=1)
            add_edge(plat_id, v_id, mao_dupla=0)

    # Exportar CSVs
    out_dir.mkdir(parents=True, exist_ok=True)
    vertices_csv = out_dir / "vertices.csv"
    arestas_csv = out_dir / "arestas.csv"

    with vertices_csv.open("w", encoding="utf-8", newline="") as vf:
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

    with arestas_csv.open("w", encoding="utf-8", newline="") as ef:
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
        description="Extrai as 6 fases Run-and-Gun oficiais do Cuphead (Unity binary scenes) para CSV."
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
