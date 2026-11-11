"""Gerador determinístico de grafos sintéticos para análise de escalabilidade.

Gera instâncias em `datasets/synthetic/v_<N>/` com tamanhos
V in {15, 30, 60, 150, 500, 1500, 5000}, contendo:
- Espinha principal de progressão;
- Alcovas em beco sem saída com coletáveis (~20% dos vértices) para avaliar a
  contração de becos (`contract_dead_ends`);
- Salas de arma/upgrade fora da rota mínima em saltos;
- Atalhos e rotas alternativas direcionadas (`mao_dupla=0`) e bidirecionais (`mao_dupla=1`).

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import random

DEFAULT_SIZES = (15, 30, 60, 150, 500, 1500, 5000)
DEFAULT_OUT_DIR = Path("datasets/synthetic")


def generate_synthetic_graph(num_vertices: int, out_dir: Path, seed: int = 42) -> dict[str, int]:
    """Gera `vertices.csv` e `arestas.csv` com exatamente `num_vertices` salas."""
    if num_vertices < 8:
        raise ValueError("num_vertices deve ser >= 8.")

    rng = random.Random(seed + num_vertices)
    num_dead_ends = max(2, int(num_vertices * 0.20))
    num_weapon = max(1, min(3, num_vertices // 25))
    num_spine = num_vertices - num_dead_ends - num_weapon

    vertices: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []

    spine_ids = [f"s_{i:04d}" for i in range(num_spine)]
    for i, sid in enumerate(spine_ids):
        if i == 0:
            rtype = "INICIO"
            val = 0.0
        elif i == num_spine - 1:
            rtype = "FIM"
            val = 0.0
        elif rng.random() < 0.22:
            rtype = "COLETAVEL"
            val = round(rng.uniform(4.0, 12.0), 1)
        else:
            rtype = "COMUM"
            val = 0.0

        vertices.append(
            {
                "id_sala": sid,
                "tipo_sala": rtype,
                "valor_coletavel": val,
                "possui_arma": 0,
            }
        )

    # Arestas da espinha principal + atalhos locais (skip edges de 2 ou 3 saltos)
    for i in range(num_spine - 1):
        u = spine_ids[i]
        v = spine_ids[i + 1]
        base_t = round(rng.uniform(2.5, 6.0), 2)
        # Dificuldade alta sem arma após o primeiro quarto do mapa
        if i >= max(2, num_spine // 5):
            diff_no_w = round(rng.uniform(18.0, 32.0), 2)
        else:
            diff_no_w = round(rng.uniform(3.0, 8.0), 2)
        diff_with_w = round(diff_no_w * 0.22, 2)
        mao_dupla = 0 if (i % 5 == 3) else 1
        edges.append(
            {
                "origem": u,
                "destino": v,
                "mao_dupla": mao_dupla,
                "tempo_base": base_t,
                "dificuldade_sem_arma": diff_no_w,
                "dificuldade_com_arma": diff_with_w,
            }
        )

        # Adicionar aresta alternativa de salto (2 passos) com custo ligeiramente maior sem arma
        if i + 2 < num_spine and i % 3 == 1:
            edges.append(
                {
                    "origem": u,
                    "destino": spine_ids[i + 2],
                    "mao_dupla": 0,
                    "tempo_base": round(base_t * 2.1, 2),
                    "dificuldade_sem_arma": round(diff_no_w * 2.4, 2),
                    "dificuldade_com_arma": round(diff_with_w * 1.6, 2),
                }
            )

    # Salas de ARMA fora da espinha principal (no primeiro terço do grafo)
    for w_idx in range(num_weapon):
        wid = f"w_{w_idx:04d}"
        anchor_i = max(1, min(num_spine - 3, (w_idx + 1) * max(1, num_spine // (num_weapon + 4))))
        u_anchor = spine_ids[anchor_i]
        v_return = spine_ids[min(num_spine - 1, anchor_i + 1)]
        vertices.append(
            {
                "id_sala": wid,
                "tipo_sala": "ARMA",
                "valor_coletavel": 0.0,
                "possui_arma": 1,
            }
        )
        edges.append(
            {
                "origem": u_anchor,
                "destino": wid,
                "mao_dupla": 1,
                "tempo_base": 2.5,
                "dificuldade_sem_arma": 3.5,
                "dificuldade_com_arma": 1.0,
            }
        )
        edges.append(
            {
                "origem": wid,
                "destino": v_return,
                "mao_dupla": 0,
                "tempo_base": 2.8,
                "dificuldade_sem_arma": 4.0,
                "dificuldade_com_arma": 1.2,
            }
        )

    # Alcovas em beco sem saída (COLETAVEL) penduradas na espinha principal
    for d_idx in range(num_dead_ends):
        did = f"c_{d_idx:04d}"
        anchor_i = rng.randint(1, num_spine - 2)
        u_anchor = spine_ids[anchor_i]
        vertices.append(
            {
                "id_sala": did,
                "tipo_sala": "COLETAVEL",
                "valor_coletavel": round(rng.uniform(5.0, 15.0), 1),
                "possui_arma": 0,
            }
        )
        edges.append(
            {
                "origem": u_anchor,
                "destino": did,
                "mao_dupla": 1,
                "tempo_base": round(rng.uniform(1.8, 3.5), 2),
                "dificuldade_sem_arma": round(rng.uniform(2.0, 6.0), 2),
                "dificuldade_com_arma": round(rng.uniform(0.8, 2.0), 2),
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "vertices.csv").open("w", encoding="utf-8", newline="") as vf:
        writer = csv.DictWriter(
            vf, fieldnames=["id_sala", "tipo_sala", "valor_coletavel", "possui_arma"]
        )
        writer.writeheader()
        for row in vertices:
            writer.writerow(row)

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

    return {
        "num_vertices": len(vertices),
        "num_edges": len(edges),
        "num_dead_ends": num_dead_ends,
        "num_weapon": num_weapon,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera datasets sintéticos de escalabilidade.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Diretório de saída para os grafos sintéticos.",
    )
    args = parser.parse_args()

    for n in DEFAULT_SIZES:
        sub = args.out_dir / f"v_{n:04d}"
        stats = generate_synthetic_graph(n, sub)
        print(
            f"v_{n:04d} | V={stats['num_vertices']:4d} | E={stats['num_edges']:4d} | "
            f"becos={stats['num_dead_ends']:4d} | armas={stats['num_weapon']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
