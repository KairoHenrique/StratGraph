# Arquitetura e Modelagem Matemática

## 1. Abstração do Mapa como Dígrafo Ponderado

O mapa de um nível é modelado como um dígrafo ponderado $G = (V, E, w)$:

* **Vértices ($V$):** salas, trechos ou plataformas seguras (`INICIO`, `COMUM`, `COLETAVEL`, `ARMA`, `FIM`).
* **Arestas ($E$):** transições direcionadas entre salas. Conexões unidirecionais (quedas, travas) geram apenas $(u, v)$; conexões bidirecionais (`mao_dupla = 1`) geram $(u, v)$ e $(v, u)$.

## 2. Pré-processamento: Contração de Becos sem Saída

Salas `COLETAVEL` sem arma cuja única conexão ocorre com uma sala adjacente $B$ (com ida e volta válidas) podem ser contraídas em $B$ na etapa de pré-processamento, somando o custo de ida e volta e transferindo o coletável. O CLI mantém a opção `--no-contract` para análise comparativa (estudo de ablação) nos experimentos.

## 3. Grafo Expandido em Camadas (Estado de Arma / *Power-up*)

Para modelar a redução permanente de dificuldade após obter uma arma ou *power-up* sem alterar pesos dinamicamente durante a busca, cada vértice $u \in V$ é duplicado em dois estados:

* $(u, 0)$ — camada **Sem Arma** (usa `dificuldade_sem_arma`).
* $(u, 1)$ — camada **Com Arma** (usa `dificuldade_com_arma`).

Em toda sala $u_{\text{arma}}$ com `possui_arma = 1`, adiciona-se uma aresta direcionada $(u_{\text{arma}}, 0) \to (u_{\text{arma}}, 1)$ de custo real zero.

## 4. Equação de Custo Efetivo Positivo

Para incentivar desvios estratégicos em direção a coletáveis mantendo $w > 0$ (condição necessária para Dijkstra sem ciclos negativos), o peso efetivo de $(u, v)$ na camada $k \in \{0, 1\}$ é:

$$w(u, v, k) = \frac{\text{TempoBase}(u, v) + \text{Dificuldade}(u, v, k)}{1 + \alpha \cdot \text{ValorColetavel}(v)}, \quad \alpha > 0$$

Na contabilização final das métricas, os itens coletados são computados por conjunto único de `id_sala`, evitando dupla contagem caso uma sala seja atravessada nas camadas `0` e `1`.

## 5. Algoritmos Comparados

1. **BFS ($O(V + E)$):** *baseline* não ponderado que minimiza o número de transições até `FIM`.
2. **DFS *Branch-and-Bound*:** busca exata que rastreia o conjunto de coletáveis já obtidos ao longo do caminho, servindo de referência de ótimo global e evidenciando o gargalo exponencial em mapas grandes.
3. **Dijkstra no Grafo em Camadas ($O((V + E)\log V)$):** solução principal baseada em fila de prioridade (*Min-Heap*), escalável para mapas extensos.

