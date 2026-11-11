"""Modelos de dados para representação do grafo original e do grafo em camadas."""

from dataclasses import dataclass, field
from enum import Enum


class RoomType(str, Enum):
    """Tipos válidos de sala na coluna `tipo_sala` de `vertices.csv`."""

    INICIO = "INICIO"
    COMUM = "COMUM"
    COLETAVEL = "COLETAVEL"
    ARMA = "ARMA"
    FIM = "FIM"


@dataclass(frozen=True)
class Vertex:
    """Representa uma sala ou plataforma segura no mapa base."""

    room_id: str
    room_type: RoomType
    collectible_value: float = 0.0
    has_weapon: bool = False


@dataclass(frozen=True)
class Edge:
    """Representa uma transição direcionada no dígrafo base."""

    origin: str
    destination: str
    base_time: float
    difficulty_no_weapon: float
    difficulty_with_weapon: float
    two_way: bool = False


@dataclass(frozen=True)
class LayeredNode:
    """Nó no grafo expandido em camadas: (id_sala, camada_arma)."""

    room_id: str
    layer: int  # 0 = sem arma/power-up, 1 = com arma/power-up


@dataclass(frozen=True)
class LayeredEdge:
    """Aresta direcionada no grafo expandido em camadas."""

    origin: LayeredNode
    destination: LayeredNode
    effective_weight: float
    real_cost: float
    is_weapon_transition: bool = False


@dataclass
class GameGraph:
    """Estrutura de dígrafo base carregado a partir dos CSVs."""

    vertices: dict[str, Vertex] = field(default_factory=dict)
    adjacency: dict[str, list[Edge]] = field(default_factory=dict)
    start_id: str = ""
    goal_id: str = ""


@dataclass
class RouteResult:
    """Resultado padronizado retornado por qualquer algoritmo de busca."""

    algorithm: str
    found: bool
    path: list[LayeredNode] = field(default_factory=list)
    real_cost: float = float("inf")
    effective_cost: float = float("inf")
    collectibles_count: int = 0
    collectibles_total_value: float = 0.0
    collected_room_ids: set[str] = field(default_factory=set)
    visited_states: int = 0
    elapsed_ms: float = 0.0
    timed_out: bool = False

