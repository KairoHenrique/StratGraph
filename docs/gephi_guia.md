# Guia de Visualização no Gephi (.gexf) — StratGraph

Este guia orienta alunos, pesquisadores e a banca avaliadora sobre como abrir, visualizar e explorar os grafos gerados pelo **StratGraph** no [Gephi](https://gephi.org/) (versões 0.9.x e 0.10.x).

---

## 1. O Que Foi Gerado?

Para cada nível (capítulos de *Celeste*, fases de *Cuphead*, exemplos didáticos e grafos sintéticos), o StratGraph exporta automaticamente um **trio de arquivos GEXF 1.2** em `results/gephi/<dataset>/`:

1. **`<dataset>_base.gexf` (Grafo Topológico Original):**
   - Grafo direcionado ponderado com as salas originais do jogo.
   - Nós posicionados conforme as coordenadas 2D espaciais reais do mapa (obtidas dos binários `.bin` e metadados).
   - Cores padronizadas por papel funcional da sala (`INICIO`, `FIM`, `ARMA`, `COLETAVEL`, `COMUM`).

2. **`<dataset>_optimal_route.gexf` (Rota Ótima Destacada):**
   - O grafo base com o caminho ótimo calculado pelo algoritmo **Dijkstra** do StratGraph destacado.
   - As arestas pertencentes à rota ótima possuem espessura aumentada (`thickness=4.0` ou `5.0`), opacidade total e cor **Laranja Cenoura**, enquanto as arestas secundárias ficam atenuadas e translúcidas (`opacity=0.3`).
   - Nós da rota ótima possuem atributo booleano `na_rota_otima = true`.

3. **`<dataset>_layered.gexf` (Grafo em Camadas L0 e L1):**
   - Demonstração visual do espaço de estados $V \times \{0, 1\}$.
   - **Camada 0 ($L_0$):** Estado sem arma / upgrade (nós em azul escuro, $z = 0$).
   - **Camada 1 ($L_1$):** Estado após coleta da arma / upgrade (nós em laranja/dourado, $z = 150$, com translação espacial no eixo Y).
   - **Transições Intercamadas:** Arestas verticais douradas com espessura destacada que conectam a sala da arma em $L_0$ para seus vizinhos em $L_1$.
   - A rota ótima atravessa de $L_0$ para $L_1$ no exato momento da aquisição do recurso.

---

## 2. Paleta de Cores Padronizada

Os nós e arestas já vêm com cores RGB embutidas (usando o namespace XML `xmlns:viz="http://www.gexf.net/1.2draft/viz"`):

| Elemento / Tipo | Cor | Código RGB | Significado Acadêmico / Prático |
| :--- | :--- | :--- | :--- |
| **INICIO** | Verde Esmeralda | `rgb(46, 204, 113)` | Ponto de spawn inicial do nível |
| **FIM** | Vermelho Alizarin | `rgb(231, 76, 60)` | Sala de saída / objetivo final |
| **ARMA** | Dourado / Amarelo | `rgb(241, 196, 15)` | Sala com item que habilita a camada $L_1$ |
| **COLETAVEL** | Roxo Ametista | `rgb(155, 89, 182)` | Sala com morango/moeda (ponderação sublinear $\alpha$) |
| **COMUM** | Azul Peter River | `rgb(52, 152, 219)` | Sala de passagem padrão |
| **ROTA ÓTIMA** | Laranja Cenoura | `rgb(230, 126, 34)` | Sequência ótima encontrada pelo StratGraph |
| **Camada L0** | Azul Escuro | `rgb(41, 128, 185)` | Estado sem arma ($z = 0$) |
| **Camada L1** | Âmbar / Ouro | `rgb(243, 156, 18)` | Estado com arma ($z = 150$) |

---

## 3. Passo a Passo: Como Abrir no Gephi

1. **Baixar e Instalar o Gephi:**
   - Acesse [https://gephi.org](https://gephi.org) e baixe o instalador gratuito (Windows/Linux/Mac).
2. **Abrir o Arquivo:**
   - No Gephi, vá em **Arquivo (File) -> Abrir (Open)**.
   - Navegue até a pasta `results/gephi/` e selecione, por exemplo:
     - `results/gephi/1_forsaken_city/1_forsaken_city_optimal_route.gexf`
3. **Janela de Relatório de Importação:**
   - O Gephi detectará automaticamente:
     - Tipo de Grafo: **Direcionado (Directed)**.
     - Número de Nós e Arestas.
     - Auto-loops e arestas múltiplas: 0.
   - Clique em **OK**.
4. **Visualização Imediata (Coordenadas Reais):**
   - Como o StratGraph já injeta coordenadas cartesianas reais (`viz:position`), o mapa do jogo já aparece montado na tela na exata geometria física das salas!
   - Se desejar ver os rótulos das salas, clique no ícone **"T"** (Mostrar rótulos dos nós) na barra inferior da visualização.

---

## 4. Layouts Recomendados no Gephi

Dependendo do objetivo da apresentação, use a aba **Distribuição (Layout)** à esquerda:

- **Para Manter a Geometria Física do Jogo:**
  - Não execute nenhum algoritmo de força! Os nós já vêm posicionados com $x, y$ reais do jogo.
- **Para Evidenciar Centralidade e Topologia (ForceAtlas2):**
  - Selecione **ForceAtlas2** no menu suspenso.
  - Marque: `Prevent Overlap` (Evitar sobreposição).
  - Diminua `Scaling` para 2.0 e clique em **Executar (Run)** por 3 a 5 segundos e pare.
  - Isso agrupa corredores lineares e destaca hubs de decisão.
- **Para o Grafo em Camadas (`_layered.gexf`):**
  - Como o arquivo possui atributo $Z$ (`z=0` para $L_0$ e `z=150` para $L_1$), no Gephi você pode usar o plugin **3D View** ou visualizar a separação vertical 2D onde a camada $L_1$ aparece deslocada verticalmente no eixo Y.

---

## 5. Como Gerar Novamente ou Exportar Outros Grafos

A exportação é 100% automatizada e roda offline via linha de comando:

```bash
# Exportar TODOS os datasets (Celeste, Cuphead e Sintéticos):
python -m scripts.export_gephi --all

# Exportar apenas um capítulo específico com um valor de alpha customizado:
python -m scripts.export_gephi --dataset datasets/celeste/1_forsaken_city --alpha 0.08 --out results/gephi
```

---

## 6. Argumentos de Defesa para a Apresentação Oral (10 min sem slides)

Ao mostrar ou citar o Gephi para o professor:
1. **Representação Fidedigna e Agnóstica:** Os arquivos GEXF provam que o modelo de dígrafo com atributos funcionais (`RoomType`) é independente da engine gráfica do jogo. Qualquer jogo (Celeste, Cuphead, Metroid, Hollow Knight) gera a mesma estrutura formal.
2. **Visualização Clara da Ponderação Sublinear:** No Gephi, ao alternar entre o grafo base e o grafo com rota ótima, fica visualmente evidente que o StratGraph desvia o caminho principal para coletar itens valiosos apenas quando a distância extra compensa a redução de custo pela fórmula $W_{eff} = W_{tempo} / (1 + \alpha \cdot \text{valor})$.
3. **Expansão em Camadas vs. Explosão Combinatória:** No arquivo `_layered.gexf`, a banca pode ver com clareza como a mudança de estado (pegar arma/upgrade) é modelada sem memória histórica em grafos, duplicando apenas os vértices alcançáveis ($2 \times |V|$) em vez de sofrer explosão exponencial de estados.
