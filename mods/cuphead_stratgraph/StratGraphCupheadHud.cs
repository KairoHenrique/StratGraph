using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using UnityEngine;

namespace StratGraph.CupheadMod
{
    /// <summary>
    /// Componente HUD e Executor TAS in-game para Cuphead (`level41` a `level46`)
    /// compilado contra `Assembly-CSharp.dll` e `UnityEngine.IMGUIModule.dll`.
    ///   1. Exibe o setor atual, coordenadas reais do player e alcovas de moedas contraídas;
    ///   2. Ao pressionar `F5`, ativa/desativa o Modo Bot TAS, movimentando o jogador
    ///      automaticamente ao longo das plataformas e moedas da rota ótima do StratGraph.
    ///
    /// Autoria:
    ///   - Heitor Henrique Zonho
    ///   - Kairo Henrique Ferreira Martins
    ///   - Michel Pires da Silva
    /// </summary>
    public class StratGraphCupheadOverlay : MonoBehaviour
    {
        private static StratGraphCupheadOverlay _instance;

        private readonly Dictionary<string, List<string>> _routesBySlug =
            new Dictionary<string, List<string>>();

        private readonly Dictionary<string, List<Vector2>> _tasWaypointsBySlug =
            new Dictionary<string, List<Vector2>>();

        private readonly Dictionary<string, List<Vector2>> _bfsWaypointsBySlug =
            new Dictionary<string, List<Vector2>>();

        private readonly Dictionary<string, Dictionary<string, string>> _contractedBySlug =
            new Dictionary<string, Dictionary<string, string>>();

        private readonly Dictionary<string, string> _summaryBySlug =
            new Dictionary<string, string>();

        private bool _hudVisible = true;
        private bool _tasBotActive;
        private bool _useBfsRoute;
        private int _currentWaypointIndex;
        private bool _armedLayerActive;
        private string _lastSlug = "";

        public static void Init()
        {
            if (_instance != null)
            {
                return;
            }

            GameObject go = new GameObject("StratGraphCupheadHudObject");
            DontDestroyOnLoad(go);
            _instance = go.AddComponent<StratGraphCupheadOverlay>();
        }

        private void Awake()
        {
            string dllDir = Path.GetDirectoryName(typeof(StratGraphCupheadOverlay).Assembly.Location) ?? ".";
            string jsonPath = Path.Combine(dllDir, "stratgraph_routes.json");
            LoadRoutesJson(jsonPath);
        }

        private void LoadRoutesJson(string path)
        {
            if (!File.Exists(path))
            {
                return;
            }

            string raw = File.ReadAllText(path);
            string[] slugs = new string[]
            {
                "1_1f_forest_follies",
                "1_2f_treetop_trouble",
                "2_1f_funfair_fever",
                "2_2f_funhouse_frazzle",
                "3_1f_perilous_piers",
                "3_2f_rugged_ridge"
            };

            foreach (string slug in slugs)
            {
                string key = "\"cuphead_" + slug + "\"";
                int idx = raw.IndexOf(key, StringComparison.Ordinal);
                if (idx < 0)
                {
                    continue;
                }

                string block = raw.Substring(idx, Math.Min(28000, raw.Length - idx));

                Match sumMatch = Regex.Match(block, "\"hud_summary\"\\s*:\\s*\"([^\"]+)\"");
                if (sumMatch.Success)
                {
                    _summaryBySlug[slug] = sumMatch.Groups[1].Value;
                }

                Match routeMatch = Regex.Match(block, "\"strat_rooms\"\\s*:\\s*\\[([^\\]]+)\\]");
                if (routeMatch.Success)
                {
                    List<string> nodes = new List<string>();
                    MatchCollection matches = Regex.Matches(routeMatch.Groups[1].Value, "\"([^\"]+)\"");
                    foreach (Match m in matches)
                    {
                        nodes.Add(m.Groups[1].Value);
                    }
                    _routesBySlug[slug] = nodes;
                }

                Match contractedMatch = Regex.Match(block, "\"contracted_text\"\\s*:\\s*\"([^\"]*)\"");
                if (contractedMatch.Success)
                {
                    Dictionary<string, string> map = new Dictionary<string, string>();
                    string[] pairs = contractedMatch.Groups[1].Value.Split(';');
                    foreach (string p in pairs)
                    {
                        string[] kvp = p.Split(':');
                        if (kvp.Length == 2)
                        {
                            map[kvp[0].Trim()] = kvp[1].Trim();
                        }
                    }
                    _contractedBySlug[slug] = map;
                }

                Match wptsMatch = Regex.Match(block, "\"tas_waypoints_flat\"\\s*:\\s*\"([^\"]*)\"");
                if (wptsMatch.Success)
                {
                    _tasWaypointsBySlug[slug] = ParseWaypointsString(wptsMatch.Groups[1].Value);
                }

                Match bfsWptsMatch = Regex.Match(block, "\"bfs_waypoints_flat\"\\s*:\\s*\"([^\"]*)\"");
                if (bfsWptsMatch.Success)
                {
                    _bfsWaypointsBySlug[slug] = ParseWaypointsString(bfsWptsMatch.Groups[1].Value);
                }
            }
        }

