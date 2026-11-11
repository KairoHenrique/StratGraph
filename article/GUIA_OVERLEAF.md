# Guia do Artigo Científico — StratGraph (IEEE Conference Template)

Esta pasta armazena o rascunho estruturado em LaTeX compatível com o **IEEE Conference Template** exigido pela disciplina:

* Template oficial no Overleaf: https://www.overleaf.com/latex/templates/ieee-conference-template/grfzhhncsfqn

## Arquivos

* [main.tex](main.tex): estrutura inicial completa do artigo com todas as seções obrigatórias (Resumo, Introdução em funil + parágrafo de roteiro, Referencial Teórico, Metodologia com espaço para o fluxograma, Resultados e Discussão, Conclusão e Próximas Etapas).
* [references.bib](references.bib): referências científicas verificadas (mais entradas reservadas para o repositório GitHub e o dataset no Zenodo/Mendeley).
* `figures/`: figuras geradas pelos scripts (`fluxograma_proposta` e gráficos experimentais).

## Checklist Antes da Submissão (AVA — 22/11/2026)

1. Confirmar a ordem dos autores alunos em `main.tex` (por contribuição decrescente, ou alfabética se igualitária), mantendo **Michel Pires da Silva** obrigatoriamente por último.
2. Inserir o link/DOI real do dataset após o upload no **Zenodo** ou **Mendeley Data** em `references.bib`.
3. Verificar todas as referências no **Google Scholar** (`scholar.google.com`) e garantir que cada item de `references.bib` esteja citado com `\cite{...}` no corpo do texto.
4. Submeter **apenas o PDF final** compilado no AVA.

