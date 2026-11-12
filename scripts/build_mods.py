"""Construtor, exportador de rotas e instalador opcional dos Mods In-Game (Celeste & Cuphead).

1. Executa o motor StratGraph (`src/`) sobre os 8 capítulos de Celeste e as 6 fases
   Run-and-Gun de Cuphead, exportando `mods/dist/stratgraph_routes.json` com as rotas
   ótimas (`StratGraph` vs `BFS`), salas de `ARMA` e becos contraídos (`contracted_into`).
2. Compila os dois mods em C# (.NET Framework 4.0) diretamente contra os binários
   oficiais instalados na Steam:
   - `mods/dist/celeste/StratGraphCelesteMod.dll` + `StratGraphCelesteMod.zip` (Everest)
   - `mods/dist/cuphead/StratGraphCupheadMod.dll` (Unity / BepInEx / Doorstop)
3. Opcionalmente (`--install-games` / `--uninstall-games`), injeta os hooks IL nos
   assemblies dos jogos na Steam com backup automático (`.stratgraph.bak`), permitindo
   testar o HUD rodando direto dentro de Celeste e Cuphead sem instalar loaders externos.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from scripts.extract_celeste_maps import CHAPTER_FILES
from scripts.extract_cuphead_maps import CUPHEAD_RUN_AND_GUN_SCENES
from src.algorithms import run_bfs, run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.preprocessing import contract_dead_ends

MODS_DIR = Path("mods")
DIST_DIR = MODS_DIR / "dist"

CSC_32 = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
CSC_64 = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")

CELESTE_DIR = Path(r"D:\SteamLibrary\steamapps\common\Celeste")
CELESTE_EXE = CELESTE_DIR / "Celeste.exe"
XNA_GAC_BASE = Path(r"C:\Windows\Microsoft.NET\assembly\GAC_32")

CUPHEAD_MANAGED_DIR = Path(r"D:\SteamLibrary\steamapps\common\Cuphead\Cuphead_Data\Managed")
CUPHEAD_ASM_DLL = CUPHEAD_MANAGED_DIR / "Assembly-CSharp.dll"


def export_mod_routes_json(alpha: float = 0.05) -> Path:
    """Exporta `stratgraph_routes.json` com as rotas ótimas e becos contraídos."""
    payload: dict[str, dict[str, object]] = {}

    all_targets: list[tuple[str, Path]] = []
    for slug, _bin in CHAPTER_FILES:
        all_targets.append((f"celeste_{slug}", Path("datasets/celeste") / slug))
    for _idx, slug, _title in CUPHEAD_RUN_AND_GUN_SCENES:
        all_targets.append((f"cuphead_{slug}", Path("datasets/cuphead") / slug))

    for key, ds_dir in all_targets:
        if not ds_dir.is_dir():
            continue
        raw_g = load_graph_from_csv(ds_dir)
        con_g = contract_dead_ends(raw_g)
        layered = build_layered_graph(con_g, alpha=alpha)

        bfs_res = run_bfs(layered)
        strat_res = run_dijkstra(layered)

        weapon_rooms = [v.room_id for v in raw_g.vertices.values() if v.has_weapon]
        weapon_room = weapon_rooms[0] if weapon_rooms else ""

        strat_rooms: list[str] = []
        for node in strat_res.path:
            if not strat_rooms or strat_rooms[-1] != node.room_id:
                strat_rooms.append(node.room_id)

        bfs_rooms: list[str] = []
        for node in bfs_res.path:
            if not bfs_rooms or bfs_rooms[-1] != node.room_id:
                bfs_rooms.append(node.room_id)

        contracted_pairs = [
            f"{parent}:{','.join(children)}"
            for parent, children in sorted(con_g.contracted_into.items())
            if children
        ]

        # Construir a sequência física completa de waypoints TAS (x,y) para StratGraph e para BFS (ambos coletando os becos contraídos)
        wpts_file = ds_dir / "waypoints.json"
        tas_points: list[str] = []
        bfs_points: list[str] = []
        if wpts_file.is_file():
            wdata = json.loads(wpts_file.read_text(encoding="utf-8"))
            edge_wpts = wdata.get("edges", {})

            def build_route_wpts(r_list: list[str]) -> list[str]:
                pts_out: list[str] = []

                def append_sub_tour(host_rm: str) -> None:
                    contracted_sub = con_g.contracted_into.get(host_rm, [])
                    if not contracted_sub:
                        return
                    allowed_sub = set(contracted_sub)
                    vis_sub: set[str] = {host_rm}
                    tour_pairs: list[tuple[str, str]] = []

                    def dfs_mod_tour(cur_sub: str) -> None:
                        nbs = sorted(
                            {
                                e_s.destination
                                for e_s in raw_g.adjacency.get(cur_sub, [])
                                if e_s.destination in allowed_sub
                            }
                        )
                        for nb_sub in nbs:
                            if nb_sub not in vis_sub:
                                vis_sub.add(nb_sub)
                                tour_pairs.append((cur_sub, nb_sub))
                                dfs_mod_tour(nb_sub)
                                tour_pairs.append((nb_sub, cur_sub))

                    dfs_mod_tour(host_rm)
                    for a_rm, b_rm in tour_pairs:
                        for pt in edge_wpts.get(f"{a_rm}->{b_rm}", []):
                            pts_out.append(f"{pt[0]},{pt[1]}")

                if r_list:
                    append_sub_tour(r_list[0])
                for idx_r in range(len(r_list) - 1):
                    u_rm = r_list[idx_r]
                    v_rm = r_list[idx_r + 1]
                    for pt in edge_wpts.get(f"{u_rm}->{v_rm}", []):
                        pts_out.append(f"{pt[0]},{pt[1]}")
                    append_sub_tour(v_rm)
                return pts_out

            tas_points = build_route_wpts(strat_rooms)
            bfs_points = build_route_wpts(bfs_rooms)

        hud_summary = (
            f"StratGraph: Custo Real={strat_res.real_cost:.1f}, w={strat_res.effective_cost:.1f}, "
            f"Itens={strat_res.collectibles_count} | BFS: Custo Real={bfs_res.real_cost:.1f}, "
            f"w={bfs_res.effective_cost:.1f}, Itens={bfs_res.collectibles_count}"
        )

        payload[key] = {
            "weapon_room": weapon_room,
            "strat_rooms": strat_rooms,
            "bfs_rooms": bfs_rooms,
            "contracted_text": ";".join(contracted_pairs),
            "tas_waypoints_flat": ";".join(tas_points),
            "bfs_waypoints_flat": ";".join(bfs_points),
            "hud_summary": hud_summary,
            "strat_real_cost": round(strat_res.real_cost, 2),
            "strat_effective_cost": round(strat_res.effective_cost, 2),
            "strat_items": strat_res.collectibles_count,
            "bfs_real_cost": round(bfs_res.real_cost, 2),
            "bfs_effective_cost": round(bfs_res.effective_cost, 2),
            "bfs_items": bfs_res.collectibles_count,
        }

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DIST_DIR / "stratgraph_routes.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return json_path


def _find_xna_dll(short_name: str) -> Path | None:
    folder = XNA_GAC_BASE / short_name
    if not folder.is_dir():
        return None
    matches = list(folder.rglob(f"{short_name}.dll"))
    return matches[0] if matches else None


def compile_celeste_mod(routes_json: Path) -> Path | None:
    """Compila `StratGraphCelesteMod.dll` e empacota `StratGraphCelesteMod.zip` (Everest)."""
    out_dir = DIST_DIR / "celeste"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(routes_json, out_dir / "stratgraph_routes.json")
    shutil.copy2(MODS_DIR / "celeste_stratgraph" / "everest.yaml", out_dir / "everest.yaml")

    ref_exe = CELESTE_EXE.with_suffix(".exe.stratgraph.bak") if CELESTE_EXE.with_suffix(".exe.stratgraph.bak").is_file() else CELESTE_EXE
    if not CSC_32.is_file() or not ref_exe.is_file():
        print("[Aviso] Compilador 32-bit ou Celeste.exe não encontrado; pulando build binário de Celeste.")
        return None

    xna_core = _find_xna_dll("Microsoft.Xna.Framework")
    xna_game = _find_xna_dll("Microsoft.Xna.Framework.Game")
    xna_gfx = _find_xna_dll("Microsoft.Xna.Framework.Graphics")
    if not (xna_core and xna_game and xna_gfx):
        print("[Aviso] DLLs do XNA 4.0 não encontradas no GAC_32; pulando build de Celeste.")
        return None

    dll_out = out_dir / "StratGraphCelesteMod.dll"
    cs_file = MODS_DIR / "celeste_stratgraph" / "StratGraphCelesteHud.cs"

    cmd = [
        str(CSC_32),
        "/nologo",
        "/target:library",
        "/platform:x86",
        f"/out:{dll_out}",
        f"/reference:{ref_exe}",
        f"/reference:{xna_core}",
        f"/reference:{xna_game}",
        f"/reference:{xna_gfx}",
        str(cs_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Erro ao compilar mod do Celeste:\n{res.stdout}\n{res.stderr}")

    zip_out = out_dir / "StratGraphCelesteMod.zip"
    with zipfile.ZipFile(zip_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(out_dir / "everest.yaml", "everest.yaml")
        zf.write(dll_out, "StratGraphCelesteMod.dll")
        zf.write(out_dir / "stratgraph_routes.json", "stratgraph_routes.json")

    return dll_out


def compile_cuphead_mod(routes_json: Path) -> Path | None:
    """Compila `StratGraphCupheadMod.dll` contra as DLLs reais do Cuphead (Unity)."""
    out_dir = DIST_DIR / "cuphead"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(routes_json, out_dir / "stratgraph_routes.json")

    ref_asm = CUPHEAD_ASM_DLL.with_suffix(".dll.stratgraph.bak") if CUPHEAD_ASM_DLL.with_suffix(".dll.stratgraph.bak").is_file() else CUPHEAD_ASM_DLL
    if not CSC_64.is_file() or not ref_asm.is_file():
        print("[Aviso] Compilador 64-bit ou pasta Managed do Cuphead não encontrada.")
        return None

    dll_out = out_dir / "StratGraphCupheadMod.dll"
    cs_file = MODS_DIR / "cuphead_stratgraph" / "StratGraphCupheadHud.cs"

    refs = [
        ref_asm,
        CUPHEAD_MANAGED_DIR / "UnityEngine.dll",
        CUPHEAD_MANAGED_DIR / "UnityEngine.CoreModule.dll",
        CUPHEAD_MANAGED_DIR / "UnityEngine.IMGUIModule.dll",
    ]
    cmd = [
        str(CSC_64),
        "/nologo",
        "/target:library",
        f"/out:{dll_out}",
        *[f"/reference:{r}" for r in refs],
        str(cs_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Erro ao compilar mod do Cuphead:\n{res.stdout}\n{res.stderr}")

    return dll_out


def install_mods_into_steam_games(routes_json: Path, cel_dll: Path | None, cup_dll: Path | None) -> None:
    """Injeta os hooks IL em Cuphead e Celeste na Steam via .NET 8 + Mono.Cecil (com backup `.stratgraph.bak`)."""
    cecil_candidates = list(
        Path(r"D:\SteamLibrary\steamapps\common").rglob("Mono.Cecil.dll")
    )
    if not cecil_candidates:
        raise RuntimeError("Mono.Cecil.dll não encontrado para injeção IL automática.")
    cecil_dll = cecil_candidates[0]

    patcher_dir = DIST_DIR / "_il_patcher"
    patcher_dir.mkdir(parents=True, exist_ok=True)

    csproj_content = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="Mono.Cecil">
      <HintPath>{cecil_dll}</HintPath>
    </Reference>
  </ItemGroup>
</Project>
"""
    (patcher_dir / "IlPatcher.csproj").write_text(csproj_content, encoding="utf-8")

    program_cs = r"""using Mono.Cecil;
using Mono.Cecil.Cil;

class Program
{
    static int Main(string[] args)
    {
        string mode = args[0];
        string srcAssembly = args[1];
        string modAssembly = args[2];
        string dstAssembly = args[3];

        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(srcAssembly)!);
        var rp = new ReaderParameters { AssemblyResolver = resolver };

        using var asm = AssemblyDefinition.ReadAssembly(srcAssembly, rp);
        using var modAsm = AssemblyDefinition.ReadAssembly(modAssembly, rp);

        if (mode == "cuphead")
        {
            var overlayType = modAsm.MainModule.GetType("StratGraph.CupheadMod.StratGraphCupheadOverlay");
            var initRef = asm.MainModule.ImportReference(overlayType.Methods.First(m => m.Name == "Init"));

            var slType = asm.MainModule.GetType("SceneLoader");
            var awake = slType.Methods.First(m => m.Name == "Awake");
            var il = awake.Body.GetILProcessor();
            il.InsertBefore(awake.Body.Instructions[0], il.Create(OpCodes.Call, initRef));

            var chType = asm.MainModule.GetType("Cuphead");
            var chInit = chType?.Methods.FirstOrDefault(m => m.Name == "Init");
            if (chInit != null && chInit.HasBody)
            {
                var il2 = chInit.Body.GetILProcessor();
                il2.InsertBefore(chInit.Body.Instructions[0], il2.Create(OpCodes.Call, initRef));
            }
        }
        else if (mode == "celeste")
        {
            var hudType = modAsm.MainModule.GetType("Celeste.Mod.StratGraph.StratGraphHudEntity");
            var attachRef = asm.MainModule.ImportReference(hudType.Methods.First(m => m.Name == "AttachToLevel"));

            var lvlType = asm.MainModule.GetType("Celeste.Level");
            var begin = lvlType.Methods.First(m => m.Name == "Begin");
            var il = begin.Body.GetILProcessor();
            var retInstr = begin.Body.Instructions.Last();
            il.InsertBefore(retInstr, il.Create(OpCodes.Ldarg_0));
            il.InsertBefore(retInstr, il.Create(OpCodes.Call, attachRef));
        }

        asm.Write(dstAssembly);
        return 0;
    }
}
"""
    (patcher_dir / "Program.cs").write_text(program_cs, encoding="utf-8")

    # 1. Instalar no Cuphead
    if cup_dll and CUPHEAD_ASM_DLL.is_file():
        cup_bak = CUPHEAD_ASM_DLL.with_suffix(".dll.stratgraph.bak")
        if not cup_bak.is_file():
            shutil.copy2(CUPHEAD_ASM_DLL, cup_bak)
        shutil.copy2(cup_dll, CUPHEAD_MANAGED_DIR / "StratGraphCupheadMod.dll")
        shutil.copy2(routes_json, CUPHEAD_MANAGED_DIR / "stratgraph_routes.json")

        subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(patcher_dir / "IlPatcher.csproj"),
                "--",
                "cuphead",
                str(cup_bak),
                str(CUPHEAD_MANAGED_DIR / "StratGraphCupheadMod.dll"),
                str(CUPHEAD_ASM_DLL),
            ],
            check=True,
        )
        print(f"[Cuphead] Mod instalado na Steam! (Backup salvo em {cup_bak.name})")

    # 2. Instalar no Celeste
    if cel_dll and CELESTE_EXE.is_file():
        cel_bak = CELESTE_EXE.with_suffix(".exe.stratgraph.bak")
        if not cel_bak.is_file():
            shutil.copy2(CELESTE_EXE, cel_bak)
        shutil.copy2(cel_dll, CELESTE_DIR / "StratGraphCelesteMod.dll")
        shutil.copy2(routes_json, CELESTE_DIR / "stratgraph_routes.json")

        subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(patcher_dir / "IlPatcher.csproj"),
                "--",
                "celeste",
                str(cel_bak),
                str(CELESTE_DIR / "StratGraphCelesteMod.dll"),
                str(CELESTE_EXE),
            ],
            check=True,
        )
        print(f"[Celeste] Mod instalado na Steam! (Backup salvo em {cel_bak.name})")


