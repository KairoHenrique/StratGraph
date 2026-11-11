"""Leitura e validação dos arquivos CSV do dataset (`vertices.csv` e `arestas.csv`)."""

from pathlib import Path

from src.models import GameGraph


def load_graph_from_csv(dataset_dir: Path) -> GameGraph:
    """Carrega `vertices.csv` e `arestas.csv`, valida esquema e retorna um `GameGraph`."""
    raise NotImplementedError("A ser implementado na Fase 2.")

