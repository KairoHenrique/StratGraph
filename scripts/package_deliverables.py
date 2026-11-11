"""Empacota os entregáveis finais para upload direto no Overleaf e no Zenodo/Mendeley Data.

Gera em `results/`:
1. `stratgraph_overleaf.zip`: contém `main.tex`, `references.bib` e `figures/*.pdf`
   pronto para `New Project -> Upload Project` no Overleaf;
2. `stratgraph_datasets_zenodo.zip`: contém toda a pasta `datasets/` documentada
   (`ESQUEMA_DATASET.md`, `celeste/`, `cuphead/`, `synthetic/`, `sample_toy/`)
   pronto para publicação de DOI no Zenodo ou Mendeley Data.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

from pathlib import Path
import zipfile


def package_overleaf(out_zip: Path = Path("results/stratgraph_overleaf.zip")) -> Path:
    """Cria o pacote `.zip` pronto para importação direta no Overleaf."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    article_dir = Path("article")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(article_dir / "main.tex", arcname="main.tex")
        zf.write(article_dir / "references.bib", arcname="references.bib")
        fig_dir = article_dir / "figures"
        if fig_dir.exists():
            for fig in sorted(fig_dir.glob("*.pdf")):
                zf.write(fig, arcname=f"figures/{fig.name}")
    return out_zip


def package_zenodo(out_zip: Path = Path("results/stratgraph_datasets_zenodo.zip")) -> Path:
    """Cria o pacote `.zip` com todos os datasets e esquema para upload no Zenodo."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    datasets_dir = Path("datasets")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(datasets_dir.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(datasets_dir.parent)
                zf.write(file_path, arcname=str(rel).replace("\\", "/"))
        summary_csv = Path("results/benchmark_summary.csv")
        if summary_csv.exists():
            zf.write(summary_csv, arcname="results/benchmark_summary.csv")
        sens_csv = Path("results/alpha_sensitivity.csv")
        if sens_csv.exists():
            zf.write(sens_csv, arcname="results/alpha_sensitivity.csv")
    return out_zip


def main() -> int:
    ov = package_overleaf()
    zn = package_zenodo()
    print(f"Pacote Overleaf gerado: {ov} ({ov.stat().st_size} bytes)")
    print(f"Pacote Zenodo gerado:   {zn} ({zn.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