def uninstall_mods_from_steam_games() -> None:
    """Restaura os backups originais (`.stratgraph.bak`) de Cuphead e Celeste."""
    cup_bak = CUPHEAD_ASM_DLL.with_suffix(".dll.stratgraph.bak")
    if cup_bak.is_file():
        shutil.copy2(cup_bak, CUPHEAD_ASM_DLL)
        cup_bak.unlink()
        for f in ("StratGraphCupheadMod.dll", "stratgraph_routes.json"):
            p = CUPHEAD_MANAGED_DIR / f
            if p.is_file():
                p.unlink()
        print("[Cuphead] Backup original restaurado com sucesso.")

    cel_bak = CELESTE_EXE.with_suffix(".exe.stratgraph.bak")
    if cel_bak.is_file():
        shutil.copy2(cel_bak, CELESTE_EXE)
        cel_bak.unlink()
        for f in ("StratGraphCelesteMod.dll", "stratgraph_routes.json"):
            p = CELESTE_DIR / f
            if p.is_file():
                p.unlink()
        print("[Celeste] Backup original restaurado com sucesso.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compila os mods C# de Celeste e Cuphead e exporta stratgraph_routes.json."
    )
    parser.add_argument(
        "--install-games",
        action="store_true",
        help="Injeta os mods diretamente nos jogos da Steam (com backup automático .stratgraph.bak).",
    )
    parser.add_argument(
        "--uninstall-games",
        action="store_true",
        help="Restaura os binários originais de Celeste e Cuphead na Steam.",
    )
    args = parser.parse_args()

    if args.uninstall_games:
        uninstall_mods_from_steam_games()
        return 0

    routes_json = export_mod_routes_json()
    print(f"Rotas ótimas para mods exportadas em: {routes_json} ({routes_json.stat().st_size} bytes)")

    cel_dll = compile_celeste_mod(routes_json)
    if cel_dll:
        print(f"Mod Celeste compilado com sucesso:  {cel_dll} ({cel_dll.stat().st_size} bytes)")

    cup_dll = compile_cuphead_mod(routes_json)
    if cup_dll:
        print(f"Mod Cuphead compilado com sucesso:  {cup_dll} ({cup_dll.stat().st_size} bytes)")

    if args.install_games:
        install_mods_into_steam_games(routes_json, cel_dll, cup_dll)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
