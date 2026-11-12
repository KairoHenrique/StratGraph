# Scripts CelesteTAS Exportados pelo StratGraph (Opção 2)

Scripts 60 FPS compatíveis com **CelesteTAS v3.47+ (Everest / Celeste Studio)** gerados
diretamente das rotas resolvidas em `src/` para **StratGraph ($L_0 \to L_1$)** e **BFS ($L_0$)**.

## Como Executar no CelesteTAS (Everest)

1. Garanta que o **Everest** e o mod **CelesteTAS** estejam ativos na instalação do *Celeste*.
2. Abra qualquer arquivo `.tas` abaixo (por exemplo `1_forsaken_city_stratgraph.tas`) no **Celeste Studio**
   ou copie o conteúdo para o arquivo ativo do CelesteTAS e pressione o atalho de reprodução (`RightControl`).
3. Pressione o atalho de salto de capítulo/debug caso queira inspecionar qualquer bloco `#lvl_<sala>` individual.

## Comparativo dos Arquivos Gerados (`alpha = 0.05`, 100% Coleta)

| Capítulo | Algoritmo | Salas | Itens | Custo Efetivo | Quadros TAS (60 FPS) | Duração Est. | Arquivo |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `1_forsaken_city` | bfs | 20 | 21 | 533.11 | 10306 | 171.77 s | [`1_forsaken_city_bfs.tas`](1_forsaken_city_bfs.tas) |
| `1_forsaken_city` | stratgraph | 22 | 21 | 466.51 | 10456 | 174.27 s | [`1_forsaken_city_stratgraph.tas`](1_forsaken_city_stratgraph.tas) |
| `2_old_site` | bfs | 8 | 18 | 845.38 | 5269 | 87.82 s | [`2_old_site_bfs.tas`](2_old_site_bfs.tas) |
| `2_old_site` | stratgraph | 10 | 18 | 472.96 | 5371 | 89.52 s | [`2_old_site_stratgraph.tas`](2_old_site_stratgraph.tas) |
| `3_celestial_resort` | bfs | 22 | 24 | 989.27 | 10642 | 177.37 s | [`3_celestial_resort_bfs.tas`](3_celestial_resort_bfs.tas) |
| `3_celestial_resort` | stratgraph | 24 | 24 | 545.49 | 10464 | 174.40 s | [`3_celestial_resort_stratgraph.tas`](3_celestial_resort_stratgraph.tas) |
| `4_golden_ridge` | bfs | 34 | 29 | 936.94 | 19789 | 329.82 s | [`4_golden_ridge_bfs.tas`](4_golden_ridge_bfs.tas) |
| `4_golden_ridge` | stratgraph | 36 | 29 | 557.80 | 19840 | 330.67 s | [`4_golden_ridge_stratgraph.tas`](4_golden_ridge_stratgraph.tas) |
| `5_mirror_temple` | bfs | 14 | 22 | 742.08 | 12260 | 204.33 s | [`5_mirror_temple_bfs.tas`](5_mirror_temple_bfs.tas) |
| `5_mirror_temple` | stratgraph | 16 | 22 | 442.91 | 12104 | 201.73 s | [`5_mirror_temple_stratgraph.tas`](5_mirror_temple_stratgraph.tas) |
| `6_reflection` | bfs | 47 | 2 | 882.59 | 14910 | 248.50 s | [`6_reflection_bfs.tas`](6_reflection_bfs.tas) |
| `6_reflection` | stratgraph | 49 | 2 | 419.39 | 15007 | 250.12 s | [`6_reflection_stratgraph.tas`](6_reflection_stratgraph.tas) |
| `7_summit` | bfs | 62 | 41 | 2395.30 | 36047 | 600.78 s | [`7_summit_bfs.tas`](7_summit_bfs.tas) |
| `7_summit` | stratgraph | 64 | 41 | 1229.26 | 36320 | 605.33 s | [`7_summit_stratgraph.tas`](7_summit_stratgraph.tas) |
| `9_core` | bfs | 29 | 7 | 651.12 | 12346 | 205.77 s | [`9_core_bfs.tas`](9_core_bfs.tas) |
| `9_core` | stratgraph | 31 | 7 | 343.94 | 12389 | 206.48 s | [`9_core_stratgraph.tas`](9_core_stratgraph.tas) |
