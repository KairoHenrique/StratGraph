using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
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

        private int _tasMoveX;
        private int _tasMoveY;
        private float _tasJumpCooldown;
        private float _tasHoldJumpTimer;
        private float _tasDashCooldown;
        private float _tasParryCooldown;
        private float _tasStuckTimer;
        private Vector2 _lastPlayerPos;

        private static MethodInfo _bufferInputMethod;
        private static MethodInfo _startBasicMethod;
        private static FieldInfo _basicField;
        private static FieldInfo _firingField;

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

        public static int FilterAxisInt(int originalValue, int axis)
        {
            if (_instance == null || !_instance._tasBotActive)
            {
                return originalValue;
            }
            if (axis == 0)
            {
                return _instance._tasMoveX;
            }
            if (axis == 1)
            {
                return _instance._tasMoveY;
            }
            return originalValue;
        }

        public static bool FilterJumpButtonHeld(bool originalValue)
        {
            if (_instance != null && _instance._tasBotActive && _instance._tasHoldJumpTimer > 0f)
            {
                return true;
            }
            return originalValue;
        }

        public static void BeforeMotorHandleInput(LevelPlayerMotor motor)
        {
            if (_instance != null && motor != null)
            {
                _instance.DriveCupheadMotor(motor);
            }
        }

        public static void AfterWeaponHandleFiring(LevelPlayerWeaponManager wm)
        {
            if (_instance != null && wm != null)
            {
                _instance.DriveCupheadWeapons(wm);
            }
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
                _tasStuckTimer = 0f;
                _tasMoveX = 0;
                _tasMoveY = 0;
            }
            if (Input.GetKeyDown(KeyCode.F6))
            {
                _useBfsRoute = !_useBfsRoute;
                _currentWaypointIndex = -1;
                _tasStuckTimer = 0f;
            }
        }

        private void TriggerBufferedInput(LevelPlayerMotor motor, int bufferedType)
        {
            try
            {
                if (_bufferInputMethod == null)
                {
                    _bufferInputMethod = typeof(LevelPlayerMotor).GetMethod(
                        "BufferInput",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public
                    );
                }
                if (_bufferInputMethod != null)
                {
                    Type enumType = _bufferInputMethod.GetParameters()[0].ParameterType;
                    object enumVal = Enum.ToObject(enumType, bufferedType);
                    _bufferInputMethod.Invoke(motor, new object[] { enumVal });
                }
            }
            catch
            {
            }
        }

        private void DriveCupheadMotor(LevelPlayerMotor motor)
        {
            if (!_tasBotActive || motor == null || motor.transform == null)
            {
                _tasHoldJumpTimer = 0f;
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

            Vector2 current = new Vector2(motor.transform.position.x, motor.transform.position.y);
            if ((current - _lastPlayerPos).sqrMagnitude > 250000f)
            {
                // Respawn ou transição de sala: realinha no waypoint mais próximo
                _currentWaypointIndex = -1;
                _tasHoldJumpTimer = 0f;
            }

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

            while (_currentWaypointIndex < waypoints.Count - 1 &&
                   Mathf.Abs(waypoints[_currentWaypointIndex].x - current.x) <= 44f &&
                   Mathf.Abs(waypoints[_currentWaypointIndex].y - current.y) <= 48f)
            {
                _currentWaypointIndex++;
                _tasStuckTimer = 0f;
            }

            Vector2 target = waypoints[_currentWaypointIndex];
            Vector2 delta = target - current;
            float dt = Time.fixedDeltaTime > 0f ? Time.fixedDeltaTime : 0.016f;

            if (_tasJumpCooldown > 0f) _tasJumpCooldown -= dt;
            if (_tasHoldJumpTimer > 0f) _tasHoldJumpTimer -= dt;
            if (_tasDashCooldown > 0f) _tasDashCooldown -= dt;
            if (_tasParryCooldown > 0f) _tasParryCooldown -= dt;

            if ((current - _lastPlayerPos).sqrMagnitude < 4f)
            {
                _tasStuckTimer += dt;
            }
            else
            {
                _tasStuckTimer = Mathf.Max(0f, _tasStuckTimer - dt * 0.5f);
            }
            _lastPlayerPos = current;

            // 1. Eixos direcionais reais do controle (lidos por HandleWalking e HandleLooking)
            _tasMoveX = Mathf.Abs(delta.x) > 10f ? (delta.x >= 0f ? 1 : -1) : 1;
            _tasMoveY = delta.y > 70f ? 1 : 0;

            // 2. Pulo real do Cuphead (BufferInput(BufferedInput.Jump = 0) + Hold de Jump via Rewired)
            if (motor.Grounded && _tasJumpCooldown <= 0f &&
                (delta.y > 18f || _tasStuckTimer > 0.12f || (Mathf.Abs(delta.x) > 155f && delta.y >= -15f)))
            {
                TriggerBufferedInput(motor, 0);
                _tasJumpCooldown = 0.26f;
                _tasHoldJumpTimer = delta.y > 55f ? 0.28f : 0.22f;
            }
            else if (motor.Grounded && _tasJumpCooldown < 0.16f)
            {
                _tasHoldJumpTimer = 0f;
            }

            // 3. Parry real no ar (BufferInput(BufferedInput.Jump = 0) quando fora do chão)
            if (!motor.Grounded && _tasParryCooldown <= 0f && delta.y > 35f)
            {
                TriggerBufferedInput(motor, 0);
                _tasParryCooldown = 0.24f;
            }

            // 4. Dash real no ar ou em lacunas largas (sem overshoot em plataformas curtas)
            if (!motor.Dashing && _tasDashCooldown <= 0f &&
                (Mathf.Abs(delta.x) > 195f || (!motor.Grounded && Mathf.Abs(delta.x) > 110f && Mathf.Abs(delta.y) < 35f)))
            {
                TriggerBufferedInput(motor, 1);
                _tasDashCooldown = 0.52f;
            }

            // Sem impulsos artificiais: se o bot errar, o jogo aplica dano/morte normalmente.
        }

        private void DriveCupheadWeapons(LevelPlayerWeaponManager wm)
        {
            if (!_tasBotActive || wm == null)
            {
                return;
            }
            try
            {
                if (_startBasicMethod == null)
                {
                    _startBasicMethod = typeof(LevelPlayerWeaponManager).GetMethod(
                        "StartBasic",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public
                    );
                }
                if (_basicField == null)
                {
                    _basicField = typeof(LevelPlayerWeaponManager).GetField(
                        "basic",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public
                    );
                }
                if (_startBasicMethod != null)
                {
                    _startBasicMethod.Invoke(wm, null);
                }
                if (_basicField != null)
                {
                    object basicState = _basicField.GetValue(wm);
                    if (basicState != null)
                    {
                        if (_firingField == null)
                        {
                            _firingField = basicState.GetType().GetField(
                                "firing",
                                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
                            );
                        }
                        if (_firingField != null)
                        {
                            _firingField.SetValue(basicState, true);
                        }
                    }
                }
            }
            catch
            {
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
