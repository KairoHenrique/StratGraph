# Mods de Teste *In-Game* — StratGraph (*Celeste* & *Cuphead*)

Esta pasta contém o código-fonte em C# (.NET Framework 4.0) dos dois mods de telemetria *in-game* do **StratGraph**, que leem o arquivo `stratgraph_routes.json` exportado pelo motor em Python (`src/`) e desenham na tela do jogo a rota ótima em camadas ($L_0 \to L_1$), o estado da arma e os becos sem saída contraídos.

## Estrutura

* [`celeste_stratgraph/StratGraphCelesteHud.cs`](celeste_stratgraph/StratGraphCelesteHud.cs) e [`celeste_stratgraph/everest.yaml`](celeste_stratgraph/everest.yaml):
  * Entidade HUD (`Monocle.Entity` com `Tags.HUD | Tags.Global`) compilada contra `Celeste.exe` e `Microsoft.Xna.Framework`.
  * Lê `level.Session.Area.ID` e `level.Session.Level` em tempo real para identificar a sala atual (`lvl_1`, `lvl_6z`, etc.), indicar a próxima sala da rota ótima do **StratGraph**, avisar quando houver becos sem saída contraídos para coletar morangos na sala atual e mudar o painel de ciano ($L_0$) para verde-esmeralda ($L_1$) ao visitar a sala de `ARMA`.
* [`cuphead_stratgraph/StratGraphCupheadHud.cs`](cuphead_stratgraph/StratGraphCupheadHud.cs):
  * Componente `UnityEngine.MonoBehaviour` (`StratGraphCupheadOverlay`) compilado contra `Cuphead_Data/Managed/Assembly-CSharp.dll`, `UnityEngine.CoreModule.dll` e `UnityEngine.IMGUIModule.dll`.
  * Lê `SceneLoader.SceneName` e `PlayerManager.Center` em tempo real no método `OnGUI()`, mapeia a coordenada $X$ do jogador para o setor do dígrafo (`sec_00` a `sec_15`), destaca as moedas em becos contraídos (`coin_01`, `coin_03`, `coin_05`) e compara o custo real e total de moedas do **StratGraph** contra o **BFS**.

## Como Exportar as Rotas e Compilar as DLLs

No Windows (com *Celeste* e *Cuphead* instalados na Steam):

```powershell
python -m scripts.build_mods
```

O comando gera automaticamente em `mods/dist/`:
1. `mods/dist/stratgraph_routes.json` — todas as rotas ótimas e becos contraídos dos 8 capítulos de *Celeste* e 6 fases *Run-and-Gun* de *Cuphead*;
2. `mods/dist/celeste/StratGraphCelesteMod.dll` e `StratGraphCelesteMod.zip` — pacote pronto para a pasta `Mods/` do **Everest** no *Celeste*;
3. `mods/dist/cuphead/StratGraphCupheadMod.dll` — biblioteca pronta para carregamento via **BepInEx 5 / Unity Doorstop** (`StratGraph.CupheadMod.StratGraphCupheadOverlay.Init()`).

