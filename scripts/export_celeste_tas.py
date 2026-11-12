"""Gerador e Validador Sintático de Arquivos `.tas` para CelesteTAS (Everest).

Converte as rotas ótimas resolvidas pelo motor **StratGraph** (`src/`, apenas Python 3.12)
e pelo baseline **BFS** sob meta de 100% dos coletáveis em arquivos `.tas` quadro a quadro
(60 FPS) compatíveis com **CelesteTAS v3.47+ / Celeste Studio**.

Observação metodológica:
    Como a física real de *Celeste* envolve posição subpixel e inércia contínua entre salas,
    e o *StratGraph* reordena desvios táticos (`ARMA` + becos contraídos), os scripts `.tas`
    exportam rótulos `#lvl_<sala>` e âncoras `console load <id> <sala>` (`Unsafe`) para
    validação modular por sala no ecossistema Everest + CelesteTAS, enquanto o simulador 2D
    e os experimentos principais do artigo rodam integralmente *offline* em Python.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extract_celeste_maps import CHAPTER_FILES
from src.algorithms import run_bfs, run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.preprocessing import contract_dead_ends

TAS_DIR = ROOT / "tas" / "celeste"

CHAPTER_AREA_IDS: dict[str, int] = {
    "1_forsaken_city": 1,
    "2_old_site": 2,
    "3_celestial_resort": 3,
    "4_golden_ridge": 4,
    "5_mirror_temple": 5,
    "6_reflection": 6,
    "7_summit": 7,
    "9_core": 9,
}

# Gramática oficial de linhas de frame no CelesteTAS (contagem de quadros + tokens válidos)
TAS_INPUT_LINE_RE = re.compile(r"^\s*(\d+)(?:,([LRUDJXKGCZQFOPSN](?:,[LRUDJXKGCZQFOPSN])*))?\s*$")


@dataclass(slots=True)
class TasChapterReport:
    chapter: str
    area_id: int
    algo_name: str
    tas_path: Path
    total_frames: int
    duration_s: float
    rooms_visited: int
    collectibles: int
    real_cost: float
    eff_cost: float
    used_weapon: bool


def _append_frames(
    ops: list[tuple[int, tuple[str, ...]]],
    frames: int,
    tokens: tuple[str, ...],
) -> None:
    """Anexa um bloco de quadros mesclando instruções adjacentes idênticas."""
    count = max(1, int(frames))
    if ops and ops[-1][1] == tokens:
        prev_n, _ = ops[-1]
        ops[-1] = (prev_n + count, tokens)
    else:
        ops.append((count, tokens))


def _waypoints_to_tas_frames(waypoints: list[list[float]]) -> list[tuple[int, tuple[str, ...]]]:
    """Traduz uma polilinha de waypoints `(wx, wy)` em comandos 60 FPS do CelesteTAS.

    Constantes base (60 FPS):
      - Corrida no solo (`MaxRun = 90 px/s`): ~1.50 px/frame
      - Pulo segurado (`JumpSpeed = -105 px/s`, `varJumpTime = 0.20s`): ~12 frames `J`
      - Escalada vertical (`ClimbUp = 45 px/s`): ~0.75 px/frame segurando `G`
      - Dash único (`DashSpeed = 240 px/s`, `DashTime = 0.15s`): 9 frames `X`
    """
    ops: list[tuple[int, tuple[str, ...]]] = []
    if len(waypoints) < 2:
        return ops

    px, py = float(waypoints[0][0]), float(waypoints[0][1])
    for wx_raw, wy_raw in waypoints[1:]:
        wx, wy = float(wx_raw), float(wy_raw)
        dx = wx - px
        dy = wy - py  # Em Celeste, Y negativo aponta para CIMA
        dist = math.hypot(dx, dy)
        px, py = wx, wy
        if dist < 2.0:
            continue

        horiz: tuple[str, ...] = ()
        if abs(dx) > 4.0:
            horiz = ("R",) if dx > 0 else ("L",)

        # 1. Subida curta ou média compatível com pulo segurado (sem gastar o 1 dash)
        if dy < -6.0 and abs(dy) <= 44.0 and abs(dx) <= 44.0:
            if abs(dx) <= 10.0:
                climb_frames = max(6, min(40, int(round(abs(dy) / 1.1))))
                _append_frames(ops, climb_frames, (*horiz, "U", "G"))
            else:
                jump_frames = max(8, min(14, int(round(max(abs(dy) * 0.28, 9)))))
                _append_frames(ops, jump_frames, (*horiz, "J"))
                coast_frames = max(2, int(round(abs(dx) / 1.6)) - jump_frames)
                if coast_frames > 0 and horiz:
                    _append_frames(ops, coast_frames, horiz)
            continue

        # 2. Vão longo horizontal ou escalada/salto alto que exige o 1 dash único
        if dy < -44.0 or abs(dx) > 44.0:
            if dy <= 6.0:
                jump_frames = 10
                _append_frames(ops, jump_frames, (*horiz, "J"))
            dash_dirs: list[str] = []
            if horiz:
                dash_dirs.append(horiz[0])
            if dy < -10.0:
                dash_dirs.append("U")
            elif dy > 16.0:
                dash_dirs.append("D")
            if not dash_dirs:
                dash_dirs.append("R")
            _append_frames(ops, 9, tuple([*dash_dirs, "X"]))
            rem_walk = max(0, int(round((dist - 48.0) / 1.55)))
            if rem_walk > 0 and horiz:
                _append_frames(ops, min(45, rem_walk), horiz)
            continue

        # 3. Queda controlada ou desnível para baixo
        if dy > 8.0:
            fall_frames = max(4, min(36, int(round(dist / 2.2))))
            _append_frames(ops, fall_frames, horiz)
            continue

        # 4. Caminhada/corrida horizontal sobre piso ou plataforma
        walk_frames = max(2, min(90, int(round(abs(dx) / 1.5))))
        _append_frames(ops, walk_frames, horiz)

    return ops


def _format_tas_line(frames: int, tokens: tuple[str, ...]) -> str:
    if not tokens:
        return f"{frames:4d}"
    return f"{frames:4d}," + ",".join(tokens)


def validate_celestetas_script(content: str) -> tuple[bool, list[str], int]:
    """Valida estritamente a sintaxe CelesteTAS de um arquivo `.tas` gerado."""
    errors: list[str] = []
    total_frames = 0
    seen_load = False
    seen_room_label = False

    for lineno, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#lvl_"):
            seen_room_label = True
            continue
        if line.startswith("#") or line.startswith("***"):
            continue
        if line in {"Unsafe", "Safe"} or line.startswith(("RecordCount:", "Set,", "Read,", "Play,", "AnalogMode,")):
            continue
        if line.startswith("console "):
            if line.startswith("console load "):
                seen_load = True
            continue
        m = TAS_INPUT_LINE_RE.match(raw)
        if not m:
            errors.append(f"Linha {lineno} inválida para CelesteTAS: {line!r}")
            continue
        total_frames += int(m.group(1))

    if not seen_load:
        errors.append("Script sem comando inicial 'console load'.")
    if not seen_room_label:
        errors.append("Script sem rótulos '#lvl_<sala>'.")
    if total_frames <= 0:
        errors.append("Script com zero quadros de execução.")
    return len(errors) == 0, errors, total_frames


def generate_chapter_tas(
    chapter: str,
    algo: str = "stratgraph",
    alpha: float = 0.05,
    out_dir: Path = TAS_DIR,
) -> TasChapterReport:
    """Gera o arquivo `.tas` (60 FPS) para um capítulo do Celeste e algoritmo (`stratgraph` ou `bfs`)."""
    ds_dir = ROOT / "datasets" / "celeste" / chapter
    area_id = CHAPTER_AREA_IDS[chapter]

    graph = load_graph_from_csv(ds_dir)
    con_g = contract_dead_ends(graph)
    layered = build_layered_graph(con_g, alpha=alpha)

    res = run_dijkstra(layered) if algo == "stratgraph" else run_bfs(layered)
    wpts_payload = json.loads((ds_dir / "waypoints.json").read_text(encoding="utf-8"))
    rooms_meta = wpts_payload.get("rooms", {})
    edges_wpts = wpts_payload.get("edges", {})

    algo_label = "StratGraph (Dijkstra L0->L1 + Contracao)" if algo == "stratgraph" else "BFS (Baseline L0 + Contracao)"
    lines: list[str] = [
        f"# StratGraph -> CelesteTAS (All Collectibles - 100%, alpha={alpha:.2f})",
        f"# Capitulo: {chapter} (Area ID: {area_id}) | Algoritmo: {algo_label}",
        f"# Custo Real: {res.real_cost:.2f} | Custo Efetivo: {res.effective_cost:.2f} | "
        f"Coletaveis: {res.collectibles_count} | Passou por ARMA: {'SIM' if res.used_weapon else 'NAO'}",
        "#",
        "# Nota: Como o StratGraph modela desvios em grafo (ARMA + becos contraidos),",
        "# cada sala e ancorada via `#lvl_<sala>` e `console load` (requer `Unsafe`) para",
        "# execucao reprodutivel por segmento no CelesteTAS Studio / Everest.",
        "",
        "RecordCount: 1",
        "Unsafe",
        "Set, CelesteTAS.SimplifiedGraphics, true",
        "",
    ]

    room_seq = [n.room_id for n in res.path]
    layer_seq = [n.layer for n in res.path]
    weapon_room = next((nid for nid, v in graph.vertices.items() if v.has_weapon), None)
    armed = False
    total_frames = 0
    prev_room: str | None = None

    for idx, room_id in enumerate(room_seq):
        short_room = room_id[4:] if room_id.startswith("lvl_") else room_id
        layer_id = layer_seq[idx] if idx < len(layer_seq) else 0
        if room_id == weapon_room or layer_id == 1:
            armed = True

        node = graph.vertices.get(room_id)
        node_val = node.collectible_value if node else 0.0
        contracted_children = con_g.contracted_into.get(room_id, [])

        lines.append(f"#lvl_{short_room}")
        lines.append(
            f"# [Passo {idx + 1}/{len(room_seq)}] Sala: {room_id} | Camada: L{layer_id} | "
            f"Valor Sala: {node_val:.1f} | Arma Ativa: {'SIM' if armed else 'NAO'}"
        )

        # Se for a sala inicial ou um salto entre ramos reordenados sem transição contígua, ancora com console load
        seg_key = f"{prev_room}->{room_id}" if prev_room else ""
        if prev_room is None or seg_key not in edges_wpts:
            lines.append(f"console load {area_id} {short_room}")
            lines.append(_format_tas_line(18, ()))
            total_frames += 18

        if seg_key and seg_key in edges_wpts:
            seg_ops = _waypoints_to_tas_frames(edges_wpts[seg_key])
            if not seg_ops:
                seg_ops = [(12, ("R",))]
            for n_fr, toks in seg_ops:
                lines.append(_format_tas_line(n_fr, toks))
                total_frames += n_fr

        # Becos contraídos conectados diretamente a esta sala: excursionar até o morango e retornar
        for child_id in contracted_children:
            c_node = graph.vertices.get(child_id)
            c_val = c_node.collectible_value if c_node else 0.0
            c_short = child_id[4:] if child_id.startswith("lvl_") else child_id
            lines.append(f"# [Beco Contraido -> Coletar {child_id} (+{c_val:.1f}) e retornar a {room_id}]")
            lines.append(f"#lvl_{c_short}")
            go_key = f"{room_id}->{child_id}"
            back_key = f"{child_id}->{room_id}"
            if go_key in edges_wpts:
                for n_fr, toks in _waypoints_to_tas_frames(edges_wpts[go_key]):
                    lines.append(_format_tas_line(n_fr, toks))
                    total_frames += n_fr
            else:
                lines.append(f"console load {area_id} {c_short}")
                lines.append(_format_tas_line(24, ("R", "J")))
                total_frames += 24
            if back_key in edges_wpts:
                for n_fr, toks in _waypoints_to_tas_frames(edges_wpts[back_key]):
                    lines.append(_format_tas_line(n_fr, toks))
                    total_frames += n_fr
            else:
                lines.append(f"console load {area_id} {short_room}")
                lines.append(_format_tas_line(12, ()))
                total_frames += 12

        # Garante ao menos um pequeno avanço na última sala (`FIM`) se sem transição posterior
        if prev_room is None and len(room_seq) == 1:
            anchor = rooms_meta.get(room_id, {}).get("anchor")
            if anchor:
                lines.append(_format_tas_line(20, ("R",)))
                total_frames += 20

        lines.append("")
        prev_room = room_id

    lines.append(f"# FIM DA ROTA: {chapter} | Total de quadros estimados (60 FPS): {total_frames}")
    content = "\n".join(lines) + "\n"

    ok, errs, parsed_frames = validate_celestetas_script(content)
    if not ok:
        raise ValueError(f"Falha de sintaxe CelesteTAS em {chapter}/{algo}: {errs}")

    out_dir.mkdir(parents=True, exist_ok=True)
    tas_file = out_dir / f"{chapter}_{algo}.tas"
    tas_file.write_text(content, encoding="utf-8")

    return TasChapterReport(
        chapter=chapter,
        area_id=area_id,
        algo_name=algo,
        tas_path=tas_file,
        total_frames=parsed_frames,
        duration_s=round(parsed_frames / 60.0, 2),
        rooms_visited=len(room_seq),
        collectibles=res.collectibles_count,
        real_cost=round(res.real_cost, 2),
        eff_cost=round(res.effective_cost, 2),
        used_weapon=res.used_weapon,
    )


def export_all_chapters(alpha: float = 0.05, out_dir: Path = TAS_DIR) -> list[TasChapterReport]:
    """Exporta arquivos `.tas` (StratGraph e BFS) para todos os 8 capítulos de Celeste e gera índice."""
    reports: list[TasChapterReport] = []
    for chapter, _bin_name in CHAPTER_FILES:
        rep_bfs = generate_chapter_tas(chapter, algo="bfs", alpha=alpha, out_dir=out_dir)
        rep_sg = generate_chapter_tas(chapter, algo="stratgraph", alpha=alpha, out_dir=out_dir)
        reports.extend([rep_bfs, rep_sg])

    readme_lines = [
        "# Scripts CelesteTAS Exportados pelo StratGraph (Opção 2)",
        "",
        "Scripts 60 FPS compatíveis com **CelesteTAS v3.47+ (Everest / Celeste Studio)** gerados",
        "diretamente das rotas resolvidas em `src/` para **StratGraph ($L_0 \\to L_1$)** e **BFS ($L_0$)**.",
        "",
        "## Como Executar no CelesteTAS (Everest)",
        "",
        "1. Garanta que o **Everest** e o mod **CelesteTAS** estejam ativos na instalação do *Celeste*.",
        "2. Abra qualquer arquivo `.tas` abaixo (por exemplo `1_forsaken_city_stratgraph.tas`) no **Celeste Studio**",
        "   ou copie o conteúdo para o arquivo ativo do CelesteTAS e pressione o atalho de reprodução (`RightControl`).",
        "3. Pressione o atalho de salto de capítulo/debug caso queira inspecionar qualquer bloco `#lvl_<sala>` individual.",
        "",
        "## Separação: Exportações *Offline* vs. Artefato Validado Ao Vivo",
        "",
        "* **Arquivos `*_{bfs,stratgraph}.tas` (abaixo):** exportações determinísticas e 100% *offline* a partir dos grafos CSV e `waypoints.json` (`python -m scripts.export_celeste_tas`).",
        "* **Capítulo 1 ao vivo (`1_forsaken_city_live.tas`):** síntese em malha fechada contra o *Celeste* + DebugRC (`python -m scripts.solve_live_celeste_tas --chapter 1_forsaken_city`), preservada em arquivo separado e sumarizada em `results/live_celeste_ch1_validation.json`.",
        "",
        "## Comparativo dos Arquivos Exportados *Offline* (`alpha = 0.05`, 100% Coleta)",
        "",
        "| Capítulo | Algoritmo | Salas | Itens | Custo Efetivo | Quadros TAS (60 FPS) | Duração Est. | Arquivo |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for r in reports:
        readme_lines.append(
            f"| `{r.chapter}` | {r.algo_name} | {r.rooms_visited} | {r.collectibles} | "
            f"{r.eff_cost:.2f} | {r.total_frames} | {r.duration_s:.2f} s | [`{r.tas_path.name}`]({r.tas_path.name}) |"
        )
    readme_lines.append("")
    (out_dir / "README_CELESTETAS.md").write_text("\n".join(readme_lines), encoding="utf-8")
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera arquivos `.tas` (60 FPS) compatíveis com CelesteTAS para todos os capítulos."
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="Fator de coleta alpha.")
    parser.add_argument("--out-dir", type=Path, default=TAS_DIR, help="Diretório de saída dos `.tas`.")
    args = parser.parse_args()

    reports = export_all_chapters(alpha=args.alpha, out_dir=args.out_dir)
    for r in reports:
        print(
            f"[CelesteTAS] {r.chapter:20s} | {r.algo_name:10s} | itens={r.collectibles:2d} | "
            f"eff={r.eff_cost:7.2f} | frames={r.total_frames:5d} ({r.duration_s:6.2f}s) -> {r.tas_path.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
