# Roteiro de Defesa Oral (Pitch de 10 Minutos — Sem Slides)

> Baseado integralmente nas regras de [`docs/pratica (1).pdf`](pratica%20(1).pdf) (**10 minutos de fala livre, sem projeção de slides**, apresentações a partir de **25/11/2026**) e estruturado seguindo a narrativa didática e visual do artigo nota total de referência da disciplina.

---

## Linha do Tempo da Fala (10 min exatos)

### 1. Gancho e Problema Real (`0:00 – 1:30`)
* **Abertura direta:** *"Todo mundo conhece o algoritmo de Dijkstra para encontrar o caminho mais curto em um grafo. Mas na prática — seja em robótica, logística ou planejamento de rotas em jogos — o caminho geograficamente mais curto muitas vezes é péssimo."*
* **O dilema em 2 pontos:**
  1. Um desvio inicial até uma **ferramenta ou arma (*power-up*)** reduz drasticamente o custo de todo o resto do mapa.
  2. Existem recompensas opcionais pelo caminho (coletáveis em becos sem saída) que valem a pena coletar sob meta *All Collectibles*.
* **Por que a abordagem ingênua falha:**
  * **BFS:** conta só saltos, ignora custos reais e ignora a arma.
  * **Subtrair bônus dos pesos:** cria arestas negativas e ciclos absorventes que quebram o Dijkstra.
  * **Guardar um bitmask de todos os $k$ itens no estado:** explode para $O(2^k|V|)$ (NP-difícil, próximo ao PCTSP e *Orienteering Problem*).

---