        private List<Vector2> ParseWaypointsString(string rawPts)
        {
            List<Vector2> pts = new List<Vector2>();
            string[] pairs = rawPts.Split(';');
            foreach (string p in pairs)
            {
                string[] xy = p.Split(',');
                if (xy.Length == 2)
                {
                    float wx, wy;
                    if (float.TryParse(xy[0], NumberStyles.Float, CultureInfo.InvariantCulture, out wx) &&
                        float.TryParse(xy[1], NumberStyles.Float, CultureInfo.InvariantCulture, out wy))
                    {
                        pts.Add(new Vector2(wx, wy));
                    }
                }
            }
            return pts;
        }

        private string ResolveCurrentSlug(string sceneName)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                return "1_1f_forest_follies";
            }
            string s = sceneName.ToLowerInvariant();
            if (s.Contains("1_1f")) return "1_1f_forest_follies";
            if (s.Contains("1_2f")) return "1_2f_treetop_trouble";
            if (s.Contains("2_1f")) return "2_1f_funfair_fever";
            if (s.Contains("2_2f")) return "2_2f_funhouse_frazzle";
            if (s.Contains("3_1f")) return "3_1f_perilous_piers";
            if (s.Contains("3_2f")) return "3_2f_rugged_ridge";
            return "1_1f_forest_follies";
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.F5))
            {
                _tasBotActive = !_tasBotActive;
                _currentWaypointIndex = -1;
            }
            if (Input.GetKeyDown(KeyCode.F6))
            {
                _useBfsRoute = !_useBfsRoute;
                _currentWaypointIndex = -1;
            }

            if (!_tasBotActive)
            {
                return;
            }

            string sceneName = SceneLoader.Exists ? (SceneLoader.SceneName ?? "Menu") : "Menu";
            string slug = ResolveCurrentSlug(sceneName);

            Dictionary<string, List<Vector2>> activeDict = _useBfsRoute
                ? _bfsWaypointsBySlug
                : _tasWaypointsBySlug;

            List<Vector2> waypoints;
            if (!activeDict.TryGetValue(slug, out waypoints) || waypoints.Count == 0)
            {
                return;
            }

            AbstractPlayerController player = PlayerManager.Current;
            if (player == null || player.transform == null)
            {
                return;
            }

            Vector2 current = new Vector2(player.transform.position.x, player.transform.position.y);
            if (_currentWaypointIndex < 0 || _currentWaypointIndex >= waypoints.Count)
            {
                int bestIdx = 0;
                float bestDist = float.MaxValue;
                for (int i = 0; i < waypoints.Count; i++)
                {
                    float d = (waypoints[i] - current).sqrMagnitude;
                    if (d < bestDist)
                    {
                        bestDist = d;
                        bestIdx = i;
                    }
                }
                _currentWaypointIndex = bestIdx;
            }

            Vector2 target = waypoints[_currentWaypointIndex];
            Vector2 delta = target - current;
            float dist = delta.magnitude;

            float stepPx = 420f * Time.deltaTime;
            if (dist <= Mathf.Max(18f, stepPx))
            {
                player.transform.position = new Vector3(target.x, target.y, player.transform.position.z);
                _currentWaypointIndex++;
            }
            else
            {
                Vector2 nextPos = current + delta.normalized * stepPx;
                player.transform.position = new Vector3(nextPos.x, nextPos.y, player.transform.position.z);
            }
        }

        private void OnGUI()
        {
            if (!_hudVisible)
            {
                return;
            }

            string sceneName = SceneLoader.Exists ? (SceneLoader.SceneName ?? "Menu") : "Menu";
            string slug = ResolveCurrentSlug(sceneName);

            if (_lastSlug != slug)
            {
                _lastSlug = slug;
                _armedLayerActive = false;
                _currentWaypointIndex = 0;
            }

            Vector2 playerPos = Vector2.zero;
            try
            {
                playerPos = PlayerManager.Center;
            }
            catch
            {
                playerPos = Vector2.zero;
            }

            int secIdx = Mathf.Clamp(Mathf.FloorToInt(Mathf.Max(0f, playerPos.x) / 1500f), 0, 15);
            string currentSector = string.Format("sec_{0:00}", secIdx);

            if (secIdx >= 2 && playerPos.y > 150f)
            {
                _armedLayerActive = true;
            }

            string nextTarget = "parry_shrine_arma -> ... -> sec_15";
            List<string> route;
            if (_routesBySlug.TryGetValue(slug, out route) && route.Count > 0)
            {
                int pos = route.IndexOf(currentSector);
                if (pos >= 0 && pos + 1 < route.Count)
                {
                    nextTarget = route[pos + 1];
                }
                else if (secIdx == 15)
                {
                    nextTarget = "FIM DA FASE (sec_15)";
                }
            }

            string contractedCoins = "Nenhuma moeda em beco neste setor";
            Dictionary<string, string> cMap;
            if (_contractedBySlug.TryGetValue(slug, out cMap))
            {
                string coinsHere;
                if (cMap.TryGetValue(currentSector, out coinsHere) && !string.IsNullOrEmpty(coinsHere))
                {
                    contractedCoins = "Moeda(s) em Beco Contraído aqui: " + coinsHere;
                }
            }

            string summary;
            if (!_summaryBySlug.TryGetValue(slug, out summary))
            {
                summary = "StratGraph (Dijkstra L0->L1 + Contração) vs BFS";
            }

            GUI.Box(new Rect(18f, 18f, 680f, 132f), "");
            GUI.Label(
                new Rect(30f, 24f, 660f, 24f),
                string.Format(
                    "[StratGraph TAS] {0} | [F5] Bot: {1} | [F6] Rota: {2}",
                    slug,
                    _tasBotActive ? "ATIVO" : "OFF",
                    _useBfsRoute ? "BFS (L0 + Coletáveis)" : "StratGraph (L0->L1 + Coletáveis)"
                )
            );
            GUI.Label(
                new Rect(30f, 48f, 660f, 24f),
                string.Format(
                    "Setor Atual: {0} | Camada: {1} | Próximo Nó Ótimo: {2}",
                    currentSector,
                    _armedLayerActive ? "L1 (ARMA ATIVA - Dificuldade Reduzida)" : "L0 (Subir em parry_shrine_arma no sec_02!)",
                    nextTarget
                )
            );
            GUI.Label(
                new Rect(30f, 72f, 660f, 24f),
                contractedCoins
            );
            GUI.Label(
                new Rect(30f, 96f, 660f, 24f),
                summary
            );
        }
    }
}
