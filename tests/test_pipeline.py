"""Esqueleto de testes do pipeline de grafos em camadas."""

from pathlib import Path

from src.models import RoomType, Vertex


def test_base_structure_imports() -> None:
    """Garante que os modelos base e o dataset de exemplo existem e importam."""
    v = Vertex(room_id="S0", room_type=RoomType.INICIO)
    assert v.room_id == "S0"
    assert Path("datasets/sample_toy/vertices.csv").exists()
    assert Path("datasets/sample_toy/arestas.csv").exists()

