# Arquitetura e Modelagem Matemática

## 1. Abstração do Mapa e Pathfinding Físico Intra-Sala

O mapa de um nível é modelado como um dígrafo ponderado $G = (V, E, w)$:

* **Vértices ($V$):** salas, setores ou plataformas seguras (`INICIO`, `COMUM`, `COLETAVEL`, `ARMA`, `FIM`).
* **Arestas ($E$) e Trajetórias Físicas (*Waypoints*):** transições direcionadas entre salas adjacentes. Em vez de estimativas abstratas em linha reta, os extratores oficiais ([`extract_celeste_maps.py`](../scripts/extract_celeste_maps.py) e [`extract_cuphead_maps.py`](../scripts/extract_cuphead_maps.py)) simulam o deslocamento físico real do jogador dentro de cada sala/setor:
  * Em ***Celeste***, um algoritmo $A^*$ percorre o grid de colisão de 8×8 pixels (`<solids>`) desde a abertura da porta de entrada, utilizando plataformas (`jumpThru`), molas (`spring`) e impulsos (`booster`, `zipMover`, `swapBlock`), passando pelas coordenadas exatas dos coletáveis (`strawberry`, `cassette`, `blackGem`) até a porta de saída;
  * Em ***Cuphead***, constrói-se a cadeia física de saltos entre plataformas jogáveis e moedas douradas (`Level_Coin`), avaliando a distância percorrida em pixels e a proximidade real dos *spawners* de inimigos no corredor do salto.

## 2. Pré-processamento: Contração de Becos sem Saída e Comparação Justa

Salas `COLETAVEL` sem arma cuja única conexão ocorre com uma sala adjacente $B$ (`mao_dupla = 1`) são contraídas em $B$ na etapa de pré-processamento ([`contract_dead_ends`](../src/preprocessing.py)), somando o custo físico de ida e volta $(B \to C \to B)$ às arestas de entrada de $B$, transferindo o valor do coletável e registrando auditoria em `contracted_into[B]`.

Isso cumpre dois objetivos fundamentais:
1. **Redução topológica ($|V| \to |V'|$):** poda até 26,7% dos vértices antes da expansão em camadas;
2. **Comparação justa de coleta entre algoritmos:** como as alcovas contraídas ficam integradas aos vértices de passagem, tanto o **BFS** quanto o **DFS *Branch-and-Bound*** e o **Dijkstra em Camadas** entram fisicamente nas alcovas e coletam os mesmos itens (ao contrário da execução sem contração `--no-contract`, que ignora becos sem saída).

## 3. Grafo Expandido em Camadas (Estado de Arma / *Power-up*)

Para modelar a redução permanente de dificuldade após obter uma arma ou *power-up* sem alterar pesos dinamicamente durante a busca, cada vértice $u \in V'$ é duplicado em dois estados:

* $(u, 0)$ — camada **Sem Arma ($L_0$)** (usa `dificuldade_sem_arma`).
* $(u, 1)$ — camada **Com Arma ($L_1$)** (usa `dificuldade_com_arma`).

Em toda sala $u_{\text{arma}}$ com `possui_arma = 1`, adiciona-se uma aresta direcionada $(u_{\text{arma}}, 0) \to (u_{\text{arma}}, 1)$ de custo real zero.

## 4. Equação de Custo Efetivo Positivo

Para incentivar desvios estratégicos em direção a coletáveis mantendo $w > 0$ (condição necessária para otimalidade global de Dijkstra), o peso efetivo de $(u, v)$ na camada $k \in \{0, 1\}$ é:

$$w(u, v, k) = \frac{\text{TempoBase}(u, v) + \text{Dificuldade}(u, v, k)}{1 + \alpha \cdot \text{ValorColetavel}(v)}, \quad \alpha > 0$$

Na contabilização final das métricas, os itens coletados são computados por conjunto único de `id_sala`, evitando dupla contagem caso uma sala seja atravessada nas camadas `0` e `1`.

## 5. Algoritmos Comparados e Execução TAS

1. **BFS ($O(V + E)$):** *baseline* em $L_0$ que minimiza o número de transições até `FIM` coletando os becos contraídos do caminho, mas sem realizar desvios estratégicos até a sala `ARMA`.
2. **DFS *Branch-and-Bound*:** busca exata em profundidade com poda por limite superior (*upper bound*), servindo de validação cruzada de otimalidade em grafos pequenos/médios e demonstrando a explosão combinatória em grafos grandes.
3. **Dijkstra no Grafo em Camadas ($O((V + E)\log V)$):** solução principal baseada em fila de prioridade (*Min-Heap*), que identifica o desvio ótimo para a camada armada ($L_0 \to L_1$) e exporta a sequência de *waypoints* físicos para o **Simulador Visual 2D** ([`scripts/simulate_route.py`](../scripts/simulate_route.py)) e para os **Mods *In-Game* com Bot TAS** ([`mods/`](../mods/README_MODS.md)).
