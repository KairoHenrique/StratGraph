"""Testes unitários e de integração do pipeline StratGraph."""

from pathlib import Path
import pytest

from src.algorithms import run_bfs, run_dfs_branch_and_bound, run_dijkstra
from src.layered_graph import build_layered_graph, compute_effective_weight
from src.loader import load_graph_from_csv
from src.main import main
from src.models import RoomType, Vertex
from src.preprocessing import contract_dead_ends


def test_base_structure_imports() -> None:
    """Garante que os modelos base e o dataset de exemplo existem e importam."""
    v = Vertex(room_id="S0", room_type=RoomType.INICIO)
    assert v.room_id == "S0"
    assert Path("datasets/sample_toy/vertices.csv").exists()
    assert Path("datasets/sample_toy/arestas.csv").exists()


def test_loader_and_dead_end_contraction() -> None:
    """Verifica leitura do CSV e fusão correta do beco sem saída S2 na sala S1."""
    raw = load_graph_from_csv("datasets/sample_toy")
    assert len(raw.vertices) == 6
    assert raw.start_id == "S0"
    assert raw.goal_id == "S5"
    assert raw.original_collectibles == {"S2": 5.0}

    contracted = contract_dead_ends(raw)
    assert len(contracted.vertices) == 5
    assert "S2" not in contracted.vertices
    assert contracted.vertices["S1"].collectible_value == pytest.approx(5.0)
    assert contracted.contracted_into.get("S1") == ["S2"]


def test_effective_weight_strictly_positive() -> None:
    """Garante que o peso efetivo é estritamente positivo e reduz com coletáveis."""
    w_no_item = compute_effective_weight(base_time=10.0, difficulty=2.0, collectible_value=0.0, alpha=0.5)
    w_with_item = compute_effective_weight(base_time=10.0, difficulty=2.0, collectible_value=4.0, alpha=0.5)
    assert w_no_item == pytest.approx(12.0)
    assert w_with_item == pytest.approx(4.0)
    assert 0.0 < w_with_item < w_no_item


def test_algorithms_on_sample_toy() -> None:
    """Valida que BFS ignora pesos/arma enquanto Dijkstra e B&B pegam a arma S3 e o item S2."""
    raw = load_graph_from_csv("datasets/sample_toy")
    contracted = contract_dead_ends(raw)
    layered = build_layered_graph(contracted, alpha=0.5)

    bfs_res = run_bfs(layered)
    bnb_res = run_dfs_branch_and_bound(layered, alpha=0.5)
    dijkstra_res = run_dijkstra(layered)

    assert bfs_res.found
    assert bnb_res.found
    assert dijkstra_res.found

    # BFS escolhe S0 -> S1 -> S4 -> S5 (sem arma, custo real alto = 64.0)
    assert not bfs_res.used_weapon
    assert bfs_res.real_cost == pytest.approx(64.0)

    # Dijkstra e Branch-and-Bound desviam por S3 (ARMA), mudam para camada 1
    # e concluem com custo real muito menor (30.0) e coletável S2 capturado.
    assert dijkstra_res.used_weapon
    assert dijkstra_res.real_cost == pytest.approx(30.0)
    assert dijkstra_res.effective_cost == pytest.approx(bnb_res.effective_cost)
    assert dijkstra_res.collected_room_ids == {"S2"}
    assert dijkstra_res.collectibles_count == 1
    assert dijkstra_res.collectibles_total_value == pytest.approx(5.0)


