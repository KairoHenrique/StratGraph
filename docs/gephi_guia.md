# Guia de Visualização no Gephi (.gexf) — StratGraph

Este guia orienta alunos, pesquisadores e a banca avaliadora sobre como abrir, visualizar e explorar os grafos gerados pelo **StratGraph** no [Gephi](https://gephi.org/) (versões 0.9.x e 0.10.x).

O **StratGraph** é totalmente **agnóstico ao jogo e à engine**: qualquer mapa modelado no esquema padrão (`vertices.csv` e `arestas.csv` dentro de `datasets/`) é processado exatamente pelo mesmo código e exportado automaticamente para o formato universal `.gexf`.

---

## 1. O Que Foi Gerado?

Para cada instância presente em `datasets/` (instâncias didáticas, benchmarks sintéticos ou datasets de fases extraídas), o StratGraph exporta automaticamente um **trio de arquivos GEXF 1.2** em `results/gephi/<dataset>/`:

1. **`<dataset>_base.gexf` (Grafo Topológico Original):**
   - Dígrafo ponderado com os vértices (salas/setores) e arestas originais da instância.
   - Coordenadas 2D calculadas automaticamente a partir da topologia do grafo (camadas de profundidade BFS entre `INICIO` e `FIM` com ordenação baricêntrica para minimizar cruzamentos; ou leitura opcional de `positions.csv`, caso exista na pasta do dataset).
   - Cores padronizadas pelo papel funcional de cada vértice (`INICIO`, `FIM`, `ARMA`, `COLETAVEL`, `COMUM`).

2. **`<dataset>_optimal_route.gexf` (Rota Ótima Destacada):**
   - O grafo base com o caminho ótimo calculado pelo algoritmo **Dijkstra em Camadas** do StratGraph destacado.
   - As arestas pertencentes à rota ótima possuem espessura aumentada (`thickness=4.0` ou `5.0`), opacidade total e cor **Laranja Cenoura**, enquanto as arestas secundárias ficam atenuadas e translúcidas (`opacity=0.3`).
   - Vértices visitados pela rota ótima possuem atributo booleano `na_rota_otima = true`.

3. **`<dataset>_layered.gexf` (Grafo em Camadas L0 e L1):**
   - Representação visual do espaço de estados expandido $V \times \{0, 1\}$.
   - **Camada 0 ($L_0$):** Estado base sem recurso permanente / *power-up* (nós em azul escuro, $z = 0$).
   - **Camada 1 ($L_1$):** Estado após aquisição da arma / *power-up* (nós em âmbar/dourado, $z = 150$, com deslocamento no eixo Y).
   - **Transições Intercamadas:** Arestas douradas com espessura destacada que conectam o vértice `ARMA` de $L_0$ para os seus destinos na camada $L_1$.

---

## 2. Paleta de Cores Padronizada

Os nós e arestas já contêm atributos visuais RGB nativos (`xmlns:viz="http://www.gexf.net/1.2draft/viz"`):

| Elemento / Tipo | Cor | Código RGB | Significado no Modelo |
| :--- | :--- | :--- | :--- |
| **INICIO** | Verde Esmeralda | `rgb(46, 204, 113)` | Vértice inicial da instância |
| **FIM** | Vermelho Alizarin | `rgb(231, 76, 60)` | Vértice de destino / objetivo final |
| **ARMA** | Dourado / Amarelo | `rgb(241, 196, 15)` | Vértice que habilita a transição de estado $L_0 \to L_1$ |
| **COLETAVEL** | Roxo Ametista | `rgb(155, 89, 182)` | Vértice com item bônus ponderado pelo parâmetro $\alpha$ |
| **COMUM** | Azul Peter River | `rgb(52, 152, 219)` | Vértice intermediário de passagem padrão |
| **ROTA ÓTIMA** | Laranja Cenoura | `rgb(230, 126, 34)` | Caminho de custo efetivo mínimo encontrado pelo StratGraph |
| **Camada L0** | Azul Escuro | `rgb(41, 128, 185)` | Estado sem *power-up* ($z = 0$) |
| **Camada L1** | Âmbar / Ouro | `rgb(243, 156, 18)` | Estado com *power-up* ativo ($z = 150$) |

---

## 3. Passo a Passo: Como Abrir no Gephi

1. **Instalar o Gephi:**
   - Acesse [https://gephi.org](https://gephi.org) (Windows, Linux ou macOS).
2. **Abrir o Arquivo:**
   - No Gephi, vá em **Arquivo (File) -> Abrir (Open)**.
   - Selecione qualquer arquivo em `results/gephi/`, por exemplo:
     - `results/gephi/sample_toy/sample_toy_optimal_route.gexf` (ou qualquer instância desejada).
3. **Relatório de Importação:**
   - O Gephi detectará automaticamente:
     - Tipo de Grafo: **Direcionado (Directed)**.
     - Contagem exata de nós, arestas e atributos (`tipo_sala`, `valor_coletavel`, `tem_arma`, `na_rota_otima`).
   - Clique em **OK**.
4. **Visualização Imediata:**
   - Como o exportador já gera posições topológicas progressivas (`INICIO` à esquerda, `FIM` à direita), o fluxo do grafo já aparece organizado sem sobreposições críticas.
   - Para exibir os identificadores dos vértices (`id_sala`), clique no botão **"T"** na barra inferior da área de visualização.

---

## 4. Layouts Recomendados no Gephi

Na aba **Distribuição (Layout)**:

- **Visualização Topológica Padrão (sem rodar layout):**
  - Preserva o fluxo direcional da esquerda (`INICIO`) para a direita (`FIM`) com cruzamentos minimizados.
- **ForceAtlas2 (para evidenciar agrupamentos e *hubs*):**
  - Selecione **ForceAtlas2**, marque `Evitar sobreposição (Prevent Overlap)` e execute por 3 a 5 segundos.
- **Grafo em Camadas (`_layered.gexf`):**
  - Evidencia a separação estrutural entre os estados $L_0$ e $L_1$ e mostra claramente o ponto em que a rota ótima salta de camada.

---

## 5. Como Gerar Novamente via CLI

A exportação roda integralmente *offline* com a biblioteca padrão do Python:

```bash
# Exportar todas as instâncias presentes em datasets/
python -m scripts.export_gephi --all

# Exportar uma instância específica com alpha customizado
python -m scripts.export_gephi --dataset datasets/<caminho_da_instancia> --alpha 0.05 --out-dir results/gephi
```

---

## 6. Argumentos de Defesa para a Banca

Ao apresentar os grafos no Gephi, os três pontos centrais de defesa são:
1. **Abstração Agnóstica a Jogos:** Os grafos em `results/gephi/` provam que o núcleo (`src/`) independe de gráficos, colisões ou engine específica; os nomes e características de jogos específicos ficam isolados exclusivamente nos arquivos de entrada em `datasets/`.
2. **Trade-off Sublinear ($\alpha$):** Alternando entre o grafo base e o grafo com rota ótima, visualiza-se quando o algoritmo decide desviar até vértices roxos (`COLETAVEL`) apenas se a recompensa compensar o custo adicional segundo $W_{\text{efetivo}} = W_{\text{tempo}} / (1 + \alpha \cdot \text{valor})$.
3. **Grafo em Camadas Polinomial:** O arquivo `_layered.gexf` demonstra como mudanças permanentes de estado ($L_0 \to L_1$) são resolvidas por Dijkstra clássico com apenas $2|V'|$ vértices, evitando explosão combinatória.
