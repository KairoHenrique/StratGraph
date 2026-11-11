"""Leitura e validação dos arquivos CSV do dataset (`vertices.csv` e `arestas.csv`)."""

import csv
from pathlib import Path

from src.models import Edge, GameGraph, RoomType, Vertex

REQUIRED_VERTEX_COLUMNS = {"id_sala", "tipo_sala", "valor_coletavel", "possui_arma"}
REQUIRED_EDGE_COLUMNS = {
    "origem",
    "destino",
    "mao_dupla",
    "tempo_base",
    "dificuldade_sem_arma",
    "dificuldade_com_arma",
}


def _parse_bool_flag(raw: str, field_name: str, row_num: int) -> bool:
    val = raw.strip().lower()
    if val in {"1", "true", "sim", "yes"}:
        return True
    if val in {"0", "false", "nao", "não", "no"}:
        return False
    raise ValueError(f"Linha {row_num}: valor inválido '{raw}' para '{field_name}' (use 0 ou 1).")


def load_graph_from_csv(dataset_dir: Path | str) -> GameGraph:
    """Carrega `vertices.csv` e `arestas.csv`, valida esquema e retorna um `GameGraph`."""
    base_path = Path(dataset_dir)
    vertices_file = base_path / "vertices.csv"
    edges_file = base_path / "arestas.csv"

    if not vertices_file.is_file():
        raise FileNotFoundError(f"Arquivo de vértices não encontrado: {vertices_file}")
    if not edges_file.is_file():
        raise FileNotFoundError(f"Arquivo de arestas não encontrado: {edges_file}")

    vertices: dict[str, Vertex] = {}
    adjacency: dict[str, list[Edge]] = {}
    original_collectibles: dict[str, float] = {}
    start_ids: list[str] = []
    goal_ids: list[str] = []

    with vertices_file.open(mode="r", encoding="utf-8", newline="") as vf:
        reader = csv.DictReader(vf)
        if reader.fieldnames is None or not REQUIRED_VERTEX_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Colunas inválidas em {vertices_file}. Esperado: {sorted(REQUIRED_VERTEX_COLUMNS)}"
            )

        for row_num, row in enumerate(reader, start=2):
            room_id = (row["id_sala"] or "").strip()
            if not room_id:
                raise ValueError(f"Linha {row_num} em vertices.csv: 'id_sala' vazio.")
            if room_id in vertices:
                raise ValueError(f"Linha {row_num} em vertices.csv: 'id_sala' duplicado '{room_id}'.")

            raw_type = (row["tipo_sala"] or "").strip().upper()
            try:
                room_type = RoomType(raw_type)
            except ValueError as exc:
                raise ValueError(
                    f"Linha {row_num} em vertices.csv: 'tipo_sala' inválido '{raw_type}'."
                ) from exc

            try:
                collectible_value = float(row["valor_coletavel"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Linha {row_num} em vertices.csv: 'valor_coletavel' inválido."
                ) from exc
            if collectible_value < 0.0:
                raise ValueError(
                    f"Linha {row_num} em vertices.csv: 'valor_coletavel' não pode ser negativo."
                )

            has_weapon = _parse_bool_flag(row["possui_arma"], "possui_arma", row_num)
            if room_type == RoomType.ARMA:
                has_weapon = True

            vertex = Vertex(
                room_id=room_id,
                room_type=room_type,
                collectible_value=collectible_value,
                has_weapon=has_weapon,
            )
            vertices[room_id] = vertex
            adjacency[room_id] = []
            if collectible_value > 0.0:
                original_collectibles[room_id] = collectible_value

            if room_type == RoomType.INICIO:
                start_ids.append(room_id)
            elif room_type == RoomType.FIM:
                goal_ids.append(room_id)

    if len(start_ids) != 1:
        raise ValueError(
            f"O grafo deve conter exatamente 1 sala 'INICIO' (encontradas: {len(start_ids)})."
        )
    if len(goal_ids) != 1:
        raise ValueError(
            f"O grafo deve conter exatamente 1 sala 'FIM' (encontradas: {len(goal_ids)})."
        )

    with edges_file.open(mode="r", encoding="utf-8", newline="") as ef:
        reader = csv.DictReader(ef)
        if reader.fieldnames is None or not REQUIRED_EDGE_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"Colunas inválidas em {edges_file}. Esperado: {sorted(REQUIRED_EDGE_COLUMNS)}"
            )

        for row_num, row in enumerate(reader, start=2):
            origin = (row["origem"] or "").strip()
            destination = (row["destino"] or "").strip()
            if origin not in vertices:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: vértice de origem '{origin}' inexistente."
                )
            if destination not in vertices:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: vértice de destino '{destination}' inexistente."
                )
            if origin == destination:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: auto-laço '{origin} -> {destination}' não permitido."
                )

            two_way = _parse_bool_flag(row["mao_dupla"], "mao_dupla", row_num)
            try:
                base_time = float(row["tempo_base"])
                diff_no_weapon = float(row["dificuldade_sem_arma"])
                diff_with_weapon = float(row["dificuldade_com_arma"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: pesos numéricos inválidos."
                ) from exc

            if base_time <= 0.0:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: 'tempo_base' deve ser estritamente positivo (> 0)."
                )
            if diff_no_weapon < 0.0 or diff_with_weapon < 0.0:
                raise ValueError(
                    f"Linha {row_num} em arestas.csv: dificuldades não podem ser negativas."
                )

            adjacency[origin].append(
                Edge(
                    origin=origin,
                    destination=destination,
                    base_time=base_time,
                    difficulty_no_weapon=diff_no_weapon,
                    difficulty_with_weapon=diff_with_weapon,
                    two_way=two_way,
                )
            )
            if two_way:
                adjacency[destination].append(
                    Edge(
                        origin=destination,
                        destination=origin,
                        base_time=base_time,
                        difficulty_no_weapon=diff_no_weapon,
                        difficulty_with_weapon=diff_with_weapon,
                        two_way=True,
                    )
                )

    return GameGraph(
        vertices=vertices,
        adjacency=adjacency,
        start_id=start_ids[0],
        goal_id=goal_ids[0],
        contracted_into={},
        original_collectibles=original_collectibles,
    )
