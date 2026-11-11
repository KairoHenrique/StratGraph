# Esquema do Dataset — StratGraph (Zenodo / Mendeley Data)

Cada cenário de mapa fica em uma subpasta contendo exatamente dois arquivos CSV com codificação **UTF-8** e separador `,`:

## 1. `vertices.csv`

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_sala` | `string` | Identificador único da sala ou plataforma (ex.: `S0`, `A1`, `BOSS`). |
| `tipo_sala` | `enum` | Um de: `INICIO`, `COMUM`, `COLETAVEL`, `ARMA`, `FIM`. |
| `valor_coletavel` | `float` | Valor/peso do item coletável presente na sala (`0` se não houver). |
| `possui_arma` | `0 \| 1` | `1` se a sala concede a arma/*power-up*; `0` caso contrário. |

## 2. `arestas.csv`

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `origem` | `string` | `id_sala` de partida. |
| `destino` | `string` | `id_sala` de chegada. |
| `mao_dupla` | `0 \| 1` | `1` gera `(origem, destino)` e `(destino, origem)`; `0` gera apenas `(origem, destino)`. |
| `tempo_base` | `float` | Tempo base de travessia (`> 0`). |
| `dificuldade_sem_arma` | `float` | Penalidade de obstáculo/combate sem arma (`>= 0`). |
| `dificuldade_com_arma` | `float` | Penalidade de obstáculo/combate com arma (`>= 0`). |

