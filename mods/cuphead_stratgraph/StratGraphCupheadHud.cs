using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using UnityEngine;

namespace StratGraph.CupheadMod
{
    /// <summary>
    /// Componente HUD visual (somente exibição de rota — sem alteração de inputs ou trapaças)
    /// para Cuphead (`level41` a `level46`) compilado contra `Assembly-CSharp.dll`.
    ///   1. Desenha na tela os waypoints e linhas da rota ótima sobre o mundo real;
    ///   2. Exibe o setor atual, camada (`L0`/`L1`) e moedas de alcovas contraídas;
    ///   3. `[F5]` mostra/oculta o HUD e `[F6]` alterna ao vivo entre StratGraph (`L0 -> L1`) e BFS (`L0`).
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
        private bool _useBfsRoute;
        private bool _armedLayerActive;
        private string _lastSlug = "";
        private Texture2D _lineTex;

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

        private static string ExtractJsonObjectBlock(string raw, string key)
        {
            int idx = raw.IndexOf(key, StringComparison.Ordinal);
            if (idx < 0)
            {
                return "";
            }
            int openBrace = raw.IndexOf('{', idx);
            if (openBrace < 0)
            {
                return "";
            }
            int depth = 0;
            bool inStr = false;
            bool escaped = false;
            for (int i = openBrace; i < raw.Length; i++)
            {
                char ch = raw[i];
                if (escaped)
                {
                    escaped = false;
                    continue;
                }
                if (ch == '\\' && inStr)
                {
                    escaped = true;
                    continue;
                }
                if (ch == '"')
                {
                    inStr = !inStr;
                    continue;
                }
                if (!inStr)
                {
                    if (ch == '{') depth++;
                    else if (ch == '}')
                    {
                        depth--;
                        if (depth == 0)
                        {
                            return raw.Substring(openBrace, i - openBrace + 1);
                        }
                    }
                }
            }
            return raw.Substring(openBrace);
        }

        private void Awake()
        {
            _lineTex = new Texture2D(1, 1);
            _lineTex.SetPixel(0, 0, Color.white);
            _lineTex.Apply();

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
                string block = ExtractJsonObjectBlock(raw, key);
                if (string.IsNullOrEmpty(block))
                {
                    continue;
                }

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
                return "";
            }
            string s = sceneName.ToLowerInvariant();
            if (s.Contains("1_1f")) return "1_1f_forest_follies";
            if (s.Contains("1_2f")) return "1_2f_treetop_trouble";
            if (s.Contains("2_1f")) return "2_1f_funfair_fever";
            if (s.Contains("2_2f")) return "2_2f_funhouse_frazzle";
            if (s.Contains("3_1f")) return "3_1f_perilous_piers";
            if (s.Contains("3_2f")) return "3_2f_rugged_ridge";
            return "";
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.F5))
            {
                _hudVisible = !_hudVisible;
            }
            if (Input.GetKeyDown(KeyCode.F6))
            {
                _useBfsRoute = !_useBfsRoute;
            }
        }

        private void DrawGuiLine(Vector2 a, Vector2 b, Color color, float thickness)
        {
            if (_lineTex == null)
            {
                return;
            }
            Vector2 diff = b - a;
            float len = diff.magnitude;
            if (len < 1f)
            {
                return;
            }
            float angle = Mathf.Atan2(diff.y, diff.x) * Mathf.Rad2Deg;
            Matrix4x4 savedMatrix = GUI.matrix;
            Color savedColor = GUI.color;

            GUI.color = color;
            GUIUtility.RotateAroundPivot(angle, a);
            GUI.DrawTexture(new Rect(a.x, a.y - thickness * 0.5f, len, thickness), _lineTex);

            GUI.matrix = savedMatrix;
            GUI.color = savedColor;
        }

        private void DrawWorldRouteOverlay(string slug, Color accent)
        {
            Camera cam = Camera.main;
            if (cam == null)
            {
                return;
            }

            Dictionary<string, List<Vector2>> activeDict = _useBfsRoute
                ? _bfsWaypointsBySlug
                : _tasWaypointsBySlug;
            List<Vector2> wpts;
            if (!activeDict.TryGetValue(slug, out wpts) || wpts.Count < 2)
            {
                return;
            }

            Vector2? prevScreen = null;
            for (int i = 0; i < wpts.Count; i++)
            {
                Vector3 sp = cam.WorldToScreenPoint(new Vector3(wpts[i].x, wpts[i].y, 0f));
                Vector2 guiPt = new Vector2(sp.x, Screen.height - sp.y);
                bool onScreen = sp.z > 0f && guiPt.x >= -120f && guiPt.x <= Screen.width + 120f &&
                                guiPt.y >= -120f && guiPt.y <= Screen.height + 120f;

                if (prevScreen.HasValue && (onScreen ||
                    (prevScreen.Value.x >= -120f && prevScreen.Value.x <= Screen.width + 120f)))
                {
                    DrawGuiLine(prevScreen.Value, guiPt, accent, 3f);
                }

                if (onScreen && i % 2 == 0)
                {
                    Color savedColor = GUI.color;
                    GUI.color = Color.white;
                    if (_lineTex != null)
                    {
                        GUI.DrawTexture(new Rect(guiPt.x - 3f, guiPt.y - 3f, 6f, 6f), _lineTex);
                    }
                    GUI.color = savedColor;
                }
                prevScreen = guiPt;
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

            if (string.IsNullOrEmpty(slug))
            {
                GUI.Box(new Rect(18f, 18f, 540f, 34f), "");
                GUI.Label(
                    new Rect(28f, 24f, 520f, 24f),
                    "[StratGraph Guia Visual] Entre em uma fase Run-and-Gun (1-1F .. 3-2F). [F5] HUD"
                );
                return;
            }

            if (_lastSlug != slug)
            {
                _lastSlug = slug;
                _armedLayerActive = false;
            }

            Color accent = _useBfsRoute
                ? new Color(1f, 0.36f, 0.47f, 0.85f)
                : (_armedLayerActive ? new Color(0f, 1f, 0.53f, 0.85f) : new Color(0f, 0.90f, 1f, 0.85f));
            DrawWorldRouteOverlay(slug, accent);

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

            GUI.Box(new Rect(18f, 18f, 680f, 126f), "");
            GUI.Label(
                new Rect(30f, 24f, 660f, 24f),
                string.Format(
                    "[StratGraph Guia Visual] {0} | [F5] HUD | [F6] Rota: {1}",
                    slug,
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