def test_no_double_counting_across_layers(tmp_path: Path) -> None:
    """Garante que atravessar a mesma sala com coletável nas camadas 0 e 1 não duplica o item."""
    v_csv = tmp_path / "vertices.csv"
    e_csv = tmp_path / "arestas.csv"

    v_csv.write_text(
        "id_sala,tipo_sala,valor_coletavel,possui_arma\n"
        "A,INICIO,0,0\n"
        "B,COLETAVEL,10,0\n"
        "C,ARMA,0,1\n"
        "D,FIM,0,0\n",
        encoding="utf-8",
    )
    # Único caminho para C (arma) passa por B e depois precisa voltar por B até D
    e_csv.write_text(
        "origem,destino,mao_dupla,tempo_base,dificuldade_sem_arma,dificuldade_com_arma\n"
        "A,B,1,2,0,0\n"
        "B,C,1,2,0,0\n"
        "B,D,0,2,50,1\n",
        encoding="utf-8",
    )

    raw = load_graph_from_csv(tmp_path)
    layered = build_layered_graph(raw, alpha=0.5)

    dijkstra_res = run_dijkstra(layered)
    bnb_res = run_dfs_branch_and_bound(layered, alpha=0.5)

    assert dijkstra_res.found
    assert bnb_res.found
    assert dijkstra_res.used_weapon
    # Mesmo passando por (B, 0) na ida para C e por (B, 1) na volta para D,
    # o coletável B deve ser contabilizado apenas 1 única vez.
    assert dijkstra_res.collectibles_count == 1
    assert dijkstra_res.collectibles_total_value == pytest.approx(10.0)
    assert bnb_res.collectibles_count == 1
    assert bnb_res.collectibles_total_value == pytest.approx(10.0)


def test_cli_execution_and_export(tmp_path: Path) -> None:
    """Testa a execução completa do CLI e exportação CSV/JSON."""
    out_csv = tmp_path / "out.csv"
    out_json = tmp_path / "out.json"
    exit_code = main(
        [
            "--dataset",
            "datasets/sample_toy",
            "--alpha",
            "0.5",
            "--output-csv",
            str(out_csv),
            "--output-json",
            str(out_json),
        ]
    )
    assert exit_code == 0
    assert out_csv.is_file()
    assert out_json.is_file()


def test_all_extracted_celeste_chapters() -> None:
    """Verifica que todos os 8 capítulos extraídos de Celeste executam e usam a camada armada."""
    celeste_dir = Path("datasets/celeste")
    chapters = sorted([d for d in celeste_dir.iterdir() if d.is_dir()])
    assert len(chapters) == 8

    for ch_dir in chapters:
        raw = load_graph_from_csv(ch_dir)
        contracted = contract_dead_ends(raw)
        layered = build_layered_graph(contracted, alpha=0.05)

        bfs_res = run_bfs(layered)
        dijkstra_res = run_dijkstra(layered)

        assert bfs_res.found, f"BFS falhou em {ch_dir.name}"
        assert dijkstra_res.found, f"Dijkstra falhou em {ch_dir.name}"
        assert dijkstra_res.used_weapon, f"Dijkstra não desviou para a arma em {ch_dir.name}"
        assert dijkstra_res.effective_cost < bfs_res.effective_cost
        assert dijkstra_res.real_cost < bfs_res.real_cost
        assert bfs_res.collectibles_count == len(raw.original_collectibles)
        assert dijkstra_res.collectibles_count == len(raw.original_collectibles)


def test_all_extracted_cuphead_levels() -> None:
    """Verifica que todas as 6 fases Run-and-Gun extraídas de Cuphead executam e usam a camada armada."""
    cuphead_dir = Path("datasets/cuphead")
    levels = sorted([d for d in cuphead_dir.iterdir() if d.is_dir()])
    assert len(levels) == 6

    for lv_dir in levels:
        raw = load_graph_from_csv(lv_dir)
        contracted = contract_dead_ends(raw)
        layered = build_layered_graph(contracted, alpha=0.05)

        bfs_res = run_bfs(layered)
        dijkstra_res = run_dijkstra(layered)

        assert bfs_res.found, f"BFS falhou em {lv_dir.name}"
        assert dijkstra_res.found, f"Dijkstra falhou em {lv_dir.name}"
        assert dijkstra_res.used_weapon, f"Dijkstra não usou arma em {lv_dir.name}"
        assert dijkstra_res.effective_cost < bfs_res.effective_cost
        assert bfs_res.collectibles_count == len(raw.original_collectibles)
        assert dijkstra_res.collectibles_count == len(raw.original_collectibles)


