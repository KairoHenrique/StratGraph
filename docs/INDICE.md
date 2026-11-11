# Índice da Documentação — StratGraph

Esta pasta centraliza a documentação técnica, os requisitos acadêmicos e os guias de execução do projeto **StratGraph**.

## Documentos Disponíveis

1. [Plano de Implementação](plano_implementacao.md) — cronograma, status atualizado, fases técnicas e plano de verificação do projeto.
2. [Arquitetura e Modelagem Matemática](arquitetura_e_modelagem.md) — definição formal do dígrafo ponderado, contração de becos sem saída, grafo em camadas e papel dos algoritmos (BFS, DFS *Branch-and-Bound* e Dijkstra).
3. [Guia de Execução (Linux e Windows)](execucao_linux_windows.md) — instruções objetivas para executar no **Ubuntu 24.04** e no **Windows**.
4. [Esquema do Dataset (Zenodo / Mendeley Data)](../datasets/ESQUEMA_DATASET.md) — formato oficial de `vertices.csv` e `arestas.csv`.
5. [Guia do Artigo IEEE / Overleaf](../article/GUIA_OVERLEAF.md) — checklist de compilação e envio no AVA.

## Checklist dos Requisitos Acadêmicos

Conforme o enunciado em [pratica (1).pdf](pratica%20(1).pdf):

- [x] **Código-Fonte (GitHub):** implementação estruturada em Python 3.12 (biblioteca padrão em `src/`), validada com 10 testes no Windows (`pytest`) e pronta para execução via terminal no Ubuntu 24.04.
- [ ] **Validação no Ubuntu 24.04:** rodar CLI e testes diretamente em terminal Linux antes da entrega.
- [x] **Base de Dados (Local):** mapas tratados dos 8 capítulos de *Celeste*, 6 fases *Run-and-Gun* de *Cuphead* e 7 grafos sintéticos gerados em `datasets/`.
- [ ] **Publicação da Base de Dados (Zenodo / Mendeley Data):** publicar o pacote `datasets/` e inserir o link/DOI definitivo em `article/references.bib`.
- [ ] **Artigo Científico (AVA / IEEE Conference Template):**
  - [x] Ordem de autoria: alunos em ordem alfabética (`Heitor Henrique Zonho`, `Kairo Henrique Ferreira Martins`) e **Michel Pires da Silva** como último autor obrigatório.
  - [x] Texto estruturado com Resumo, Introdução (funil e roteiro), Referencial Teórico, Metodologia (**fluxograma obrigatório** incluso em `article/figures/fluxograma_proposta.pdf`), Resultados e Discussão (gráficos e tabelas reais) e Conclusão.
  - [ ] Compilação final no Overleaf, conferência das referências no Google Scholar (`scholar.google.com`), conferência do limite de 250 palavras no resumo e inserção do DOI final do Zenodo.
- [ ] **Prazo de entrega no AVA:** 22/11/2026.
- [ ] **Apresentação Oral (Pitch):** início em 25/11/2026 (10 minutos sem slides).