### 2. A Ideia Central do **StratGraph** (`1:30 – 4:15`)
* **Núcleo agnóstico a domínio:** *"Nós desenvolvemos o **StratGraph**, um motor genérico em Python 3.12 usando exclusivamente biblioteca padrão — roda via terminal no Ubuntu 24.04 sobre qualquer grafo no formato `vertices.csv` e `arestas.csv`, sem depender de nenhum jogo."*
* **Três decisões claras de engenharia que tornam o problema polinomial:**
  1. **Contração Iterativa de Becos Sem Saída (`src/preprocessing.py`):** para cumprir a meta *All Collectibles* nas ramificações terminais, fundimos iterativamente cada beco sem saída com coletável na sala vizinha, somando o custo mínimo de ida e volta por camada (`sem arma` e `com arma`) e mantendo o log em `contracted_into`. Só nisso reduzimos até **72,7%** dos vértices nos mapas reais (*Old Site*: $33 \to 9$).
  2. **Expansão Markoviana em Duas Camadas (`src/layered_graph.py`):** duplicamos o grafo reduzido em $L_0$ (sem arma) e $L_1$ (com arma), ligados por arestas de custo zero $(u_{\text{arma}}, 0) \to (u_{\text{arma}}, 1)$. Mantemos o estado apenas como $(v, k)$ — sem bitmask de itens — garantindo espaço $O(2|V'|)$ em vez de $O(2^k|V|)$.
  3. **Função Substituta Heurística Estritamente Positiva:**
     $$w(u, v, k) = \frac{\text{TempoBase}(u, v) + \text{Dificuldade}(u, v, k)}{1 + \alpha \cdot \text{ValorColetavel}(v)}, \quad \alpha \ge 0$$
     Garante sempre $w > 0$, preservando a validade do Dijkstra enquanto $\alpha$ regula o apetite por desvios com recompensas.

---

### 3. Validação Empírica, Análise no Gephi e Resultados Reais (`4:15 – 7:30`)
* **Como alimentamos os testes:** extraímos 14 fases reais de *Celeste* (8 capítulos, $A^*$ físico em grid $8\times 8$) e *Cuphead* (6 fases *Run-and-Gun*, cadeias de plataformas) publicadas no **Zenodo** (`doi:10.5281/zenodo.24147071`), além de 7 grafos sintéticos de $15$ a $5.000$ salas.
* **O que o Gephi mostrou estruturalmente:** exportando `.gexf` (*Force Atlas 2*, *Modularity Class* de Louvain e grau), provamos que os níveis reais têm grafos esparsos (densidade entre $0{,}015$ e $0{,}080$) e alta modularidade ($Q$ entre $0{,}59$ e $0{,}93$ nos unificados), formando subcomunidades ligadas por gargalos de transição. Filtrando o subgrafo no Gephi, vê-se claramente o BFS seguindo reto na camada $L_0$ enquanto o StratGraph desvia no ponto ótimo para ativar $L_1$.
* **Resultados em Custo Real AND Peso Efetivo (não só na heurística!):**
  * Mesmo olhando apenas para o **Custo Real bruto ($\text{TempoBase} + \text{Dificuldade}$)**, o Dijkstra em camadas corta o custo em **11,1% a 50,9%** em *Celeste* (**48,1%** em *The Summit*) e **55,4% a 68,3%** em *Cuphead* (*2-2F Funhouse Frazzle*: de $2.100{,}5$ para $666{,}9$) frente ao BFS, coletando **100%** dos itens nas 14 fases reais (enquanto `--no-contract` perde mais da metade em *Celeste* e 5/5 moedas em *Cuphead*).
  * Na ablação de $\alpha$ em `v_0150`, subir $\alpha$ de $0{,}00$ para $0{,}50$ amplia a captura de $30$ para $43$ itens ($+43{,}3\%$) pagando apenas $+5{,}9\%$ de custo real adicional, enquanto sem contração estagna em $17$.

---

### 4. Análise Crítica de Gargalos e Honestidade Científica (`7:30 – 9:15`)
* **Comparação assintótica (`v_0015` a `v_5000`):** o DFS *Branch-and-Bound* iguala os custos até $|V|=30$, mas explode combinatoriamente por ciclos paralelos a partir de $|V|=60$ (estourando o *timeout* de 150 ms após >65 mil estados), enquanto o Dijkstra em camadas resolve 5.000 salas em **14,49 ms** ($O((V+E)\log V)$).
* **Limitações explicitamente assumidas:**
  1. **Exatidão relativa à função substituta:** o Dijkstra resolve *exatamente* a soma estática de $w(u,v,k)$ sobre $G_L$; ele é uma relaxação polinomial (não um solver NP-difícil para múltiplas passagens por uma mesma sala coletável). Caso uma sala com coletável não contraído seja visitada em $L_0$ e depois em $L_1$ (como observado isoladamente em `v_0060`), a busca estática aplica o desconto nos dois arcos enquanto nossa auditoria `evaluate_path` deduplica o desconto.
  2. Em grafos sintéticos com itens em caminhos paralelos disjuntos, a contração garante 100% apenas sobre as folhas terminais dos nós visitados.
  3. Para $k$ armas acumuláveis simultaneamente, o modelo cresceria para $2^k|V|$, apontando para uso futuro de $A^*$ com heurísticas admissíveis ou rotulação seletiva apenas nos nós articuladores.

---

### 5. Fechamento e Reprodutibilidade (`9:15 – 10:00`)
* *"Todo o projeto está reproduzível em terminal Ubuntu 24.04, validado com suíte automatizada (`pytest -v`), gráficos GEXF para Gephi, simulador 2D e dados abertos com DOI no Zenodo. Estamos abertos para as perguntas da banca."*

---

## FAQ — Respostas Prontas para Perguntas Difíceis da Banca

1. **P: "Por que vocês dizem que o Dijkstra resolve de forma ótima se a fórmula tem $\alpha$ heurístico e o estado não guarda os itens já pegos?"**
   * **R:** *"Excelente ponto. O Dijkstra é garantidamente ótimo **para a função objetivo substituta estática sobre $G_L$**, que escolhemos de forma estritamente positiva para preservar $O((V+E)\log V)$. Omitir o bitmask de itens no estado foi uma decisão consciente para evitar a explosão $O(2^k|V|)$ do Orienteering/PCTSP. Em topologias com passagem dupla na mesma sala coletável entre $L_0$ e $L_1$, a relaxação estática difere da avaliação deduplicada em `evaluate_path` — o que assumimos explicitamente nas limitações."*
2. **P: "A comparação com o BFS usando o próprio peso efetivo de vocês não beneficia o método?"**
   * **R:** *"Por isso reportamos também o **Custo Real** bruto ($\text{TempoBase} + \text{Dificuldade}$, sem $\alpha$ nem divisão) nas Tabelas I e II: mesmo no custo físico puro, o Dijkstra em camadas economiza até 50,9% em Celeste e 68,3% em Cuphead em relação ao BFS, sob os mesmos 100% de itens coletados."*
3. **P: "A contração de becos não altera o problema obrigando o agente a pegar itens que talvez não compensassem?"**
   * **R:** *"Sim, essa é uma premissa explícita do problema: quando o objetivo é coleta em ramificações terminais (*All Collectibles* nas folhas), toda alcova terminal ligada a um único pai pode ter sua ida e volta embutida nas arestas de entrada desse pai (com escolha independente da menor aresta em $L_0$ e em $L_1$). Nossa ablação `--no-contract` mostra exatamente o que acontece sem essa decisão: o algoritmo ignora os becos."*
4. **P: "O código de vocês depende de Celeste ou Cuphead para rodar?"**
   * **R:** *"De forma alguma. Toda a pasta `src/` tem zero importação de bibliotecas de jogo ou pacotes externos — usa só a biblioteca padrão do Python 3.12 e lê `vertices.csv` e `arestas.csv`. Os jogos entraram apenas como extratores externos para gerar benchmarks realistas e reproduzíveis publicados no Zenodo."*