def test_synthetic_scalability_benchmarks() -> None:
    """Verifica que os 7 grafos sintéticos de escalabilidade (V=15..5000) executam corretamente."""
    syn_dir = Path("datasets/synthetic")
    instances = sorted([d for d in syn_dir.iterdir() if d.is_dir()])
    assert len(instances) == 7

    for inst_dir in instances:
        raw = load_graph_from_csv(inst_dir)
        contracted = contract_dead_ends(raw)
        assert len(contracted.vertices) < len(raw.vertices)
        layered = build_layered_graph(contracted, alpha=0.05)
        dijkstra_res = run_dijkstra(layered)
        assert dijkstra_res.found
        assert dijkstra_res.used_weapon


def test_results_and_figures_exist() -> None:
    """Garante que o resumo experimental, sensibilidade e todas as figuras do artigo IEEE foram gerados."""
    assert Path("results/benchmark_summary.csv").is_file()
    assert Path("results/benchmark_summary.json").is_file()
    assert Path("results/alpha_sensitivity.csv").is_file()
    assert Path("results/alpha_sensitivity.json").is_file()
    for fig_name in (
        "fluxograma_proposta",
        "comparacao_custos",
        "escalabilidade_tempo",
        "contracao_becos",
        "sensibilidade_alpha",
    ):
        assert Path(f"article/figures/{fig_name}.pdf").is_file()
        assert Path(f"article/figures/{fig_name}.png").is_file()


def test_simulator_and_mods_export() -> None:
    """Verifica a geração do Simulador 2D TAS e das rotas/DLLs dos Mods In-Game."""
    import json

    from scripts.build_mods import export_mod_routes_json
    from scripts.simulate_route import generate_simulator_html

    sim_html = generate_simulator_html()
    assert sim_html.is_file()
    assert sim_html.stat().st_size > 100_000

    routes_json = export_mod_routes_json()
    assert routes_json.is_file()
    data = json.loads(routes_json.read_text(encoding="utf-8"))
    assert "celeste_1_forsaken_city" in data
    assert "cuphead_1_1f_forest_follies" in data
    assert len(data["celeste_1_forsaken_city"]["tas_waypoints_flat"]) > 50
    assert len(data["cuphead_1_1f_forest_follies"]["tas_waypoints_flat"]) > 50


def test_celeste_tas_export(tmp_path: Path) -> None:
    """Valida a exportação e sintaxe CelesteTAS (60 FPS, 100% coleta) nos 8 capítulos."""
    from scripts.export_celeste_tas import export_all_chapters, validate_celestetas_script

    reports = export_all_chapters(alpha=0.05, out_dir=tmp_path)
    assert len(reports) == 16  # 8 capítulos x {bfs, stratgraph}
    assert (tmp_path / "README_CELESTETAS.md").is_file()

    by_chapter: dict[str, dict[str, object]] = {}
    for rep in reports:
        assert rep.tas_path.is_file()
        content = rep.tas_path.read_text(encoding="utf-8")
        ok, errs, parsed_frames = validate_celestetas_script(content)
        assert ok, f"Erros TAS em {rep.tas_path.name}: {errs}"
        assert parsed_frames == rep.total_frames
        assert parsed_frames > 0
        raw = load_graph_from_csv(Path("datasets/celeste") / rep.chapter)
        assert rep.collectibles == len(raw.original_collectibles)
        by_chapter.setdefault(rep.chapter, {})[rep.algo_name] = rep

    for chapter, pair in by_chapter.items():
        bfs_rep = pair["bfs"]
        sg_rep = pair["stratgraph"]
        assert sg_rep.used_weapon, f"{chapter} StratGraph TAS não ativou ARMA"
        assert sg_rep.eff_cost < bfs_rep.eff_cost, f"{chapter} StratGraph não reduziu custo efetivo"


